import unittest

import mlx.core as mx
import numpy as np

from experimental.flashloop_mlx.cache import CrossLoopCache
from experimental.flashloop_mlx.selected_kv import gather_selected


class SelectedKVTests(unittest.TestCase):
    def test_gather_matches_dense_reconstruction(self):
        rng = np.random.default_rng(321)
        for dtype in (mx.float32, mx.float16, mx.bfloat16):
            for length, dim, group, residual in ((17, 33, 16, 8), (193, 128, 64, 64), (128, 65, 16, 0)):
                shape = (2, 3, length, dim)
                arrays = [mx.array(rng.normal(size=shape)).astype(dtype) for _ in range(8)]
                cache = CrossLoopCache.from_loops(arrays[:4], arrays[4:], group_size=group, residual_length=residual)
                current = [mx.array(rng.normal(size=(2, 3, 1, dim))).astype(dtype) for _ in range(2)]
                idx = rng.integers(0, length + 1, size=(2, 3, 13), dtype=np.int32)
                idx[..., :4] = [0, length - 1, length, length // 2]
                indices = mx.array(idx)
                for loop in range(4):
                    actual = gather_selected(cache, loop, indices, *current)
                    for got, old, new in zip(actual, cache.rows(loop, 0, length), current):
                        full = mx.concatenate((old, new), axis=2)
                        want = mx.take_along_axis(full, mx.broadcast_to(indices[..., None], got.shape), axis=2)
                        np.testing.assert_array_equal(np.array(got.astype(mx.float32)), np.array(want.astype(mx.float32)))

    def test_invalid_indices_are_safe(self):
        x = mx.ones((1, 1, 193, 128))
        cache = CrossLoopCache.from_loops([x] * 4, [x] * 4)
        current = x[:, :, :1]
        k, v = gather_selected(cache, 3, mx.array([[[-1, 194]]]), current, current)
        self.assertTrue(mx.all(mx.isnan(k) & mx.isnan(v)).item())
        with self.assertRaises(ValueError):
            gather_selected(cache, 4, mx.array([[[0]]]), current, current)

    def test_strided_inputs_and_partial_loop_cache(self):
        rng = np.random.default_rng(827)
        for length in (7, 129):
            x = mx.array(rng.normal(size=(2, 4, length, 32)).astype(np.float32))
            cache = CrossLoopCache.from_loops([x, -x], [-x, x])
            # Slices have gaps between heads, batches and selected positions.
            current = x[:, :, :1]
            indices = mx.broadcast_to(mx.array([[[0, 1, length, 0]]]), (2, 4, 4))[..., ::2]
            actual = gather_selected(cache, 1, indices, current, -current)
            for got, old, new in zip(actual, cache.rows(1, 0, length), (current, -current)):
                want = mx.take_along_axis(mx.concatenate((old, new), axis=2),
                                         mx.broadcast_to(indices[..., None], got.shape), axis=2)
                np.testing.assert_array_equal(np.array(got), np.array(want))
