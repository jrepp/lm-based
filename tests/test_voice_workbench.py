import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import wave

from lm_launcher.voice_workbench import clean_regions, dataset, media_options, number, word_error_rate


def wav(path):
    with wave.open(str(path), 'wb') as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(24000)
        out.writeframes(b'\0\0' * 24000)


class VoiceWorkbenchTests(unittest.TestCase):
    def test_word_error_rate_normalizes_case_and_counts_edits(self):
        self.assertEqual(word_error_rate("This is a test.", "this IS a test"), 0)
        self.assertEqual(word_error_rate("This is a test", "This was a test"), .25)
        self.assertEqual(word_error_rate("one", "one two three"), 2)

    def test_extract_preserves_source_offsets_and_unresolved_roles(self):
        from contextlib import nullcontext
        from types import SimpleNamespace
        from lm_launcher.voice_workbench import extract
        full = {'text': 'hello', 'segments': [{'start': 1., 'end': 2., 'words': [{'word': 'hello', 'start': 1., 'end': 2.}]}]}
        with tempfile.TemporaryDirectory() as directory, \
                patch('lm_launcher.voice_workbench.media', return_value={'path': '/tmp/test.wav', 'end': 720}), \
                patch('lm_launcher.voice_workbench.analyze', return_value={'analysis': '/tmp/analysis.json', 'speakers': {'speaker_0': {}}}), \
                patch('lm_launcher.voice_workbench.gpu_work', return_value=nullcontext()), \
                patch.dict('sys.modules', {'mlx_whisper': SimpleNamespace(transcribe=lambda *a, **k: full)}):
            result = extract({'url': 'https://example.org/video', 'start': 600, 'end': 720, 'language': 'en'}, Path(directory))
            transcript = json.loads(Path(result['transcript']).read_text())
            self.assertEqual(transcript['segments'][0]['source_start'], 601)
            self.assertEqual(transcript['segments'][0]['words'][0]['source_end'], 602)
            self.assertEqual(transcript['segments'][0]['start'], 1)
            roles = json.loads(Path(result['roles']).read_text())
            self.assertEqual(roles['labels']['speaker_0']['status'], 'unresolved')

    def test_overlap_is_excluded_not_assigned_to_one_speaker(self):
        segments = [{'speaker': 'speaker_0', 'start': 0, 'end': 8}, {'speaker': 'speaker_1', 'start': 3, 'end': 5}]
        self.assertEqual(clean_regions(segments, 8), [
            {'speaker': 'speaker_0', 'start': 0., 'end': 3.},
            {'speaker': 'speaker_0', 'start': 5., 'end': 8.},
        ])

    def test_streaming_boundaries_merge_and_long_turns_split(self):
        rows = [{'speaker': 'speaker_0', 'start': 0, 'end': 10}, {'speaker': 'speaker_0', 'start': 10, 'end': 25}]
        self.assertEqual([(r['start'], r['end']) for r in clean_regions(rows, 25)], [(0., 12.), (12., 24.), (24., 25.)])

    def test_url_and_range_validation(self):
        opts = media_options({'url': 'https://www.youtube.com/watch?v=abc', 'end': 30}, Path('/tmp/job'))
        self.assertTrue(opts['noplaylist'])
        self.assertEqual(opts['format'], 'bestaudio/best')
        for request in [{'url': 'file:///etc/passwd'}, {'url': 'https://name:password@example.org'}, {'url': 'https://example.org', 'end': 4000}, {'url': 'https://example.org', 'start': 10, 'end': 5}]:
            with self.assertRaises(ValueError):
                media_options(request, Path('/tmp/job'))
        for value in [float('nan'), float('inf'), True, '5']:
            with self.assertRaises(ValueError):
                number(value, 'number', 0, 10)

    def test_dataset_selection_corrections_and_holdout(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            clips = []
            for index in range(6):
                audio = root / f'{index}.wav'
                wav(audio)
                clips.append({'id': str(index), 'speaker': 'speaker_0' if index < 5 else 'speaker_1', 'audio': str(audio), 'text': 'Original'})
            analysis = root / 'analysis.json'
            analysis.write_text(json.dumps({'clips': clips}))
            request = {'analysis': str(analysis), 'speaker': 'speaker_0', 'clip_ids': [str(i) for i in range(5)], 'transcripts': {'0': 'Corrected'}}
            result = dataset(request, root)
            self.assertEqual(result['training_clips'], 4)
            self.assertEqual(result['validation_clips'], 1)
            rows = [json.loads(line) for line in (root / 'train.jsonl').read_text().splitlines()]
            self.assertEqual(rows[0]['text'], 'Corrected')
            self.assertEqual(len({row['ref_audio'] for row in rows}), 1)
            with self.assertRaisesRegex(ValueError, 'requested speaker'):
                dataset({**request, 'clip_ids': ['5']}, root)
            with self.assertRaisesRegex(ValueError, 'unknown clip_ids'):
                dataset({**request, 'clip_ids': ['missing']}, root)
            merged = dataset({**request, 'speaker': 'reviewed', 'clip_ids': ['0', '5'],
                              'speaker_labels': {'speaker_0': 'reviewed', 'speaker_1': 'reviewed'},
                              'review_note': 'Confirmed by the source owner'}, root)
            self.assertEqual(merged['speaker_labels']['speaker_1'], 'reviewed')
            self.assertEqual(merged['selected_clips'][1]['original_speaker'], 'speaker_1')
            self.assertTrue(merged['selected_clips'][0]['corrected'])
            self.assertEqual(merged['review_note'], 'Confirmed by the source owner')
