"""Run in the speech runtime: uv run --no-project --python 3.13 --with
mlx-audio==0.6.6 --with fastapi --with httpx python -m unittest discover -s tests -p test_tts_api.py
"""
import importlib.util
import io
from types import SimpleNamespace
import unittest
import wave

HAS_RUNTIME = all(importlib.util.find_spec(name) for name in ('numpy', 'fastapi', 'httpx'))


@unittest.skipUnless(HAS_RUNTIME, 'requires optional speech runtime')
class SpeechApiTests(unittest.TestCase):
    def setUp(self):
        import numpy as np
        from fastapi.testclient import TestClient
        from lm_launcher.tts_server import SpeechEngine, create_app
        self.calls = []
        calls = self.calls

        class Model:
            def generate_custom_voice(self, **args):
                calls.append(args)
                for _ in range(2):
                    yield SimpleNamespace(audio=np.array([0., .5, -.5]), sample_rate=24000)

        self.client = TestClient(create_app(SpeechEngine(Model(), 'custom_voice'), 'test-tts', 'secret'))

    def test_health_models_auth_and_multichunk_wav(self):
        self.assertEqual(self.client.get('/health').status_code, 200)
        self.assertEqual(self.client.get('/v1/models').json()['data'][0]['id'], 'test-tts')
        body = {'model': 'test-tts', 'input': 'Hello'}
        self.assertEqual(self.client.post('/v1/audio/speech', json=body).status_code, 401)
        response = self.client.post('/v1/audio/speech', json=body, headers={'Authorization': 'Bearer secret'})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.headers['content-type'], 'audio/wav')
        with wave.open(io.BytesIO(response.content)) as wav:
            self.assertEqual(wav.getnframes(), 6)
            self.assertEqual(wav.getframerate(), 24000)
        self.assertEqual(self.calls[0]['speaker'], 'ryan')

    def test_reject_malformed_and_wrong_model_before_inference(self):
        for body in ([], {'model': 'other', 'input': 'Hello'}, {'model': 'test-tts', 'input': ''}):
            response = self.client.post('/v1/audio/speech', json=body, headers={'Authorization': 'Bearer secret'})
            self.assertEqual(response.status_code, 400)
        self.assertEqual(self.calls, [])
