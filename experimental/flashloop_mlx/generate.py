"""Bounded local thinking test with runtime loop receipts and answer checks."""

import argparse
import hashlib
import json
from pathlib import Path
import time

import mlx.core as mx
from transformers import AutoTokenizer

from .engine import OuroEngine
from .trajectory import validate


PROMPT = """Solve this small inventory problem. A shop receives 19 boxes, and every
box contains exactly 23 bolts. There were no bolts in stock before this delivery.
After all of the boxes have been unpacked, the shop sells 58 individual bolts.
There are no damaged bolts, no returns, no additional deliveries, and no other
sales. How many individual bolts remain in the shop?

Use the numbers in the question exactly as written. The boxes are packaging, not
extra inventory items. First determine the number of bolts delivered and then
subtract the bolts sold. Briefly check your arithmetic in your thinking, keeping
that explanation short. Give the final count as a whole number. End your response
with a separate line in precisely this format: Answer: N, replacing N with the
number of bolts remaining."""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("model", type=Path)
    parser.add_argument("--mode", choices=("dense", "flash"), default="flash")
    parser.add_argument("--max-tokens", type=int, default=1024)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--eval-every", type=int, default=8)
    parser.add_argument("--compiled-ops", action="store_true")
    args = parser.parse_args()
    if not 1 <= args.max_tokens <= 1024:
        raise SystemExit("max-tokens must be 1..1024 for this bounded test")
    if args.output.exists():
        raise SystemExit("refusing to overwrite an existing trajectory")
    source_names = ("engine.py", "cache.py", "selected_kv.py", "generate.py", "trajectory.py")
    source_hashes = {name: hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()
                     for name in source_names}
    model_hashes = {}
    for path in sorted(args.model.glob("*.safetensors")):
        with path.open("rb") as handle:
            model_hashes[path.name] = hashlib.file_digest(handle, "sha256").hexdigest()
    mx.set_default_device(mx.gpu)
    mx.set_memory_limit(12 * 1024**3)
    tokenizer = AutoTokenizer.from_pretrained(str(args.model), local_files_only=True)
    prompt = tokenizer.apply_chat_template([{"role": "user", "content": PROMPT}],
                                           tokenize=False, add_generation_prompt=True, enable_thinking=True)
    tokens = tokenizer.encode(prompt, add_special_tokens=False)
    print(json.dumps({"stage": "load", "mode": args.mode, "prompt_tokens": len(tokens)}), flush=True)
    started = time.monotonic()
    engine = OuroEngine.load(args.model, flash=args.mode == "flash",
                             eval_every=args.eval_every, compiled_ops=args.compiled_ops)
    loaded = time.monotonic()
    logits = engine.prefill(tokens)
    mx.eval(logits)
    prefilling = time.monotonic() - loaded
    print(json.dumps({"stage": "prefilled", "seconds": prefilling,
                      "cache_bytes": sum(c.storage_bytes for c in engine.cache)}), flush=True)
    generated, timings = [], []
    stopped = False
    end_ids = {tokenizer.eos_token_id, tokenizer.convert_tokens_to_ids("<|im_end|>")}
    for step in range(args.max_tokens):
        token = int(mx.argmax(logits).item())
        generated.append(token)
        if token in end_ids:
            stopped = True
            break
        if step + 1 == args.max_tokens:
            break
        before = time.monotonic()
        logits = engine.decode(token)
        mx.eval(logits)
        timings.append(time.monotonic() - before)
        if (step + 1) % 16 == 0:
            print(json.dumps({"stage": "decode", "tokens": step + 1,
                              "last_seconds": timings[-1],
                              "text_tail": tokenizer.decode(generated[-48:], skip_special_tokens=False)}), flush=True)
    text = tokenizer.decode(generated, skip_special_tokens=False)
    checks = validate(engine.receipts, generated, text, prompt_tokens=len(tokens),
                      layers=engine.layers, flash=args.mode == "flash")
    checks["stopped_on_end_token"] = stopped
    checks["packed_prefix_exercised"] = args.mode == "dense" or engine.cache[0].keys[0].packed is not None
    checks["source_unchanged_during_run"] = all(
        hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest() == digest
        for name, digest in source_hashes.items())
    receipt = {
        "schema_version": 1, "mode": args.mode, "model": args.model.name,
        "eval_every": engine.eval_every, "compiled_ops": engine.compiled_ops,
        "source_sha256": source_hashes, "checkpoint_sha256": model_hashes,
        "config": engine.config, "prompt": prompt, "prompt_token_ids": tokens,
        "generated_token_ids": generated, "completion": text,
        "prompt_tokens": len(tokens), "completion_tokens": len(generated),
        "load_seconds": loaded - started, "prefill_seconds": prefilling,
        "decode_seconds_per_token": timings, "elapsed_seconds": time.monotonic() - started,
        "stored_cache_bytes": sum(c.storage_bytes for c in engine.cache),
        "mlx_peak_bytes": mx.get_peak_memory(), "checks": checks,
        "loop_receipts": engine.receipts,
        "limitations": "One arithmetic case; visible thinking and runtime loop metrics do not prove faithful reasoning.",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps({"stage": "complete", "checks": checks, "output": str(args.output)}), flush=True)
    print(text, flush=True)
    if not all(checks.values()):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
