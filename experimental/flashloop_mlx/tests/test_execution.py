"""Execution schedules must preserve packed-cache trajectories and observers."""

import unittest

import mlx.core as mx
import numpy as np

from experimental.flashloop_mlx.engine import OuroEngine


class ExecutionTests(unittest.TestCase):
    def test_schedules_and_compilation(self):
        mx.random.seed(719)
        config = dict(model_type="ouro", total_ut_steps=4, num_attention_heads=2,
                      num_key_value_heads=2, head_dim=8, num_hidden_layers=3,
                      rms_norm_eps=1e-6, rope_theta=10000)
        weights = {}
        for name in ("model.embed_tokens", "lm_head"):
            weights[name + ".weight"] = mx.random.normal((32, 16)) * 0.05
        weights["model.norm.weight"] = mx.ones((16,))
        for layer in range(3):
            prefix = f"model.layers.{layer}"
            for norm in ("input_layernorm", "input_layernorm_2", "post_attention_layernorm",
                         "post_attention_layernorm_2"):
                weights[f"{prefix}.{norm}.weight"] = mx.ones((16,))
            for proj in ("q", "k", "v", "o"):
                weights[f"{prefix}.self_attn.{proj}_proj.weight"] = mx.random.normal((16, 16)) * 0.05
            for proj, shape in (("gate", (24, 16)), ("up", (24, 16)), ("down", (16, 24))):
                weights[f"{prefix}.mlp.{proj}_proj.weight"] = mx.random.normal(shape) * 0.05
        mx.eval(weights)
        for dtype in (mx.float32, mx.bfloat16):
            typed_weights = {name: value.astype(dtype) for name, value in weights.items()}
            for flash in (False, True):
                baseline = None
                for interval, compiled in ((1, False), (2, False), (8, False), (8, True)):
                    observed = []
                    engine = OuroEngine(config, typed_weights, flash=flash, eval_every=interval,
                                        compiled_ops=compiled, observer=observed.append)
                    logits = [np.array(engine.prefill([i % 32 for i in range(126)]).astype(mx.float32))]
                    # Cross the 128-token compression boundary with packed history.
                    for token in (3, 7, 11, 17):
                        logits.append(np.array(engine.decode(token).astype(mx.float32)))
                    cache = [[np.array(x.astype(mx.float32)) for loop in range(4)
                              for x in c.rows(loop, 0, engine.position)] for c in engine.cache]
                    self.assertEqual(observed, engine.receipts)
                    self.assertEqual(len(observed), 20)
                    if baseline is None:
                        baseline = (logits, cache, engine.receipts)
                    else:
                        for actual, expected in zip(logits, baseline[0]):
                            np.testing.assert_allclose(actual, expected, atol=2e-5, rtol=2e-4)
                            self.assertEqual(actual.argmax(), expected.argmax())
                        for actual_layer, expected_layer in zip(cache, baseline[1]):
                            for actual, expected in zip(actual_layer, expected_layer):
                                np.testing.assert_allclose(actual, expected, atol=2e-5, rtol=2e-4)
                        if not compiled:
                            self.assertEqual(engine.receipts, baseline[2])



if __name__ == "__main__":
    unittest.main()
