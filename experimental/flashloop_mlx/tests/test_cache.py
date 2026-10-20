import unittest

import mlx.core as mx
import numpy as np

from experimental.flashloop_mlx.cache import CacheStream, CrossLoopCache, pack


def oracle(x, axis, group=64):
    """Independent NumPy implementation of upstream affine/nibble conventions."""
    dim = 2 if axis == "key" else 3
    chunks, minima, scales = [], [], []
    for start in range(0, x.shape[dim], group):
        slices = [slice(None)] * 4
        slices[dim] = slice(start, start + group)
        part = x[tuple(slices)].astype(np.float32)
        minimum = part.min(axis=dim, keepdims=True)
        span = part.max(axis=dim, keepdims=True) - minimum
        scale = np.where(span > 0, span / 15, 1)
        chunks.append(np.clip(np.rint((part - minimum) / scale), 0, 15).astype(np.uint8))
        minima.append(minimum.astype(np.float16))
        scales.append(scale.astype(np.float16))
    codes = np.concatenate(chunks, axis=dim)
    padded = np.pad(codes, [(0, 0)] * 3 + [(0, x.shape[-1] % 2)])
    payload = padded[..., ::2] | (padded[..., 1::2] << 4)
    minimum, scale = np.concatenate(minima, dim), np.concatenate(scales, dim)
    lo = np.repeat(minimum, group, axis=dim)
    sc = np.repeat(scale, group, axis=dim)
    slices = tuple(slice(0, size) for size in x.shape)
    decoded = codes.astype(np.float32) * sc[slices].astype(np.float32) + lo[slices].astype(np.float32)
    return payload, minimum, scale, decoded.astype(x.dtype)


class CacheTests(unittest.TestCase):
    def setUp(self):
        self.rng = np.random.default_rng(812)

    def test_codec_matches_independent_oracle(self):
        for shape in [(1, 2, 129, 128), (2, 1, 65, 7), (1, 1, 1, 1)]:
            x = self.rng.normal(size=shape).astype(np.float32)
            for axis in ("key", "value"):
                with self.subTest(shape=shape, axis=axis):
                    packed = pack(mx.array(x), axis=axis)
                    expected = oracle(x, axis)
                    for actual, reference in zip(
                        (packed.payload, packed.minimum, packed.scale), expected[:3]
                    ):
                        np.testing.assert_array_equal(np.array(actual), reference)
                    np.testing.assert_allclose(np.array(packed.rows(0, shape[2])), expected[3], atol=1e-6)
                    if shape[2] > 64:
                        np.testing.assert_allclose(np.array(packed.rows(63, 65)), expected[3][:, :, 63:65], atol=1e-6)

    def test_constants_and_half_precision(self):
        for dtype in (mx.float16, mx.bfloat16, mx.float32):
            x = mx.full((1, 2, 128, 128), -2.5, dtype=dtype)
            for axis in ("key", "value"):
                packed = pack(x, axis=axis)
                self.assertTrue(mx.all(packed.rows(0, 128) == x).item())
                self.assertLess(packed.storage_bytes, x.nbytes)

    def test_tail_and_boundary(self):
        for length in (1, 64, 127, 128, 193):
            x = mx.array(self.rng.normal(size=(1, 1, length, 128)).astype(np.float32))
            cache = CacheStream.from_array(x, axis="key")
            boundary = max(0, (length - 64) // 64) * 64
            np.testing.assert_array_equal(np.array(cache.tail), np.array(x[:, :, boundary:]))
            np.testing.assert_array_equal(
                np.array(cache.rows(max(0, length - 32), length)),
                np.array(x[:, :, max(0, length - 32):]),
            )
            if boundary:
                expected = np.concatenate((
                    oracle(np.array(x[:, :, :boundary]), "key")[3],
                    np.array(x[:, :, boundary:]),
                ), axis=2)
                np.testing.assert_allclose(np.array(cache.rows(boundary - 3, boundary + 3)),
                                           expected[:, :, boundary - 3:boundary + 3], atol=1e-6)

    def test_cross_loop_tiled_attention_matches_dense_decoded_cache(self):
        shape = (2, 2, 193, 128)
        keys = [mx.array(self.rng.normal(size=shape).astype(np.float32)) for _ in range(4)]
        values = [mx.array(self.rng.normal(size=shape).astype(np.float32)) for _ in range(4)]
        cache = CrossLoopCache.from_loops(keys, values)
        q = mx.array(self.rng.normal(size=(2, 2, 1, 128)).astype(np.float32))
        for loop in range(4):
            k, v = cache.rows(loop, 0, shape[2])
            # NumPy dense softmax is independent of the MLX online recurrence.
            logits = np.array(q) @ np.swapaxes(np.array(k), -1, -2) / np.sqrt(128)
            exp = np.exp(logits - logits.max(axis=-1, keepdims=True))
            expected = (exp / exp.sum(axis=-1, keepdims=True)) @ np.array(v)
            for tile in (31, 64, 256):
                actual = np.array(cache.attend(q, loop=loop, tile_size=tile))
                np.testing.assert_allclose(actual, expected, atol=2e-6, rtol=2e-5)
        self.assertLess(cache.storage_bytes, sum(x.nbytes for x in keys + values))

    def test_residual_reconstruction_and_storage(self):
        shape = (1, 1, 512, 128)
        keys = [mx.full(shape, i * 0.5, dtype=mx.bfloat16) for i in range(4)]
        values = [mx.full(shape, -i * 0.25, dtype=mx.bfloat16) for i in range(4)]
        cache = CrossLoopCache.from_loops(keys, values)
        for loop in range(4):
            k, v = cache.rows(loop, 0, 512)
            self.assertTrue(mx.all(k == keys[loop]).item())
            self.assertTrue(mx.all(v == values[loop]).item())
        dense_bytes = sum(x.nbytes for x in keys + values)
        self.assertLess(cache.storage_bytes / dense_bytes, 0.4)

    def test_residuals_use_reconstructed_base_and_exact_tail(self):
        shape = (1, 1, 193, 128)
        arrays = [self.rng.normal(size=shape).astype(np.float32) for _ in range(4)]
        cache = CrossLoopCache.from_loops([mx.array(x) for x in arrays],
                                         [mx.array(-x) for x in arrays])
        expected = None
        for loop, x in enumerate(arrays):
            prefix = x[:, :, :128]
            residual = prefix if expected is None else prefix - expected
            decoded = oracle(residual, "key")[3]
            expected = decoded if expected is None else expected + decoded
            k, _ = cache.rows(loop, 0, 193)
            np.testing.assert_allclose(np.array(k[:, :, :128]), expected, atol=2e-6)
            np.testing.assert_array_equal(np.array(k[:, :, 128:]), x[:, :, 128:])

    def test_invalid_inputs(self):
        x = mx.ones((1, 1, 128, 128))
        for kwargs in ({"axis": "other"}, {"axis": "key", "group_size": 0}):
            with self.assertRaises(ValueError):
                pack(x, **kwargs)
        with self.assertRaises(TypeError):
            pack(x.astype(mx.int32), axis="key")
        with self.assertRaises(ValueError):
            pack(x * float("nan"), axis="key")
        with self.assertRaises(ValueError):
            pack(x * 1e6, axis="key")
        cache = CrossLoopCache.from_loops([x], [x])
        for query in (x, mx.ones((1, 2, 1, 128))):
            with self.assertRaises(ValueError):
                cache.attend(query, loop=0)
        with self.assertRaises(ValueError):
            cache.rows(1, 0, 1)
        with self.assertRaises(ValueError):
            cache.rows(0, -1, 1)

    def test_append_matches_rebuild_at_flush_boundaries(self):
        for group, tail in ((64, 64), (16, 8)):
            shape = (1, 2, 259, 128)
            keys = [mx.array(self.rng.normal(size=shape).astype(np.float32)) for _ in range(4)]
            values = [mx.array(self.rng.normal(size=shape).astype(np.float32)) for _ in range(4)]
            prefix = lambda xs, n: [x[:, :, :n] for x in xs]
            cache = CrossLoopCache.from_loops(prefix(keys, 63), prefix(values, 63),
                                              group_size=group, residual_length=tail)
            start = 63
            for end in (64, 127, 128, 129, 192, 259):
                old = cache
                cache = cache.append([x[:, :, start:end] for x in keys],
                                     [x[:, :, start:end] for x in values])
                rebuilt = CrossLoopCache.from_loops(prefix(keys, end), prefix(values, end),
                                                    group_size=group, residual_length=tail)
                self.assertEqual(old.shape[2], start)
                self.assertEqual(cache.storage_bytes, rebuilt.storage_bytes)
                for loop in range(4):
                    for actual, expected in zip(cache.rows(loop, 0, end), rebuilt.rows(loop, 0, end)):
                        np.testing.assert_array_equal(np.array(actual), np.array(expected))
                if old.keys[0].packed:
                    n = old.keys[0].packed.shape[2]
                    np.testing.assert_array_equal(np.array(cache.keys[0].packed.payload[:, :, :n]),
                                                  np.array(old.keys[0].packed.payload))
                start = end
            q = mx.ones((1, 2, 1, 128))
            np.testing.assert_allclose(np.array(cache.attend(q, loop=3)),
                                       np.array(rebuilt.attend(q, loop=3)), atol=1e-6)

    def test_append_validation_is_atomic(self):
        x = mx.ones((1, 1, 128, 128))
        cache = CrossLoopCache.from_loops([x], [x])
        for keys, values in (([], []), ([x], [x.astype(mx.float16)]),
                             ([x], [x * float("nan")])):
            with self.assertRaises(ValueError):
                cache.append(keys, values)
        self.assertEqual(cache.shape, x.shape)
        self.assertTrue(mx.all(cache.rows(0, 0, 128)[0] == x).item())

    def test_exact_tail_append_preserves_packed_history_and_rejects_nonfinite(self):
        shape = (1, 2, 193, 128)
        keys = [mx.array(self.rng.normal(size=shape).astype(np.float32)) for _ in range(4)]
        values = [mx.array(self.rng.normal(size=shape).astype(np.float32)) for _ in range(4)]
        cache = CrossLoopCache.from_loops(keys, values)
        new = mx.ones((1, 2, 1, 128))
        extended = cache.append([new] * 4, [-new] * 4)
        for loop in range(4):
            self.assertIs(extended.keys[loop].packed, cache.keys[loop].packed)
            self.assertIs(extended.values[loop].packed, cache.values[loop].packed)
            before = cache.rows(loop, 0, 193)
            after = extended.rows(loop, 0, 194)
            for old, added, expected in zip(before, after, (new, -new)):
                np.testing.assert_array_equal(np.array(old), np.array(added[:, :, :193]))
                np.testing.assert_array_equal(np.array(expected), np.array(added[:, :, 193:]))
        for bad in (float("nan"), float("inf")):
            with self.assertRaises(ValueError):
                cache.append([new] * 4, [new, new * bad, new, new])
        self.assertEqual(cache.shape, shape)


if __name__ == "__main__":
    unittest.main()
