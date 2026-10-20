"""Metal gather/dequantization for FlashLoop's selected late-loop KV rows.

Only selected rows are materialized. Sequential residual additions retain the cache
storage dtype's rounding, matching CrossLoopCache.rows before gathering.
"""

from functools import lru_cache

import mlx.core as mx


@lru_cache(maxsize=16)
def _kernel(axis, loop, packed):
    names = ["indices", "tail", "current"]
    source = """
        uint elem = thread_position_in_grid.x;
        uint dim = current_shape[3];
        uint selected = indices_shape[2];
        uint channel = elem % dim;
        uint row = elem / dim;
        uint head = row / selected;
        int position = int(indices[row]);
        uint boundary = BOUNDARY;
        uint tail_length = tail_shape[2];
        uint length = boundary + tail_length;
        if (position < 0 || uint(position) > length) {
            out[elem] = T(NAN);
            return;
        }
        if (uint(position) == length) {
            out[elem] = current[head * dim + channel];
            return;
        }
        if (uint(position) >= boundary) {
            out[elem] = tail[(head * tail_length + uint(position) - boundary) * dim + channel];
            return;
        }
    """
    if packed:
        source = source.replace("BOUNDARY", "p0_shape[2]")
        source += """
            uint payload_offset = (head * boundary + uint(position)) * ((dim + 1) / 2) + channel / 2;
            uint groups = (dim + GROUP - 1) / GROUP;
            uint meta = IS_KEY
                ? (head * (boundary / GROUP) + uint(position) / GROUP) * dim + channel
                : (head * boundary + uint(position)) * groups + channel / GROUP;
            T result = T(0);
        """
        for i in range(loop + 1):
            names.extend((f"p{i}", f"m{i}", f"s{i}"))
            source += f"""
                uint code{i} = (uint(p{i}[payload_offset]) >> ((channel % 2) * 4)) & 15;
                T value{i} = T(float(code{i}) * float(s{i}[meta]) + float(m{i}[meta]));
                result = {'value0' if i == 0 else f'T(float(result) + float(value{i}))'};
            """
        source += "out[elem] = result;"
    else:
        source = source.replace("BOUNDARY", "0")
    return mx.fast.metal_kernel(name=f"flashloop_selected_{axis}_{loop}_{int(packed)}",
                               input_names=names, output_names=["out"], source=source)


def gather_selected(cache, loop, indices, current_keys, current_values):
    """Gather per-head indices from cached history plus the current token.

    Indices have shape [batch, heads, selected]; engine-generated positions are
    in [0, cache length]. Invalid positions produce NaN without out-of-bounds reads.
    """
    if not 0 <= loop < len(cache.keys):
        raise ValueError("invalid zero-based loop")
    batch, heads, _, dim = cache.shape
    if indices.ndim != 3 or indices.shape[:2] != (batch, heads) or indices.shape[2] < 1:
        raise ValueError("expected nonempty per-head indices")
    if indices.dtype not in (mx.int32, mx.uint32):
        raise TypeError("indices must be int32 or uint32")
    out_shape = (batch, heads, indices.shape[2], dim)
    size = batch * heads * indices.shape[2] * dim
    outputs = []
    for axis, streams, current in (("key", cache.keys, current_keys),
                                   ("value", cache.values, current_values)):
        if current.shape != (batch, heads, 1, dim) or current.dtype != streams[loop].tail.dtype:
            raise ValueError("current KV must match cache heads, channels and dtype")
        packed = streams[0].packed is not None
        inputs = [indices, streams[loop].tail, current]
        if packed:
            for stream in streams[:loop + 1]:
                inputs.extend((stream.packed.payload, stream.packed.minimum, stream.packed.scale))
        outputs.append(_kernel(axis, loop, packed)(
            inputs=inputs, template=[("T", current.dtype), ("GROUP", cache.group_size),
                                     ("IS_KEY", axis == "key")],
            grid=(size, 1, 1), threadgroup=(min(size, 256), 1, 1),
            output_shapes=[out_shape], output_dtypes=[current.dtype])[0])
    return tuple(outputs)
