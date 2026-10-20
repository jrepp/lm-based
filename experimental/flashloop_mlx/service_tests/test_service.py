import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
import threading
from contextlib import nullcontext
import unittest

import httpx
from fastapi.testclient import TestClient

from experimental.flashloop_mlx.runtime import GenerationCancelled, InputTooLong
from experimental.flashloop_mlx.service import MODEL, create_app

BODY = {"model": MODEL, "messages": [{"role": "user", "content": "private prompt"}], "max_tokens": 2}


class FakeRuntime:
    base = None
    max_context = 3072
    prompt_tokens = output_tokens = 0

    def __init__(self):
        self.entered = threading.Event()
        self.release = threading.Event()
        self.release.set()
        self.failure = None

    def run(self, body, metrics, cancel, admitted):
        self.entered.set()
        while not self.release.wait(.01):
            if cancel.is_set():
                raise GenerationCancelled()
        if self.failure:
            raise self.failure
        self.prompt_tokens, self.output_tokens = 7, 2
        metrics.prompt.inc(7)
        metrics.generated.inc(2)
        metrics.prefill_time.observe(.2)
        metrics.decode_time.observe(.1)
        metrics.cache.set(128)
        metrics.last_cache.set(128)
        metrics.observe_loop({"phase": "decode", "loop": 3, "qkv_rows": 144,
                              "mlp_rows": 48, "next_token_entropy": .1, "hidden_delta_rms": .2})
        return {"content": "answer", "finish_reason": "length", "prompt_tokens": 7, "completion_tokens": 2}


class ServiceTests(unittest.TestCase):
    def test_usage_persists_and_aliases_match(self):
        with TestClient(create_app("unused", runtime=FakeRuntime())) as client:
            self.assertFalse(client.get("/health").json()["model_loaded"])
            for _ in range(2):
                reply = client.post("/v1/chat/completions", json=BODY)
                self.assertEqual(reply.status_code, 200, reply.text)
                self.assertEqual(reply.json()["usage"], {"prompt_tokens": 7, "completion_tokens": 2, "total_tokens": 9})
            text = client.get("/metrics").text
            for expected in ('flashloop_prompt_tokens_total 14.0', 'llamacpp:prompt_tokens_total 14.0',
                             'llamacpp:tokens_predicted_total 4.0', 'llamacpp:prompt_seconds_total 0.4',
                             'flashloop_requests_active 0.0', 'flashloop_cache_bytes 0.0',
                             'flashloop_last_request_cache_bytes 128.0',
                             'flashloop_generation_requests_total{outcome="success"} 2.0',
                             'flashloop_loop_passes_total{loop="3",phase="decode"} 2.0'):
                self.assertIn(expected, text)
            self.assertNotIn("private prompt", text)
            self.assertFalse(client.get("/slots").json()[0]["is_processing"])

    def test_rejections_and_registry_isolation(self):
        for _ in range(2):
            with TestClient(create_app("unused", runtime=FakeRuntime())) as client:
                for changes in ({"stream": True}, {"temperature": .8}, {"max_tokens": 0}, {"tools": []}):
                    self.assertEqual(client.post("/v1/chat/completions", json=BODY | changes).status_code, 422)
                self.assertEqual(client.post("/v1/chat/completions", json=BODY | {"model": "unknown"}).status_code, 400)
                client.get("/private-path-123")
                text = client.get("/metrics").text
                self.assertIn('route="unmatched"', text)
                self.assertNotIn("private-path-123", text)
                self.assertIn("flashloop_generated_tokens_total 0.0", text)

    def test_failure_releases_slot(self):
        runtime = FakeRuntime()
        with TestClient(create_app("unused", runtime=runtime)) as client:
            for failure, status, outcome in ((InputTooLong(), 400, "rejected_context"),
                                             (GenerationCancelled(), 499, "cancelled"),
                                             (RuntimeError("test"), 500, "error")):
                runtime.failure = failure
                with self.assertLogs("experimental.flashloop_mlx.service", level="ERROR") if status == 500 else nullcontext():
                    self.assertEqual(client.post("/v1/chat/completions", json=BODY).status_code, status)
                text = client.get("/metrics").text
                self.assertIn('outcome="' + outcome + '"} 1.0', text)
                self.assertIn("flashloop_requests_active 0.0", text)
            runtime.failure = None
            self.assertEqual(client.post("/v1/chat/completions", json=BODY).status_code, 200)

    def test_live_scrapes_and_busy_admission(self):
        runtime = FakeRuntime()
        runtime.release.clear()
        with TestClient(create_app("unused", runtime=runtime)) as client, ThreadPoolExecutor() as pool:
            future = pool.submit(client.post, "/v1/chat/completions", json=BODY)
            try:
                self.assertTrue(runtime.entered.wait(5))
                self.assertIn("flashloop_requests_active 1.0", client.get("/metrics").text)
                self.assertTrue(client.get("/slots").json()[0]["is_processing"])
                self.assertEqual(client.post("/v1/chat/completions", json=BODY).status_code, 503)
            finally:
                runtime.release.set()
            self.assertEqual(future.result(timeout=5).status_code, 200)


class CancellationTests(unittest.IsolatedAsyncioTestCase):
    async def test_disconnect_event_reaches_worker(self):
        runtime = FakeRuntime()
        runtime.release.clear()
        app = create_app("unused", runtime=runtime)
        incoming = asyncio.Queue()
        await incoming.put({"type": "http.request", "body": json.dumps(BODY).encode(), "more_body": False})
        sent = []

        async def send(message):
            sent.append(message)

        scope = {"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
                 "method": "POST", "scheme": "http", "path": "/v1/chat/completions",
                 "query_string": b"", "headers": [(b"content-type", b"application/json")],
                 "client": ("127.0.0.1", 1), "server": ("127.0.0.1", 80), "root_path": ""}
        async with app.router.lifespan_context(app):
            task = asyncio.create_task(app(scope, incoming.get, send))
            try:
                for _ in range(100):
                    if runtime.entered.is_set():
                        break
                    await asyncio.sleep(.01)
                self.assertTrue(runtime.entered.is_set())
                await incoming.put({"type": "http.disconnect"})
                await asyncio.wait_for(task, timeout=2)
                self.assertEqual(next(m["status"] for m in sent if m["type"] == "http.response.start"), 499)
            finally:
                runtime.release.set()

    async def test_cancelled_client_worker_cleanup(self):
        runtime = FakeRuntime()
        runtime.release.clear()
        app = create_app("unused", runtime=runtime)
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://local") as client:
                request = asyncio.create_task(client.post("/v1/chat/completions", json=BODY))
                for _ in range(100):
                    if runtime.entered.is_set():
                        break
                    await asyncio.sleep(.01)
                self.assertTrue(runtime.entered.is_set())
                request.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await request
                for _ in range(100):
                    text = (await client.get("/metrics")).text
                    if 'outcome="cancelled"} 1.0' in text:
                        break
                    await asyncio.sleep(.01)
                self.assertIn('outcome="cancelled"} 1.0', text)
                self.assertIn('flashloop_requests_active 0.0', text)
                runtime.release.set()
                self.assertEqual((await client.post("/v1/chat/completions", json=BODY)).status_code, 200)
