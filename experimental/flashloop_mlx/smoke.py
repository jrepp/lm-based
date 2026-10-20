"""Small synthetic Metal exercise; not an Ouro model or performance benchmark."""

import gc
import json

import mlx.core as mx

from .cache import CrossLoopCache


def main():
    if not mx.metal.is_available():
        raise SystemExit("this smoke check requires Apple Metal")
    mx.set_default_device(mx.gpu)
    mx.random.seed(812)
    mx.clear_cache()
    baseline = mx.get_active_memory()
    shape = (1, 2, 512, 128)
    keys = [mx.random.normal(shape).astype(mx.bfloat16) for _ in range(4)]
    values = [mx.random.normal(shape).astype(mx.bfloat16) for _ in range(4)]
    mx.eval(keys, values)
    dense_bytes = sum(x.nbytes for x in keys + values)
    cache = CrossLoopCache.from_loops(keys, values)
    del keys, values
    gc.collect()
    mx.clear_cache()
    cache_active_delta = mx.get_active_memory() - baseline
    query = mx.random.normal((1, 2, 1, 128))
    output = cache.attend(query, loop=3)
    mx.eval(output)
    if not mx.all(mx.isfinite(output)).item():
        raise RuntimeError("non-finite attention output")
    print(json.dumps({
        "kind": "synthetic_mlx_cache_smoke",
        "metal": True,
        "shape_per_loop": shape,
        "loops": 4,
        "dense_bf16_kv_bytes": dense_bytes,
        "stored_array_bytes": cache.storage_bytes,
        "stored_to_dense_ratio": cache.storage_bytes / dense_bytes,
        "mlx_active_bytes_above_baseline_after_releasing_inputs": cache_active_delta,
        "finite_attention": True,
        "limitations": "Static cache, all rows retained, no model weights, not a speed benchmark",
    }, indent=2))


if __name__ == "__main__":
    main()
