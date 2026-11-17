"""Speech client with native macOS playback; no inference dependencies."""
from __future__ import annotations

import argparse
import base64
import json
import os
from pathlib import Path
import platform
import subprocess
import tempfile
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

CUSTOM_MODEL = "qwen3-tts-0.6b-customvoice-8bit"
BASE_MODEL = "qwen3-tts-0.6b-base-8bit"
SPEECH_MODELS = (CUSTOM_MODEL, BASE_MODEL)


def play_audio(path: Path) -> None:
    if platform.system() != "Darwin":
        raise ValueError("native playback requires macOS; use --output to save WAV")
    subprocess.run(["/usr/bin/afplay", str(path.resolve())], check=True)


def main() -> None:
    from lm_launcher.service_endpoints import swap_api_base
    parser = argparse.ArgumentParser(description="Generate Qwen3-TTS speech and optionally play it on macOS")
    parser.add_argument("text", nargs="?")
    parser.add_argument("--model", choices=SPEECH_MODELS)
    parser.add_argument("--list-models", action="store_true")
    parser.add_argument("--endpoint", default=os.getenv("LM_BASED_SPEECH_URL", swap_api_base()))
    parser.add_argument("--voice")
    parser.add_argument("--language", default="English")
    parser.add_argument("--ref-audio", type=Path)
    parser.add_argument("--ref-text")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--play", action="store_true")
    args = parser.parse_args()
    if args.list_models:
        print("\n".join(SPEECH_MODELS))
        return
    if not args.text:
        parser.error("text is required")
    if not args.play and args.output is None:
        parser.error("specify --play or --output")
    model = args.model or (BASE_MODEL if args.ref_audio else CUSTOM_MODEL)
    body = {"model": model, "input": args.text, "response_format": "wav", "language": args.language}
    if args.voice:
        body["voice"] = args.voice
    try:
        if args.ref_audio:
            from lm_launcher.tts_server import MAX_REFERENCE_BYTES
            with args.ref_audio.open("rb") as source:
                reference = source.read(MAX_REFERENCE_BYTES + 1)
            if len(reference) > MAX_REFERENCE_BYTES:
                raise ValueError("reference WAV exceeds 4 MiB")
            body["ref_audio"] = base64.b64encode(reference).decode()
        if args.ref_text:
            body["ref_text"] = args.ref_text
        from lm_launcher.tts_server import generation_args
        generation_args(body, "base" if model == BASE_MODEL else "custom_voice")
        headers = {"Content-Type": "application/json"}
        if os.getenv("LM_TTS_API_KEY"):
            headers["Authorization"] = "Bearer " + os.environ["LM_TTS_API_KEY"]
        request = Request(args.endpoint.rstrip("/") + "/audio/speech", json.dumps(body).encode(), headers)
        with urlopen(request, timeout=300) as response:
            if response.headers.get_content_type() != "audio/wav":
                raise ValueError("speech endpoint did not return WAV audio")
            audio = response.read()
        with tempfile.TemporaryDirectory(prefix="lm-speech-") as directory:
            output = args.output or Path(directory) / "speech.wav"
            output.parent.mkdir(parents=True, exist_ok=True)
            with output.open("xb") as destination:
                destination.write(audio)
            if args.play:
                play_audio(output)
            if args.output:
                print(str(output.resolve()))
    except HTTPError as exc:
        parser.exit(1, f"Speech request failed ({exc.code}): {exc.read(4096).decode(errors='replace')}\n")
    except (OSError, ValueError, URLError, subprocess.CalledProcessError) as exc:
        parser.exit(1, f"Speech failed: {exc}\n")
