"""Lazy model loading and exact event accounting on one dedicated MLX thread."""

import time


class GenerationCancelled(Exception):
    pass


class InputTooLong(Exception):
    pass


class Runtime:
    def __init__(self, model_path, mode="flash", max_context=3072):
        self.model_path, self.mode, self.max_context = model_path, mode, max_context
        self.base = self.tokenizer = None
        self.prompt_tokens = self.output_tokens = 0

    def run(self, body, metrics, cancel, admitted):
        import mlx.core as mx
        from transformers import AutoTokenizer
        from .engine import OuroEngine
        mx.set_default_device(mx.gpu)
        mx.set_memory_limit(12 * 1024**3)
        if self.tokenizer is None:
            self.tokenizer = AutoTokenizer.from_pretrained(str(self.model_path), local_files_only=True)
        text = self.tokenizer.apply_chat_template(
            [m.model_dump() for m in body.messages], tokenize=False,
            add_generation_prompt=True, enable_thinking=body.enable_thinking)
        tokens = self.tokenizer.encode(text, add_special_tokens=False)
        if len(tokens) + body.max_tokens > self.max_context:
            raise InputTooLong()
        if cancel.is_set():
            raise GenerationCancelled()
        if self.base is None:
            start = time.monotonic()
            self.base = OuroEngine.load(self.model_path, flash=self.mode == "flash")
            metrics.load_time.observe(time.monotonic() - start)
            metrics.loads.inc()
            metrics.ready.set(1)
        engine = OuroEngine(self.base.config, self.base.weights, flash=self.mode == "flash",
                            observer=metrics.observe_loop)
        generated = []
        def snapshot():
            size = sum(c.storage_bytes for c in engine.cache)
            metrics.cache.set(size)
            metrics.last_cache.set(size)
            metrics.context.set(engine.position)
            metrics.memory.set(mx.get_active_memory())
            metrics.peak.set(mx.get_peak_memory())
        try:
            if cancel.is_set():
                raise GenerationCancelled()
            start = time.monotonic()
            logits = engine.prefill(tokens)
            mx.eval(logits)
            metrics.prefill_time.observe(time.monotonic() - start)
            metrics.prompt.inc(len(tokens))
            self.prompt_tokens = len(tokens)
            snapshot()
            finish = "length"
            end_ids = {self.tokenizer.eos_token_id, self.tokenizer.convert_tokens_to_ids("<|im_end|>")}
            for step in range(body.max_tokens):
                if cancel.is_set():
                    raise GenerationCancelled()
                token = int(mx.argmax(logits).item())
                generated.append(token)
                metrics.generated.inc()
                self.output_tokens = len(generated)
                if step == 0:
                    metrics.ttft.observe(time.monotonic() - admitted)
                if token in end_ids:
                    finish = "stop"
                    break
                if step + 1 < body.max_tokens:
                    start = time.monotonic()
                    logits = engine.decode(token)
                    mx.eval(logits)
                    metrics.decode_time.observe(time.monotonic() - start)
                    snapshot()
            return {"content": self.tokenizer.decode(generated, skip_special_tokens=True),
                    "finish_reason": finish, "prompt_tokens": len(tokens), "completion_tokens": len(generated)}
        finally:
            engine = None
            mx.clear_cache()
            metrics.memory.set(mx.get_active_memory())
            metrics.peak.set(mx.get_peak_memory())
