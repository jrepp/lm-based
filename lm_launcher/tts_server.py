"""Qwen3-TTS on MLX: resident weights, serialized inference, bounded WAV API."""
from __future__ import annotations

import argparse
import base64
import binascii
import io
import json
import os
from pathlib import Path
import platform
import tempfile
import threading
import wave

RUNTIME = "mlx-audio==0.6.6"
MAX_REFERENCE_BYTES = 4 * 1024 * 1024


def reference_wav(value: str) -> bytes:
    try:
        data = base64.b64decode(value, validate=True)
        if len(data) > MAX_REFERENCE_BYTES:
            raise ValueError("reference WAV exceeds 4 MiB")
        with wave.open(io.BytesIO(data)) as wav:
            duration = wav.getnframes() / wav.getframerate()
            if not 1 <= duration <= 30:
                raise ValueError("reference WAV must be 1–30 seconds")
            if wav.getnchannels() != 1 or wav.getsampwidth() != 2:
                raise ValueError("reference WAV must be mono PCM16")
            if len(wav.readframes(wav.getnframes())) != wav.getnframes() * 2:
                raise ValueError("truncated reference WAV")
        return data
    except (binascii.Error, wave.Error, EOFError) as exc:
        raise ValueError("invalid base64 PCM WAV reference") from exc


def generation_args(body: dict, variant: str) -> tuple[dict, bytes | None]:
    text = body.get("input")
    if not isinstance(text, str) or not text.strip() or len(text) > 4000:
        raise ValueError("input must contain 1–4000 characters")
    if body.get("response_format", "wav") != "wav" or body.get("stream", False):
        raise ValueError("only non-streaming WAV output is supported")
    if body.get("speed", 1) != 1:
        raise ValueError("speed must be 1")
    language = body.get("language", "English")
    if language not in {"auto", "English", "Chinese", "German", "Italian", "Portuguese", "Spanish", "Japanese", "Korean", "French", "Russian"}:
        raise ValueError("unsupported language")
    args = {"text": text, "max_tokens": 2048, "verbose": False}
    if variant == "base":
        if body.get("voice") or body.get("instructions"):
            raise ValueError("Base requires a reference voice, not a preset or instructions")
        ref_text = body.get("ref_text")
        if not isinstance(ref_text, str) or not ref_text.strip() or len(ref_text) > 4000:
            raise ValueError("Base requires ref_text containing the reference transcript")
        ref = body.get("ref_audio")
        if not isinstance(ref, str) or len(ref) > MAX_REFERENCE_BYTES * 4 // 3 + 4:
            raise ValueError("Base requires a base64 WAV ref_audio (maximum 4 MiB)")
        args.update(ref_text=ref_text, lang_code=language)
        return args, reference_wav(ref)
    if body.get("ref_audio") or body.get("ref_text"):
        raise ValueError("voice cloning requires the Base model")
    voice = body.get("voice", "ryan")
    if voice not in {"ryan", "aiden", "vivian", "serena", "uncle_fu", "dylan", "eric", "ono_anna", "sohee"}:
        raise ValueError("unknown preset voice")
    if body.get("instructions"):
        raise ValueError("the 0.6B preset model does not support style instructions")
    args.update(speaker=voice, language=language)
    return args, None


class SpeechEngine:
    def __init__(self, model, variant: str):
        self.model = model
        self.variant = variant
        self.lock = threading.Lock()

    def synthesize(self, args: dict, reference: bytes | None) -> bytes:
        import numpy as np
        # MLX model state is shared; concurrent requests must not interleave.
        with self.lock, tempfile.TemporaryDirectory(prefix="lm-tts-") as directory:
            args = dict(args)
            if reference is not None:
                path = Path(directory) / "reference.wav"
                path.write_bytes(reference)
                args["ref_audio"] = str(path)
            generate = self.model.generate if self.variant == "base" else self.model.generate_custom_voice
            output = io.BytesIO()
            rate = None
            with wave.open(output, "wb") as wav:
                wav.setnchannels(1)
                wav.setsampwidth(2)
                for result in generate(**args):
                    if rate is None:
                        rate = result.sample_rate
                        wav.setframerate(rate)
                    elif rate != result.sample_rate:
                        raise RuntimeError("sample rate changed during generation")
                    samples = np.asarray(result.audio).reshape(-1)
                    wav.writeframes((np.clip(samples, -1, 1) * 32767).astype("<i2").tobytes())
                if rate is None:
                    raise RuntimeError("model returned no audio")
            return output.getvalue()


def create_app(engine: SpeechEngine, alias: str, api_key: str | None = None):
    from fastapi import FastAPI, Request
    from fastapi.responses import JSONResponse, Response
    from starlette.concurrency import run_in_threadpool

    app = FastAPI()

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.get("/v1/models")
    def models():
        return {"object": "list", "data": [{"id": alias, "object": "model", "owned_by": "local", "type": "tts"}]}

    # Request is local to this factory; avoid postponed annotation resolution.
    async def speech(request):
        if api_key and request.headers.get("authorization") != f"Bearer {api_key}":
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        data = bytearray()
        async for chunk in request.stream():
            data.extend(chunk)
            if len(data) > 6 * 1024 * 1024:
                return JSONResponse({"error": "request too large"}, status_code=413)
        try:
            body = json.loads(data)
            if not isinstance(body, dict):
                raise ValueError("request must be a JSON object")
            if body.get("model") != alias:
                raise ValueError(f"model must be {alias}")
            args, reference = generation_args(body, engine.variant)
        except (ValueError, TypeError) as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)
        audio = await run_in_threadpool(engine.synthesize, args, reference)
        return Response(audio, media_type="audio/wav")

    speech.__annotations__["request"] = Request
    app.post("/v1/audio/speech")(speech)
    return app


def build_args(settings) -> list[str]:
    return ["uv", "run", "--no-project", "--python", "3.13", "--with", RUNTIME,
            "--with", "fastapi>=0.115,<1", "--with", "uvicorn>=0.34,<1", "python",
            str(Path(__file__).resolve()), "--model", str(settings.model_path.parent),
            "--alias", str(settings.alias), "--host", settings.host, "--port", str(settings.port)]


def main() -> None:
    from lm_launcher.settings import ServerSettings
    settings = ServerSettings()
    if platform.system() != "Darwin" or platform.machine() != "arm64":
        raise SystemExit("Qwen3-TTS MLX requires Apple Silicon macOS")
    if not settings.model_path.is_file():
        raise SystemExit(f"Missing model: {settings.model_path}; run download_model.py first")
    env = os.environ.copy()
    if settings.api_key:
        env["LM_TTS_API_KEY"] = settings.api_key
    os.execvpe("uv", build_args(settings), env)


def serve() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True)
    parser.add_argument("--alias", required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8001)
    args = parser.parse_args()
    from mlx_audio.tts.utils import load_model
    import uvicorn
    config = json.loads((Path(args.model) / "config.json").read_text())
    variant = config.get("tts_model_type")
    if variant not in {"base", "custom_voice"}:
        raise SystemExit(f"Unsupported Qwen3-TTS variant: {variant}")
    model = load_model(args.model)
    uvicorn.run(create_app(SpeechEngine(model, variant), args.alias, os.getenv("LM_TTS_API_KEY")),
                host=args.host, port=args.port)


if __name__ == "__main__":
    serve()
