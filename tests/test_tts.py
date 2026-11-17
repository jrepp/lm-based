from __future__ import annotations

import base64
import importlib.util
import io
import os
from pathlib import Path
import unittest
from unittest.mock import patch
import wave

from lm_launcher.tts_server import build_args, generation_args, reference_wav
from lm_launcher.speech_client import play_audio
from lm_launcher.pi_bootstrap import load_sidecars
from lm_launcher.settings import ServerSettings


def wav_reference(seconds=1):
    output = io.BytesIO()
    with wave.open(output, 'wb') as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(24000)
        wav.writeframes(b'\0\0' * 24000 * seconds)
    return base64.b64encode(output.getvalue()).decode()


class SpeechTests(unittest.TestCase):
    def test_clone_routes_transcript_without_preset(self):
        args, reference = generation_args({'input': 'hello', 'ref_audio': wav_reference(), 'ref_text': 'reference words'}, 'base')
        self.assertEqual(args['ref_text'], 'reference words')
        self.assertNotIn('speaker', args)
        self.assertNotIn('voice', args)
        self.assertTrue(reference.startswith(b'RIFF'))

    def test_invalid_and_conflicting_requests(self):
        for variant, body in [
            ('base', {'input': 'hello'}),
            ('base', {'input': 'hello', 'voice': 'ryan'}),
            ('custom_voice', {'input': 'hello', 'ref_audio': wav_reference()}),
            ('custom_voice', {'input': 'hello', 'voice': 'unknown'}),
            ('custom_voice', {'input': 'hello', 'response_format': 'mp3'}),
            ('custom_voice', {'input': 'hello', 'stream': True}),
            ('custom_voice', {'input': 'hello', 'speed': 2}),
            ('custom_voice', {'input': ' '}),
        ]:
            with self.subTest(body=body), self.assertRaises(ValueError):
                generation_args(body, variant)

    def test_reference_validation(self):
        for data in ['not base64', base64.b64encode(b'not WAV').decode(), wav_reference(31)]:
            with self.assertRaises(ValueError):
                reference_wav(data)

    def test_native_playback_uses_argument_vector(self):
        with patch('platform.system', return_value='Darwin'), patch('subprocess.run') as run:
            play_audio(Path('/tmp/a voice; literal.wav'))
        run.assert_called_once_with(['/usr/bin/afplay', str(Path('/tmp/a voice; literal.wav').resolve())], check=True)

    def test_sidecar_and_launcher(self):
        with patch.dict(os.environ, {}, clear=True):
            settings = ServerSettings(_env_file=None, model_slug='qwen3-tts-0.6b-base-8bit')
        self.assertEqual(settings.profile, 'mlx-qwen3-tts')
        self.assertEqual(load_sidecars()[settings.model_slug].kind, "speech")
        args = build_args(settings)
        self.assertIn('mlx-audio==0.6.6', args)
        self.assertIn(str(settings.model_path.parent), args)
        self.assertNotIn('mlx_lm.server', args)

    def test_dispatch_tts_before_generic_mlx(self):
        spec = importlib.util.spec_from_file_location('tts_run_server_test', Path(__file__).resolve().parents[1] / 'run-server.py')
        for env in [{'MODEL_SLUG': 'qwen3-tts-0.6b-base-8bit'}, {'PROFILE': 'mlx-qwen3-tts'}, {'MODEL_FILE': 'Qwen3-TTS-12Hz-0.6B-Base-8bit/config.json'}]:
            with patch.dict(os.environ, env, clear=True):
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                self.assertEqual(module.select_backend(), 'tts')
