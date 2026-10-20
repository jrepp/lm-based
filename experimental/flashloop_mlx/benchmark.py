"""Reproducible warm decode benchmark, including cache flushes and loop receipts."""

import argparse
import hashlib
import json
from pathlib import Path
import statistics
import time

import mlx.core as mx
from transformers import AutoTokenizer

from .cache import CrossLoopCache
from .engine import OuroEngine
from .generate import PROMPT


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("model", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--steps", type=int, default=64)
    parser.add_argument("--repeats", type=int, default=2)
    comparison = parser.add_mutually_exclusive_group()
    comparison.add_argument("--compare-selected", action="store_true")
    comparison.add_argument("--compare-execution", action="store_true")
    parser.add_argument("--eval-every", type=int, default=8)
    parser.add_argument("--baseline-eval-every", type=int, default=1)
    parser.add_argument("--compiled-ops", action="store_true")
    parser.add_argument("--prompt-repeats", type=int, default=1)
    args = parser.parse_args()
    if args.output.exists() or not 1 <= args.steps <= 256 or not 1 <= args.repeats <= 5:
        parser.error("output must be new; steps 1..256 and repeats 1..5")
    if not (1 <= args.eval_every <= 48 and 1 <= args.baseline_eval_every <= 48):
        parser.error("eval-every must be 1..48")
    if not 1 <= args.prompt_repeats <= 8:
        parser.error("prompt-repeats must be 1..8")
    hashes = {name: hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()
              for name in ("engine.py", "cache.py", "selected_kv.py", "benchmark.py")}
    mx.set_default_device(mx.gpu)
    mx.set_memory_limit(12 * 1024**3)
    tokenizer = AutoTokenizer.from_pretrained(str(args.model), local_files_only=True)
    text = tokenizer.apply_chat_template([{"role": "user", "content": PROMPT * args.prompt_repeats}],
                                         tokenize=False, add_generation_prompt=True, enable_thinking=True)
    prompt = tokenizer.encode(text, add_special_tokens=False)
    base = OuroEngine.load(args.model)
    append_times = []
    original = CrossLoopCache.append

    def timed_append(cache, keys, values):
        start = time.perf_counter()
        result = original(cache, keys, values)
        append_times.append(time.perf_counter() - start)
        return result
    CrossLoopCache.append = timed_append
    runs = []

    def record(status, checks=None):
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps({"status": status, "checks": checks or {},
            "source_sha256": hashes, "prompt_token_ids": prompt, "runs": runs}, indent=2) + "\n")

    try:
        order = [True] * args.repeats
        if args.compare_selected:
            order = [selected for repeat in range(args.repeats)
                     for selected in ((False, True) if repeat % 2 == 0 else (True, False))]
        variants = [(selected, args.eval_every, args.compiled_ops) for selected in order]
        if args.compare_execution:
            baseline, candidate = (True, args.baseline_eval_every, False), (True, args.eval_every, args.compiled_ops)
            variants = [variant for repeat in range(args.repeats)
                        for variant in ((baseline, candidate) if repeat % 2 == 0 else (candidate, baseline))]
        for selected, eval_every, compiled_ops in variants:
            mx.reset_peak_memory()
            engine = OuroEngine(base.config, base.weights, selected_reads=selected,
                                eval_every=eval_every, compiled_ops=compiled_ops)
            prefill_start = time.perf_counter()
            logits = engine.prefill(prompt)
            mx.eval(logits)
            prefill_seconds = time.perf_counter() - prefill_start
            tokens, timings, append_per_token = [], [], []
            for step in range(args.steps):
                token = int(mx.argmax(logits).item())
                tokens.append(token)
                append_times.clear()
                start = time.perf_counter()
                logits = engine.decode(token)
                mx.eval(logits)
                timings.append(time.perf_counter() - start)
                append_per_token.append(sum(append_times))
            run = {"selected_reads": selected, "eval_every": eval_every, "compiled_ops": compiled_ops,
                   "prefill_seconds": prefill_seconds, "peak_memory_bytes": mx.get_peak_memory(),
                   "token_ids": tokens, "decode_seconds": timings,
                   "append_seconds": append_per_token, "loop_receipts": engine.receipts,
                   "cache_bytes": sum(c.storage_bytes for c in engine.cache),
                   "median_seconds": statistics.median(timings),
                   "tokens_per_second": len(timings) / sum(timings),
                   "append_fraction": sum(append_per_token) / sum(timings)}
            runs.append(run)
            record("incomplete")
            print(json.dumps({k: v for k, v in run.items() if not isinstance(v, list)}), flush=True)
            engine = None
            mx.clear_cache()
    finally:
        CrossLoopCache.append = original
    checks = {"source_unchanged": all(
        hashlib.sha256(Path(__file__).with_name(n).read_bytes()).hexdigest() == h
        for n, h in hashes.items())}
    if args.compare_selected or args.compare_execution:
        for key in ("token_ids", "loop_receipts", "cache_bytes"):
            checks[key + "_identical"] = all(run[key] == runs[0][key] for run in runs[1:])
    record("passed" if all(checks.values()) else "failed", checks)
    if not all(checks.values()):
        raise SystemExit("benchmark checks failed; results retained in " + str(args.output))



if __name__ == "__main__":
    main()
