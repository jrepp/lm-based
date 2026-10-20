"""Bounded-label, process-lifetime metrics derived from runtime events."""

from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram, Info
from prometheus_client.core import CounterMetricFamily, GaugeMetricFamily


class DashboardAliases:
    """Compatibility names consumed by serve-manager; backend identity stays MLX."""

    def __init__(self, metrics):
        self.metrics = metrics

    def collect(self):
        m = self.metrics
        for metric, sample, name, family in (
            (m.prompt, "flashloop_prompt_tokens_total", "llamacpp:prompt_tokens", CounterMetricFamily),
            (m.generated, "flashloop_generated_tokens_total", "llamacpp:tokens_predicted", CounterMetricFamily),
            (m.prefill_time, "flashloop_prefill_seconds_sum", "llamacpp:prompt_seconds", CounterMetricFamily),
            (m.decode_time, "flashloop_decode_seconds_sum", "llamacpp:tokens_predicted_seconds", CounterMetricFamily),
            (m.active, "flashloop_requests_active", "llamacpp:requests_processing", GaugeMetricFamily),
        ):
            value = next(s.value for f in metric.collect() for s in f.samples if s.name == sample)
            yield family(name, "FlashLoop compatibility alias for serve-manager", value=value)


class Metrics:
    def __init__(self, model, mode):
        self.registry = CollectorRegistry()
        def counter(name, help, labels=()):
            return Counter("flashloop_" + name, help, labels, registry=self.registry)
        def gauge(name, help):
            return Gauge("flashloop_" + name, help, registry=self.registry)
        def histogram(name, help, labels=(), buckets=(.01, .05, .1, .25, .5, 1, 2, 5, 10, 30, 60, 300, 900)):
            return Histogram("flashloop_" + name, help, labels, registry=self.registry, buckets=buckets)
        self.info = Info("flashloop_backend", "Serving backend identity", registry=self.registry)
        self.info.info({"model": model, "mode": mode, "harness": "mlx"})
        self.http = counter("http_requests_total", "HTTP responses by normalized route", ("method", "route", "status"))
        self.requests = counter("generation_requests_total", "Finished generation attempts", ("outcome",))
        self.active = gauge("requests_active", "Admitted generation requests, including loading")
        self.ready = gauge("model_loaded", "One after successful weight loading")
        self.loads = counter("model_loads_total", "Successful weight loads")
        self.prompt = counter("prompt_tokens_total", "Exact input token IDs consumed by successful prefill")
        self.generated = counter("generated_tokens_total", "Exact selected output token IDs, including end tokens")
        self.request_time = histogram("request_seconds", "Admission to completion, including cold load")
        self.load_time = histogram("load_seconds", "Weight load latency")
        self.ttft = histogram("time_to_first_token_seconds", "Admission to first selected token; not network delivery")
        self.prefill_time = histogram("prefill_seconds", "Completed prompt prefill latency")
        self.decode_time = histogram("decode_seconds", "Completed single-token decode latency")
        self.loops = counter("loop_passes_total", "Completed latent loop passes", ("phase", "loop"))
        self.qkv = counter("qkv_rows_total", "Projected Q/K/V rows", ("phase", "loop"))
        self.mlp = counter("mlp_rows_total", "Executed MLP rows", ("phase", "loop"))
        self.entropy = histogram("next_token_entropy_nats", "Per-loop next-token entropy", ("phase", "loop"),
                                 (0, .001, .01, .05, .1, .25, .5, 1, 2, 4, 8, 16))
        self.delta = histogram("hidden_delta_rms", "Per-loop RMS hidden-state change", ("phase", "loop"),
                               (0, .001, .01, .05, .1, .25, .5, 1, 2, 4, 8))
        self.cache = gauge("cache_bytes", "Current request's stored KV arrays; zero when idle")
        self.last_cache = gauge("last_request_cache_bytes", "Most recent observed request KV footprint")
        self.context = gauge("context_tokens", "Current request's cached token positions; zero when idle")
        self.memory = gauge("mlx_active_bytes", "Last observed MLX active allocation, including weights")
        self.peak = gauge("mlx_peak_bytes", "Last observed process-lifetime MLX peak allocation")
        self.progress = gauge("last_progress_timestamp_seconds", "Unix time of most recent completed loop")
        self.registry.register(DashboardAliases(self))

    def observe_loop(self, row):
        import time
        phase, loop = row["phase"], str(row["loop"])
        if phase not in ("prefill", "decode") or loop not in ("1", "2", "3", "4"):
            raise ValueError("unsupported loop metric labels")
        labels = phase, loop
        self.loops.labels(*labels).inc()
        self.qkv.labels(*labels).inc(row["qkv_rows"])
        self.mlp.labels(*labels).inc(row["mlp_rows"])
        self.entropy.labels(*labels).observe(row["next_token_entropy"])
        self.delta.labels(*labels).observe(row["hidden_delta_rms"])
        self.progress.set(time.time())
