"""Physical int4 cache and bounded-tile decode attention for MLX.

Adapted from FlashLoop packing/cache contracts at aeaadee10d75b7aa8c4a42a809f15c75d6d3bdc6.
See THIRD_PARTY_NOTICES.md. This is an inference-only cache prototype.
"""

from dataclasses import dataclass
import math

import mlx.core as mx


def _validate(x):
    if x.ndim != 4 or min(x.shape) <= 0:
        raise ValueError("expected nonempty [batch, heads, tokens, channels]")
    if x.dtype not in (mx.float32, mx.float16, mx.bfloat16):
        raise TypeError("expected floating-point KV")
    if not mx.all(mx.isfinite(x)).item():
        raise ValueError("KV must be finite")


@dataclass(frozen=True)
class Packed4Bit:
    payload: mx.array
    minimum: mx.array
    scale: mx.array
    shape: tuple
    axis: str
    group_size: int
    dtype: object

    @property
    def storage_bytes(self):
        return self.payload.nbytes + self.minimum.nbytes + self.scale.nbytes

    def append_groups(self, other):
        """Join complete token groups without decoding or requantizing history."""
        if (self.axis, self.group_size, self.dtype, self.shape[:2], self.shape[3]) != (
                other.axis, other.group_size, other.dtype, other.shape[:2], other.shape[3]):
            raise ValueError("incompatible packed streams")
        if self.shape[2] % self.group_size or other.shape[2] % self.group_size:
            raise ValueError("only complete token groups can be appended")
        payload = mx.concatenate((self.payload, other.payload), axis=2)
        # K metadata has one row per token group; V has one row per token.
        minimum = mx.concatenate((self.minimum, other.minimum), axis=2)
        scale = mx.concatenate((self.scale, other.scale), axis=2)
        mx.eval(payload, minimum, scale)
        shape = self.shape[:2] + (self.shape[2] + other.shape[2], self.shape[3])
        return Packed4Bit(payload, minimum, scale, shape, self.axis, self.group_size, self.dtype)

    def rows(self, start, end):
        """Decode only a token interval, including unaligned group boundaries."""
        if not 0 <= start < end <= self.shape[2]:
            raise ValueError("invalid token interval")
        payload = self.payload[:, :, start:end]
        codes = mx.stack((payload & 15, payload >> 4), axis=-1)
        codes = codes.reshape(*payload.shape[:-1], -1)[..., :self.shape[3]]
        if self.axis == "key":
            groups = mx.arange(start, end) // self.group_size
            minimum = mx.take(self.minimum, groups, axis=2)
            scale = mx.take(self.scale, groups, axis=2)
        else:
            groups = mx.arange(self.shape[3]) // self.group_size
            minimum = mx.take(self.minimum[:, :, start:end], groups, axis=3)
            scale = mx.take(self.scale[:, :, start:end], groups, axis=3)
        return (codes.astype(mx.float32) * scale.astype(mx.float32)
                + minimum.astype(mx.float32)).astype(self.dtype)


def pack(x, *, axis, group_size=64):
    """K: per-channel over token groups; V: per-token over channel groups."""
    _validate(x)
    if axis not in ("key", "value") or type(group_size) is not int or group_size <= 0:
        raise ValueError("invalid axis/group size")
    dim = 2 if axis == "key" else 3
    codes, minima, scales = [], [], []
    for start in range(0, x.shape[dim], group_size):
        part = (x[:, :, start:start + group_size] if dim == 2
                else x[..., start:start + group_size]).astype(mx.float32)
        minimum = mx.min(part, axis=dim, keepdims=True)
        span = mx.max(part, axis=dim, keepdims=True) - minimum
        scale = mx.where(span > 0, span / 15, 1)
        codes.append(mx.clip(mx.round((part - minimum) / scale), 0, 15).astype(mx.uint8))
        minima.append(minimum.astype(mx.float16))
        scales.append(scale.astype(mx.float16))
    codes = mx.concatenate(codes, axis=dim)
    if x.shape[-1] % 2:
        codes = mx.pad(codes, [(0, 0), (0, 0), (0, 0), (0, 1)])
    payload = codes[..., ::2] | (codes[..., 1::2] << 4)
    minimum, scale = mx.concatenate(minima, axis=dim), mx.concatenate(scales, axis=dim)
    mx.eval(payload, minimum, scale)  # Detach lazy construction from full-size inputs.
    if not (mx.all(mx.isfinite(minimum)) & mx.all(mx.isfinite(scale))
            & mx.all(scale > 0)).item():
        raise ValueError("affine metadata is not representable in float16")
    return Packed4Bit(payload, minimum, scale, x.shape, axis, group_size, x.dtype)


@dataclass(frozen=True)
class CacheStream:
    """Packed old tokens plus an exact tail (64..127 tokens at default settings)."""

    packed: Packed4Bit | None
    tail: mx.array
    shape: tuple

    @classmethod
    def from_array(cls, x, *, axis, group_size=64, residual_length=64):
        _validate(x)
        if type(residual_length) is not int or residual_length < 0:
            raise ValueError("invalid residual length")
        if type(group_size) is not int or group_size <= 0:
            raise ValueError("invalid group size")
        if axis not in ("key", "value"):
            raise ValueError("invalid axis")
        boundary = max(0, (x.shape[2] - residual_length) // group_size) * group_size
        packed = pack(x[:, :, :boundary], axis=axis, group_size=group_size) if boundary else None
        # Force a copy: a tail view must not keep the original dense allocation alive.
        tail = mx.array(x[:, :, boundary:])
        mx.eval(tail)
        return cls(packed, tail, x.shape)

    @property
    def storage_bytes(self):
        return (self.packed.storage_bytes if self.packed else 0) + self.tail.nbytes

    def rows(self, start, end):
        if not 0 <= start < end <= self.shape[2]:
            raise ValueError("invalid token interval")
        boundary = self.packed.shape[2] if self.packed else 0
        parts = []
        if start < boundary:
            parts.append(self.packed.rows(start, min(end, boundary)))
        if end > boundary:
            parts.append(self.tail[:, :, max(start - boundary, 0):end - boundary])
        return parts[0] if len(parts) == 1 else mx.concatenate(parts, axis=2)


@dataclass(frozen=True)
class CrossLoopCache:
    """One layer: anchor plus residuals against previously reconstructed KV.

    All rows are retained in later loops for this first correctness baseline.
    Tails are absolute, exact per-loop values, not quantized residuals.
    """

    keys: tuple
    values: tuple
    group_size: int = 64
    residual_length: int = 64

    @classmethod
    def from_loops(cls, keys, values, *, group_size=64, residual_length=64):
        settings = {"group_size": group_size, "residual_length": residual_length}
        if not keys or len(keys) != len(values) or len(keys) > 4:
            raise ValueError("expected matching 1..4 loop KV lists")
        for x in (*keys, *values):
            _validate(x)
            if x.shape != keys[0].shape or x.dtype != keys[0].dtype:
                raise ValueError("loop shapes and dtypes must match")
        def streams(arrays, axis):
            result = []
            for i, x in enumerate(arrays):
                if i == 0:
                    stream = CacheStream.from_array(x, axis=axis, **settings)
                else:
                    # Construction accepts dense prefill snapshots. Decode itself
                    # reconstructs bounded tiles only.
                    previous = cls._reconstruct(result, i - 1, 0, x.shape[2])
                    stream = CacheStream.from_array(
                        (x - previous).astype(x.dtype), axis=axis, **settings
                    )
                    boundary = stream.packed.shape[2] if stream.packed else 0
                    tail = mx.array(x[:, :, boundary:])
                    mx.eval(tail)
                    stream = CacheStream(stream.packed, tail, x.shape)
                result.append(stream)
            return tuple(result)
        return cls(streams(keys, "key"), streams(values, "value"), group_size, residual_length)

    def append(self, keys, values):
        """Return a new cache after appending a complete set of loop snapshots.

        Only old exact tails and new tokens are encoded. Existing packed history
        is copied as bytes, never decoded/requantized. The source cache remains
        usable even if validation or quantization fails.

        Call after all loops for the new token(s) have completed. This does not
        expose partially completed loops to attention.
        """
        if len(keys) != len(self.keys) or len(values) != len(self.values):
            raise ValueError("append requires the same loop count")
        width = keys[0].shape[2] if keys[0].ndim == 4 else 0
        expected = self.shape[:2] + (width, self.shape[3])
        for x in (*keys, *values):
            if x.ndim != 4 or min(x.shape) <= 0:
                raise ValueError("expected nonempty [batch, heads, tokens, channels]")
            if x.dtype not in (mx.float32, mx.float16, mx.bfloat16):
                raise TypeError("expected floating-point KV")
            if x.shape != expected or x.dtype != self.keys[0].tail.dtype:
                raise ValueError("append shapes and dtypes must match the cache")
        # One device evaluation instead of one CPU/GPU round trip per stream.
        finite = mx.all(mx.stack([mx.all(mx.isfinite(x)) for x in (*keys, *values)]))
        pending_keys = [mx.concatenate((s.tail, x), axis=2) for s, x in zip(self.keys, keys)]
        pending_values = [mx.concatenate((s.tail, x), axis=2) for s, x in zip(self.values, values)]
        new_shape = self.shape[:2] + (self.shape[2] + width, self.shape[3])
        if pending_keys[0].shape[2] < self.residual_length + self.group_size:
            # No complete group to compress: tails are absolute per-loop KV.
            # Preserve packed history by reference and never form residuals.
            mx.eval(finite, *pending_keys, *pending_values)
            if not finite.item():
                raise ValueError("KV must be finite")
            def extend(streams, tails):
                return tuple(CacheStream(s.packed, tail, new_shape)
                             for s, tail in zip(streams, tails))
            return type(self)(extend(self.keys, pending_keys), extend(self.values, pending_values),
                              self.group_size, self.residual_length)
        if not finite.item():
            raise ValueError("KV must be finite")
        pending = type(self).from_loops(
            pending_keys, pending_values,
            group_size=self.group_size, residual_length=self.residual_length,
        )
        def join(old_streams, new_streams):
            result = []
            for old, new in zip(old_streams, new_streams):
                packed = old.packed
                if new.packed is not None:
                    packed = new.packed if packed is None else packed.append_groups(new.packed)
                result.append(CacheStream(packed, new.tail, new_shape))
            return tuple(result)
        return type(self)(join(self.keys, pending.keys), join(self.values, pending.values),
                          self.group_size, self.residual_length)

    @property
    def shape(self):
        return self.keys[0].shape

    @property
    def storage_bytes(self):
        return sum(s.storage_bytes for s in (*self.keys, *self.values))

    def rows(self, loop, start, end):
        if not 0 <= loop < len(self.keys):
            raise ValueError("invalid zero-based loop")
        return (self._reconstruct(self.keys, loop, start, end),
                self._reconstruct(self.values, loop, start, end))

    @staticmethod
    def _reconstruct(streams, loop, start, end):
        if not 0 <= start < end <= streams[0].shape[2]:
            raise ValueError("invalid token interval")
        boundary = streams[0].packed.shape[2] if streams[0].packed else 0
        parts = []
        if start < boundary:
            stop = min(end, boundary)
            out = streams[0].packed.rows(start, stop)
            for stream in streams[1:loop + 1]:
                out = out + stream.packed.rows(start, stop)
            parts.append(out)
        if end > boundary:
            parts.append(streams[loop].tail[:, :, max(0, start - boundary):end - boundary])
        return parts[0] if len(parts) == 1 else mx.concatenate(parts, axis=2)

    def attend(self, query, *, loop, tile_size=128):
        """Single-token, unmasked decode using online softmax over bounded tiles.

        All cached positions are visible. Not valid for causal multi-token prefill.
        No full-context dense KV, logits, or probability tensor is constructed.
        """
        expected = (self.shape[0], self.shape[1], 1, self.shape[3])
        if query.shape != expected:
            raise ValueError(f"decode query must have shape {expected}")
        _validate(query)
        if type(tile_size) is not int or tile_size <= 0:
            raise ValueError("invalid tile size")
        q = query.astype(mx.float32) / math.sqrt(self.shape[3])
        maximum = mx.full(expected[:-1] + (1,), -float("inf"))
        denominator = mx.zeros_like(maximum)
        output = mx.zeros(expected, dtype=mx.float32)
        for start in range(0, self.shape[2], tile_size):
            k, v = self.rows(loop, start, min(start + tile_size, self.shape[2]))
            k, v = k.astype(mx.float32), v.astype(mx.float32)
            logits = q @ mx.swapaxes(k, -1, -2)
            next_max = mx.maximum(maximum, mx.max(logits, axis=-1, keepdims=True))
            correction = mx.exp(maximum - next_max)
            weights = mx.exp(logits - next_max)
            denominator = denominator * correction + mx.sum(weights, axis=-1, keepdims=True)
            output = output * correction + weights @ v
            maximum = next_max
            # Bound the lazy graph as well as the sizes of individual intermediates.
            mx.eval(maximum, denominator, output)
        return output / denominator
