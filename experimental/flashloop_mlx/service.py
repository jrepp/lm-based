"""Experimental loopback HTTP service with runtime-derived Prometheus metrics."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
import logging
from pathlib import Path
import threading
import time
from typing import Literal
import uuid

from fastapi import FastAPI, HTTPException, Request, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from pydantic import BaseModel, ConfigDict, Field

from .metrics import Metrics
from .runtime import GenerationCancelled, InputTooLong, Runtime

MODEL = "ouro-2.6b-thinking-mlx-flashloop"


class Message(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: Literal["system", "user", "assistant"]
    content: str = Field(max_length=32768)


class Completion(BaseModel):
    model_config = ConfigDict(extra="forbid")
    model: str = MODEL
    messages: list[Message] = Field(min_length=1, max_length=64)
    max_tokens: int = Field(default=128, ge=1, le=1024)
    temperature: Literal[0] = 0
    stream: Literal[False] = False
    enable_thinking: bool = True


class HTTPMetrics:
    """Pass ASGI receive through unchanged so disconnect events reach requests."""

    def __init__(self, app, metrics):
        self.app, self.metrics = app, metrics

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        status = 500

        async def response(message):
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
            await send(message)
        try:
            await self.app(scope, receive, response)
        finally:
            route = scope.get("route")
            method = scope["method"] if scope["method"] in ("GET", "POST") else "other"
            self.metrics.http.labels(method, route.path if route else "unmatched", str(status)).inc()


def create_app(model_path, *, mode="flash", runtime=None):
    runtime = runtime or Runtime(Path(model_path), mode)
    metrics = Metrics(MODEL, mode)
    gate = asyncio.Lock()
    pending = set()
    cancellation = threading.Event()

    @asynccontextmanager
    async def lifespan(app):
        with ThreadPoolExecutor(max_workers=1, thread_name_prefix="flashloop-mlx") as executor:
            app.state.executor = executor
            try:
                yield
            finally:
                cancellation.set()
                if pending:
                    await asyncio.gather(*pending, return_exceptions=True)

    app = FastAPI(lifespan=lifespan)
    app.state.metrics = metrics

    app.add_middleware(HTTPMetrics, metrics=metrics)

    @app.get("/health")
    async def health():
        return {"status": "ok", "backend": "mlx", "mode": mode,
                "model_loaded": runtime.base is not None}

    @app.get("/v1/models")
    async def models():
        return {"object": "list", "data": [{"id": MODEL, "object": "model", "owned_by": "local"}]}

    @app.get("/metrics")
    async def scrape():
        return Response(generate_latest(metrics.registry), headers={"Content-Type": CONTENT_TYPE_LATEST})

    @app.get("/slots")
    async def slots():
        return [{"id": 0, "n_ctx": runtime.max_context, "is_processing": gate.locked(),
                 "n_prompt_tokens": runtime.prompt_tokens,
                 "n_prompt_tokens_processed": runtime.prompt_tokens, "n_prompt_tokens_cache": 0,
                 "next_token": [{"n_decoded": runtime.output_tokens}]}]

    async def generate(body, admitted):
        outcome = "error"
        try:
            result = await asyncio.get_running_loop().run_in_executor(
                app.state.executor, runtime.run, body, metrics, cancellation, admitted)
            outcome = "success"
            return result
        except InputTooLong:
            outcome = "rejected_context"
            raise HTTPException(400, "Prompt plus output exceeds context capacity") from None
        except GenerationCancelled:
            outcome = "cancelled"
            raise HTTPException(499, "Generation cancelled") from None
        except Exception:
            logging.getLogger(__name__).exception("Generation failed")
            raise HTTPException(500, "Generation failed") from None
        finally:
            metrics.requests.labels(outcome).inc()
            metrics.request_time.observe(time.monotonic() - admitted)
            metrics.active.set(0)
            metrics.cache.set(0)
            metrics.context.set(0)
            runtime.prompt_tokens = runtime.output_tokens = 0
            gate.release()

    @app.post("/v1/chat/completions")
    async def completion(body: Completion, request: Request):
        if body.model != MODEL:
            raise HTTPException(400, "Unknown model")
        if gate.locked():
            raise HTTPException(503, "Model is busy", headers={"Retry-After": "1"})
        await gate.acquire()
        cancellation.clear()
        metrics.active.set(1)
        admitted = time.monotonic()
        task = asyncio.create_task(generate(body, admitted))
        pending.add(task)

        def finished(task):
            pending.discard(task)
            if not task.cancelled():
                task.exception()  # Retrieve failures even after the client disconnects.
        task.add_done_callback(finished)
        try:
            while not task.done():
                await asyncio.wait({task}, timeout=.1)
                if await request.is_disconnected():
                    cancellation.set()
                    raise HTTPException(499, "Client disconnected")
            result = task.result()
        except asyncio.CancelledError:
            cancellation.set()
            raise
        return {"id": "chatcmpl-" + uuid.uuid4().hex, "object": "chat.completion",
                "created": int(time.time()), "model": MODEL,
                "choices": [{"index": 0, "message": {"role": "assistant", "content": result["content"]},
                             "finish_reason": result["finish_reason"]}],
                "usage": {"prompt_tokens": result["prompt_tokens"],
                          "completion_tokens": result["completion_tokens"],
                          "total_tokens": result["prompt_tokens"] + result["completion_tokens"]}}
    return app


def main():
    import argparse
    import uvicorn
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("model", type=Path)
    parser.add_argument("--port", type=int, default=19095)
    parser.add_argument("--mode", choices=("flash", "dense"), default="flash")
    args = parser.parse_args()
    uvicorn.run(create_app(args.model, mode=args.mode), host="127.0.0.1", port=args.port, access_log=False, timeout_graceful_shutdown=5)


if __name__ == "__main__":
    main()
