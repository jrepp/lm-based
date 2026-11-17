import array
import importlib.util
import math
from pathlib import Path
import tempfile
import unittest
import wave

from lm_launcher.audio_mix import stitch, extend_pauses


def tone(path, level, rate=24000, frequency=440):
    values = array.array('h', (round(level * 32767 * math.sin(2 * math.pi * frequency * i / rate)) for i in range(rate * 3)))
    with wave.open(str(path), 'wb') as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(rate)
        out.writeframes(values.tobytes())


class MixValidationTests(unittest.TestCase):
    def test_invalid_requests_fail_before_ffmpeg(self):
        for request in ({'paths': []}, {'paths': ['x'], 'gap_ms': float('nan')}, {'paths': ['x'], 'compress': 'yes'}, {'paths': ['x'], 'target_lufs': 0}):
            with self.assertRaises(ValueError):
                stitch(request, Path('/tmp'), '/no/ffmpeg')

    def test_only_existing_interior_pauses_are_extended(self):
        with tempfile.TemporaryDirectory() as directory:
            source, target = Path(directory)/'source.wav', Path(directory)/'target.wav'
            speech = array.array('h', [2000] * 2400).tobytes()
            with wave.open(str(source), 'wb') as out:
                out.setnchannels(1)
                out.setsampwidth(2)
                out.setframerate(24000)
                out.writeframes(b'\0\0' * 4800 + speech + b'\0\0' * 4800 + speech + b'\0\0' * 4800)
            result = extend_pauses(source, target, 400)
            self.assertEqual(result['extended_pauses'], 1)
            self.assertAlmostEqual(result['added_seconds'], .2)
            with wave.open(str(target)) as audio:
                self.assertEqual(audio.getnframes(), 24000)



@unittest.skipUnless(importlib.util.find_spec('imageio_ffmpeg'), 'requires isolated ffmpeg runtime')
class MixIntegrationTests(unittest.TestCase):
    def test_order_gap_leveling_peak_and_source_preservation(self):
        import imageio_ffmpeg
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first, second = root / 'quiet.wav', root / 'loud.wav'
            tone(first, .02, frequency=440)
            tone(second, .5, rate=48000, frequency=880)
            original = first.read_bytes(), second.read_bytes()
            result = stitch({'paths': [str(first), str(second)], 'gap_ms': 200}, root, imageio_ffmpeg.get_ffmpeg_exe())
            self.assertAlmostEqual(result['duration_seconds'], 6.2, places=2)
            self.assertAlmostEqual(result['timeline'][1]['start'], 3.2, places=2)
            with wave.open(result['path']) as wav:
                self.assertEqual((wav.getnchannels(), wav.getframerate(), wav.getsampwidth()), (1, 24000, 2))
                samples = array.array('h', wav.readframes(wav.getnframes()))
            self.assertLessEqual(max(abs(s) for s in samples), 27600)
            def rms(start, end):
                chunk = samples[round(start * 24000):round(end * 24000)]
                return math.sqrt(sum(s*s for s in chunk) / len(chunk))
            self.assertLess(abs(20 * math.log10(rms(.5, 2.5) / rms(3.7, 5.7))), 3)
            self.assertEqual(max(abs(s) for s in samples[72000:76800]), 0)
            def crossings(start, end):
                chunk = samples[round(start * 24000):round(end * 24000)]
                return sum(a <= 0 < b for a, b in zip(chunk, chunk[1:]))
            self.assertGreater(crossings(3.7, 4.7), crossings(.5, 1.5) * 1.8)
            self.assertEqual((first.read_bytes(), second.read_bytes()), original)
            self.assertFalse(list(root.glob('mix-*.wav')))
            self.assertFalse((root / 'stitched.partial.wav').exists())

    def test_silence_is_preserved_without_normalization_errors(self):
        import imageio_ffmpeg
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'silence.wav'
            tone(source, 0)
            result = stitch({'paths': [str(source)]}, root, imageio_ffmpeg.get_ffmpeg_exe())
            self.assertIn('skipped', result['timeline'][0]['loudness_measurement']['note'])
            with wave.open(result['path']) as wav:
                self.assertFalse(any(wav.readframes(wav.getnframes())))
