"""Validate small-model MLX logits against local Ouro and pinned FlashLoop."""

import argparse
import json
import subprocess
import sys

import mlx.core as mx
import numpy as np
import torch
from transformers import AutoConfig, AutoModelForCausalLM

from .engine import OuroEngine
from .verify_upstream import REVISION


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("model", help="local Ouro directory (code/config only; weights are not loaded)")
    parser.add_argument("upstream", help="reviewed FlashLoop checkout")
    parser.add_argument("--device", choices=("cpu", "metal"), default="metal")
    parser.add_argument("--eval-every", type=int, default=8)
    parser.add_argument("--compiled-ops", action="store_true")
    args = parser.parse_args()
    args.cpu = args.device == "cpu"
    if args.cpu:
        mx.set_default_device(mx.cpu)
    if subprocess.check_output(["git", "-C", args.upstream, "rev-parse", "HEAD"], text=True).strip() != REVISION:
        raise SystemExit("unexpected FlashLoop revision")
    if subprocess.check_output(["git", "-C", args.upstream, "status", "--porcelain"], text=True).strip():
        raise SystemExit("upstream checkout must be clean")
    torch.manual_seed(814)
    config = AutoConfig.from_pretrained(args.model, trust_remote_code=True, local_files_only=True)
    config.num_hidden_layers = 2
    config.hidden_size = 64
    config.num_attention_heads = config.num_key_value_heads = 4
    config.head_dim = 16
    config.intermediate_size = 96
    config.vocab_size = 128
    config.layer_types = ["full_attention"] * 2
    config._attn_implementation = "eager"
    model = AutoModelForCausalLM.from_config(config, trust_remote_code=True).float().eval()
    weights = {name: mx.array(value.detach().numpy()) for name, value in model.state_dict().items()}
    errors = []
    def compare(actual, expected):
        actual, expected = np.asarray(actual).reshape(-1), np.asarray(expected).reshape(-1)
        errors.append(float(np.max(np.abs(actual - expected))))
        if args.cpu:
            np.testing.assert_allclose(actual, expected, atol=2e-5, rtol=3e-4)
        else:
            # Metal's arithmetic differs from CPU BLAS and accumulates over
            # recurrent layers. Require bounded error AND identical greedy choice.
            np.testing.assert_allclose(actual, expected, atol=0.003, rtol=3e-4)
            relative_rms = np.linalg.norm(actual - expected) / max(np.linalg.norm(expected), 1e-12)
            assert relative_rms < 0.005, relative_rms
        assert actual.argmax() == expected.argmax()
    tokens = list(range(3, 80))
    engine = OuroEngine(config.to_dict(), weights, flash=False,
                        eval_every=args.eval_every, compiled_ops=args.compiled_ops)
    with torch.no_grad():
        result = model(torch.tensor([tokens]), use_cache=True, exit_at_step=3)
    compare(np.array(engine.prefill(tokens)), result.logits[:, -1:].numpy())
    cache = result.past_key_values
    for token in (7, 9, 13):
        with torch.no_grad():
            result = model(torch.tensor([[token]]), past_key_values=cache, use_cache=True, exit_at_step=3)
        cache = result.past_key_values
        compare(np.array(engine.decode(token)), result.logits.numpy())
    print("PASS: dense MLX prefill + 3 decode steps match original Ouro", flush=True)

    sys.path.insert(0, args.upstream)
    from flashloop import FlashLoopEngine, FlashLoopConfig
    import flashloop.engine as reference_module
    original_sparse = reference_module.sparse_prefill_loop
    def preserve_score_input(layers, hidden, **kwargs):
        # Upstream consume_inputs=True aliases hidden2/hidden3, zeroing the
        # loop-4 change scores. Preserve the prior hidden state for selection.
        return original_sparse(layers, hidden.clone(), **kwargs)
    reference_module.sparse_prefill_loop = preserve_score_input
    reference = FlashLoopEngine(model, config=FlashLoopConfig(kv_reader_backend="triton_row",
                                                             fuse_projection_weights=False),
                                validate_model=False)
    flash = OuroEngine(config.to_dict(), weights, flash=True,
                       eval_every=args.eval_every, compiled_ops=args.compiled_ops)
    output = reference.prefill(torch.tensor([tokens]))
    # Compare execution independently of the cache: this short prompt has no packed
    # prefix. Longer quantized-cache differences are covered by codec tests.
    expected = output.logits.detach().numpy()
    actual = np.array(flash.prefill(tokens))
    compare(actual, expected)
    for token in (7, 9, 13):
        expected = reference.decode(torch.tensor([[token]])).logits.detach().numpy()
        actual = np.array(flash.decode(token))
        compare(actual, expected)
    print(json.dumps({"status": "PASS", "dense_decode_steps": 3, "flash_decode_steps": 3,
                      "prefill_active_rows": [r["active_rows"] for r in flash.receipts[:4]],
                      "reference_revision": REVISION, "reference_adjustment": "clone sparse score input",
                      "eval_every": args.eval_every, "compiled_ops": args.compiled_ops,
                      "device": "cpu" if args.cpu else "metal", "max_logit_absolute_errors": errors}))


if __name__ == "__main__":
    main()
