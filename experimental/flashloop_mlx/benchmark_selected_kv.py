"""Isolate selected cache reading from model weight traffic; not a token-rate test."""

import json
import statistics
import time

import mlx.core as mx

from .cache import CrossLoopCache
from .selected_kv import gather_selected


def main():
    mx.set_default_device(mx.gpu)
    mx.random.seed(197)
    for length in (198, 1024, 3072):
        shape = (1, 16, length, 128)
        arrays = [mx.random.normal(shape).astype(mx.bfloat16) for _ in range(8)]
        cache = CrossLoopCache.from_loops(arrays[:4], arrays[4:])
        current = [mx.random.normal((1, 16, 1, 128)).astype(mx.bfloat16) for _ in range(2)]
        count = (length + 10) // 10
        indices = mx.sort(mx.random.randint(0, length + 1, (1, 16, count)), axis=-1)
        mx.eval(*current, indices)

        def reference():
            k, v = cache.rows(3, 0, length)
            gather = mx.broadcast_to(indices[..., None], (1, 16, count, 128))
            return tuple(mx.take_along_axis(mx.concatenate((old, new), axis=2), gather, axis=2)
                         for old, new in zip((k, v), current))

        def selected():
            return gather_selected(cache, 3, indices, *current)

        for got, want in zip(selected(), reference()):
            assert mx.array_equal(got, want).item()
        timings = {"full": [], "selected": []}
        for _ in range(10):
            for name, function in (("full", reference), ("selected", selected),
                                   ("selected", selected), ("full", reference)):
                start = time.perf_counter()
                mx.eval(*function())
                timings[name].append(time.perf_counter() - start)
        full, sparse = (statistics.median(timings[name]) for name in ("full", "selected"))
        print(json.dumps({"context": length, "selected_rows": count, "full_median_ms": full * 1000,
                          "selected_median_ms": sparse * 1000, "reader_speedup": full / sparse,
                          "exact": True, "seconds": timings}), flush=True)
        del arrays, cache, current
        mx.clear_cache()


if __name__ == "__main__":
    main()
