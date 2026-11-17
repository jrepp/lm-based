"""Local media/voice jobs invoked by Pi. Heavy dependencies stay in uv runtimes."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import json
import math
import os
from pathlib import Path
import platform
import re
import signal
import subprocess
import sys
import time
from urllib.parse import urlsplit
from urllib.request import urlopen
import wave

ROOT = Path(__file__).resolve().parents[1]
DIAR_MODEL = 'mlx-community/diar_streaming_sortformer_4spk-v2.1-fp16'
ASR_MODEL = 'mlx-community/whisper-small-mlx'
TRAIN_MODEL = 'mlx-community/Qwen3-TTS-12Hz-0.6B-Base-bf16'
MAX_SECONDS = 3600


def write_json(path: Path, value) -> None:
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n')
    temporary.replace(path)


def progress(output: Path, stage: str, **fields) -> None:
    write_json(output / 'progress.json', {'stage': stage, 'updated_at': time.time(), **fields})


def number(value, name: str, low: float, high: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not low <= value <= high:
        raise ValueError(f'{name} must be between {low} and {high}')
    return value


def identifier(value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r'[a-z0-9][a-z0-9_-]{0,63}', value):
        raise ValueError('name must be 1–64 lowercase letters, digits, underscores or hyphens')
    return value


def media_options(request: dict, output: Path) -> dict:
    url = urlsplit(request['url'])
    if url.scheme not in {'http', 'https'} or not url.hostname or url.username or url.password:
        raise ValueError('url must be an HTTP(S) media URL without credentials')
    mode = request.get('mode', 'audio')
    if mode not in {'info', 'audio', 'video'}:
        raise ValueError('mode must be info, audio or video')
    start = number(request.get('start', 0), 'start', 0, 86400)
    end = request.get('end')
    if end is not None:
        number(end, 'end', start + 0.1, start + MAX_SECONDS)
    return {
        'noplaylist': True, 'playlistend': 1, 'skip_download': mode == 'info',
        'format': 'bestaudio/best' if mode != 'video' else 'best[height<=720][vcodec!=none][acodec!=none]/best[vcodec!=none][acodec!=none]',
        'outtmpl': str(output / 'source.%(ext)s'), 'overwrites': False,
        'max_filesize': 1024 * 1024 * 1024, 'retries': 3, 'fragment_retries': 3,
        'socket_timeout': 30, 'quiet': True, 'noprogress': True,
        'cachedir': False, 'js_runtimes': {'node': {}},
    }


def ffmpeg() -> str:
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


def convert_audio(source: Path, output: Path, start=0, end=None, rate=24000) -> None:
    args = [ffmpeg(), '-nostdin', '-v', 'error', '-n', '-ss', str(start), '-i', str(source)]
    if end is not None:
        args += ['-t', str(end - start)]
    args += ['-vn', '-ac', '1', '-ar', str(rate), '-c:a', 'pcm_s16le', str(output)]
    subprocess.run(args, check=True, timeout=600)


def media(request: dict, output: Path) -> dict:
    import yt_dlp
    progress(output, 'inspecting_media')
    options = media_options(request, output)
    mode = request.get('mode', 'audio')
    options['ffmpeg_location'] = ffmpeg()
    # yt-dlp's section downloader checks ffmpeg on PATH independently of
    # ffmpeg_location. Supply a job-local shim for the bundled executable.
    binaries = output / 'bin'
    binaries.mkdir(exist_ok=True)
    (binaries / 'ffmpeg').symlink_to(options['ffmpeg_location'])
    os.environ['PATH'] = str(binaries) + os.pathsep + os.environ.get('PATH', '')
    with yt_dlp.YoutubeDL(options) as ydl:
        info = ydl.extract_info(request['url'], download=False)
        if not info or info.get('_type') in {'playlist', 'multi_video'} or info.get('entries') is not None:
            raise ValueError('provide one video URL, not a playlist')
        if info.get('is_live'):
            raise ValueError('live streams are not supported; use a finished video')
        duration = info.get('duration')
        summary = {key: info.get(key) for key in ('id', 'title', 'webpage_url', 'duration', 'uploader')}
        if mode == 'info':
            write_json(output / 'media.json', summary)
            return summary
        if not isinstance(duration, (int, float)) or duration <= 0:
            raise ValueError('media duration is unavailable; cannot bound this download')
        start = request.get('start', 0)
        end = min(request.get('end', duration), duration)
        number(end - start, 'selected duration', .1, MAX_SECONDS)
        # Bound the downloaded interval as well as the output file.
        if start or end < duration:
            from yt_dlp.utils import download_range_func
            ydl.params.update(download_ranges=download_range_func(None, [(start, end)]), ffmpeg_location=ffmpeg())
        progress(output, 'downloading')
        ydl.extract_info(request['url'], download=True)
        files = [p for p in output.glob('source.*') if p.suffix not in {'.part', '.ytdl'} and p.is_file()]
        if len(files) != 1:
            raise RuntimeError('download did not produce exactly one media file')
        source = files[0]
        if mode == 'audio':
            target = output / 'audio.wav'
            convert_audio(source, target, end=end - start)
            source.unlink()  # Only this job's intermediate download.
        else:
            target = source
        summary.update(path=str(target), mode=mode, start=start, end=end)
        write_json(output / 'media.json', summary)
        return summary


def clean_regions(segments: list[dict], duration: float, min_seconds=1.0, max_seconds=12.0) -> list[dict]:
    """Sweep activity intervals, keeping only exactly one active speaker."""
    events: dict[float, list[tuple[str, int]]] = {}
    for item in segments:
        start = max(0., number(item['start'], 'segment start', 0, duration + 1))
        end = min(duration, number(item['end'], 'segment end', start, duration + 1))
        if end <= start:
            continue
        speaker = identifier(str(item['speaker']))
        events.setdefault(start, []).append((speaker, 1))
        events.setdefault(end, []).append((speaker, -1))
    active: dict[str, int] = {}
    pieces: list[dict] = []
    previous = 0.
    for point in sorted(events):
        speakers = [key for key, value in active.items() if value > 0]
        if len(speakers) == 1 and point > previous:
            speaker = speakers[0]
            if pieces and pieces[-1]['speaker'] == speaker and abs(pieces[-1]['end'] - previous) < 1e-6:
                pieces[-1]['end'] = point
            else:
                pieces.append({'start': previous, 'end': point, 'speaker': speaker})
        for speaker, delta in events[point]:
            active[speaker] = active.get(speaker, 0) + delta
        previous = point
    result = []
    for piece in pieces:
        start = piece['start']
        while piece['end'] - start >= min_seconds:
            end = min(piece['end'], start + max_seconds)
            result.append({**piece, 'start': round(start, 4), 'end': round(end, 4)})
            start = end
    return result


@contextmanager
def gpu_work(min_free_gb=8):
    if platform.system() != 'Darwin' or platform.machine() != 'arm64':
        raise ValueError('MLX voice work requires Apple Silicon macOS')
    import fcntl
    directory = Path(os.environ.get('LM_VOICE_WORKBENCH_ROOT', str(ROOT / '.runtime' / 'voice-workbench')))
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / 'gpu.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ValueError('another voice analysis/training job is using the GPU; wait for it') from exc
        pressure = subprocess.check_output(['/usr/bin/memory_pressure'], text=True, timeout=15)
        match = re.search(r'System-wide memory free percentage: (\d+)%', pressure)
        total = int(subprocess.check_output(['/usr/sbin/sysctl', '-n', 'hw.memsize'], text=True))
        if not match or total * int(match[1]) / 100 < min_free_gb * 1024**3:
            raise ValueError(f'insufficient available memory (need {min_free_gb} GiB); no services were stopped')
        try:
            with urlopen('http://127.0.0.1:8081/running', timeout=2) as response:
                print('llama-swap running:', response.read(65536).decode(), flush=True)
        except OSError:
            print('llama-swap /running unavailable; system-wide memory check passed', flush=True)
        yield


def analyze(request: dict, output: Path) -> dict:
    import gc
    import soundfile as sf
    import mlx.core as mx
    source = Path(request['path']).expanduser().resolve(strict=True)
    normalized = output / 'analysis.wav'
    # Enforce a duration limit before model loading; never truncate silently.
    convert_audio(source, normalized, end=MAX_SECONDS + 1, rate=16000)
    waveform, rate = sf.read(normalized, dtype='float32')
    duration = len(waveform) / rate
    if duration > MAX_SECONDS:
        raise ValueError('analyze at most one hour at a time; select a shorter download interval')
    if duration < 1:
        raise ValueError('audio is shorter than one second')
    with gpu_work():
        from mlx_audio.vad import load
        progress(output, 'loading_diarization')
        print('Loading speaker diarization model', flush=True)
        model = load(DIAR_MODEL)
        segments = []
        for batch in model.generate_stream(waveform, sample_rate=rate, chunk_duration=10., min_duration=.25):
            segments.extend({'start': float(s.start), 'end': float(s.end), 'speaker': f'speaker_{s.speaker}'} for s in batch.segments)
            progress(output, 'diarizing', segments=len(segments))
            print(f'Diarization: {len(segments)} segments', flush=True)
        del model
        gc.collect()
        mx.clear_cache()
        regions = clean_regions(segments, duration)
        if not regions:
            raise ValueError('no clean single-speaker speech found')
        if len(regions) > 1000:
            raise ValueError('more than 1000 clips; analyze a shorter interval')
        import mlx_whisper
        print('Loading transcription model', flush=True)
        clips = []
        for index, region in enumerate(regions):
            clip = output / f'{index:04d}.wav'
            data = waveform[round(region['start'] * rate):round(region['end'] * rate)]
            # Write 24 kHz PCM16 references compatible with clone_voice and training.
            from scipy.signal import resample_poly
            sf.write(clip, resample_poly(data, 3, 2), 24000, subtype='PCM_16')
            result = mlx_whisper.transcribe(data, path_or_hf_repo=ASR_MODEL, language=request.get('language'), verbose=False)
            text = result['text'].strip()
            clips.append({**region, 'id': f'clip_{index:04d}', 'audio': str(clip), 'text': text, 'transcript_status': 'automatic'})
            progress(output, 'transcribing', completed=index + 1, total=len(regions))
            print(f'Transcribed {index + 1}/{len(regions)}', flush=True)
    analysis = {'source': str(source), 'duration': duration, 'diarization_model': DIAR_MODEL, 'asr_model': ASR_MODEL,
                'segments': segments, 'clips': clips, 'note': 'Automatic labels/transcripts require review; overlaps excluded, not separated.'}
    write_json(output / 'analysis.json', analysis)
    speakers = {}
    for clip in clips:
        item = speakers.setdefault(clip['speaker'], {'clips': 0, 'seconds': 0., 'examples': []})
        item['clips'] += 1
        item['seconds'] += clip['end'] - clip['start']
        if len(item['examples']) < 3:
            item['examples'].append({'id': clip['id'], 'text': clip['text'], 'audio': clip['audio']})
    return {'analysis': str(output / 'analysis.json'), 'speakers': speakers, 'note': analysis['note']}


def dataset(request: dict, output: Path) -> dict:
    source = Path(request['analysis']).resolve(strict=True)
    analysis = json.loads(source.read_text())
    speaker = identifier(request['speaker'])
    chosen = set(request['clip_ids'])
    if not chosen:
        raise ValueError('select reviewed clip_ids for one speaker')
    known = {c['id']: c for c in analysis['clips']}
    if chosen - known.keys():
        raise ValueError('unknown clip_ids')
    corrections = request.get('transcripts', {})
    labels = request.get('speaker_labels', {})
    if not isinstance(labels, dict) or any(identifier(k) != k or identifier(v) != v for k, v in labels.items()):
        raise ValueError('speaker_labels must map original labels to reviewed speaker names')
    records = []
    for name in sorted(chosen):
        clip = known[name]
        if labels.get(clip['speaker'], clip['speaker']) != speaker:
            raise ValueError('all selected clips must belong to the requested speaker')
        text = corrections.get(name, clip['text'])
        if not isinstance(text, str) or not text.strip() or len(text) > 4000:
            raise ValueError(f'{name}: empty or oversized transcript; correct it first')
        audio = Path(clip['audio']).resolve(strict=True)
        with wave.open(str(audio)) as wav:
            duration = wav.getnframes() / wav.getframerate()
            if wav.getnchannels() != 1 or wav.getsampwidth() != 2 or not 1 <= duration <= 30:
                raise ValueError(f'{name}: invalid reference WAV')
        records.append({'audio': str(audio), 'text': text.strip(), 'duration': duration, 'clip_id': name, 'original_speaker': clip['speaker'], 'original_text': clip['text'], 'corrected': name in corrections})
    # Fixed held-out set for any dataset large enough to evaluate separately.
    heldout = max(1, len(records) // 10) if len(records) >= 5 else 0
    train, validation = (records[:-heldout], records[-heldout:]) if heldout else (records, [])
    reference = max(train, key=lambda r: r['duration'])['audio']
    for filename, rows in [('train.jsonl', train), ('validation.jsonl', validation)]:
        (output / filename).write_text(''.join(json.dumps({'audio': r['audio'], 'text': r['text'], 'ref_audio': reference}, ensure_ascii=False) + '\n' for r in rows))
    result = {'dataset': str(output / 'dataset.json'), 'speaker': speaker, 'analysis': str(source), 'train': str(output / 'train.jsonl'), 'validation': str(output / 'validation.jsonl'),
              'reference': reference, 'speaker_labels': labels, 'review_note': request.get('review_note'), 'selected_clips': records, 'training_clips': len(train), 'validation_clips': len(validation), 'seconds': sum(r['duration'] for r in records)}
    write_json(output / 'dataset.json', result)
    return result


def train(request: dict, output: Path) -> dict:
    speaker = identifier(request['name'])
    metadata = json.loads(Path(request['dataset']).resolve(strict=True).read_text())
    epochs = int(number(request.get('epochs', 3), 'epochs', 1, 10))
    training = Path(metadata['train']).resolve(strict=True)
    records = [json.loads(line) for line in training.read_text().splitlines() if line.strip()]
    if len(records) < 2:
        raise ValueError('training requires at least two selected clips; use reference cloning for one clip')
    with gpu_work(12):
        from qwen_tts.prepare_data import PrepareConfig, run_prepare
        from qwen_tts.train import TrainConfig, run_training
        encoded = output / 'encoded.jsonl'
        progress(output, 'encoding_training_audio')
        run_prepare(PrepareConfig(data=str(training), output=str(encoded), model_id=TRAIN_MODEL))
        import gc
        import mlx.core as mx
        gc.collect()
        mx.clear_cache()
        checkpoint = output / 'checkpoint'
        progress(output, 'training', epochs=epochs)
        run_training(TrainConfig(data=str(encoded), name=speaker, output=str(checkpoint), model_id=TRAIN_MODEL,
                                 epochs=epochs, batch_size=1, lr=2e-5, grad_accum=4, lora_rank=8))
    result = {'voice': str(output / 'trained-voice.json'), 'name': speaker, 'model': str(checkpoint), 'dataset': request['dataset'], 'epochs': epochs,
              'note': 'Trained checkpoint; evaluate new and held-out sentences with voice_render before adopting.'}
    write_json(output / 'trained-voice.json', result)
    return result


def render(request: dict, output: Path) -> dict:
    from mlx_audio.tts.utils import load_model
    import soundfile as sf
    import numpy as np
    text = request['text']
    if not isinstance(text, str) or not text.strip() or len(text) > 4000:
        raise ValueError('text must contain 1–4000 characters')
    metadata = json.loads(Path(request['voice']).resolve(strict=True).read_text())
    with gpu_work():
        model = load_model(metadata['model'])
        chunks, rate = [], None
        for result in model.generate_custom_voice(text=text, speaker=metadata['name'], language=request.get('language', 'English'), max_tokens=2048):
            if rate is not None and rate != result.sample_rate:
                raise ValueError('inconsistent sample rate')
            rate = result.sample_rate
            chunks.append(np.asarray(result.audio).reshape(-1))
        if not chunks:
            raise ValueError('model generated no audio')
        audio = output / 'speech.wav'
        sf.write(audio, np.concatenate(chunks), rate, subtype='PCM_16')
    if request.get('play', False):
        subprocess.run(['/usr/bin/afplay', str(audio)], check=True)
    return {'path': str(audio), 'name': metadata['name'], 'text': text}


def word_error_rate(expected: str, actual: str) -> float:
    reference = re.findall(r"\w+", expected.casefold())
    hypothesis = re.findall(r"\w+", actual.casefold())
    if not reference:
        raise ValueError('expected text must contain words')
    previous = list(range(len(hypothesis) + 1))
    for index, word in enumerate(reference, 1):
        current = [index]
        for column, other in enumerate(hypothesis, 1):
            current.append(min(previous[column] + 1, current[-1] + 1, previous[column - 1] + (word != other)))
        previous = current
    return previous[-1] / len(reference)


def evaluate(request: dict, output: Path) -> dict:
    import mlx_whisper
    import soundfile as sf
    expected = request['expected_text']
    if not isinstance(expected, str) or not expected.strip() or len(expected) > 4000:
        raise ValueError('expected_text must contain 1–4000 characters')
    source = Path(request['path']).resolve(strict=True)
    normalized = output / 'evaluation.wav'
    convert_audio(source, normalized, end=MAX_SECONDS + 1, rate=16000)
    waveform, rate = sf.read(normalized, dtype='float32')
    if len(waveform) / rate > MAX_SECONDS:
        raise ValueError('evaluation is limited to one hour')
    with gpu_work():
        transcription = mlx_whisper.transcribe(waveform, path_or_hf_repo=ASR_MODEL, language=request.get('language'), verbose=False)['text'].strip()
    result = {'source': str(source), 'expected_text': expected, 'transcript': transcription,
              'word_error_rate': word_error_rate(expected, transcription),
              'note': 'ASR-based intelligibility proxy only; speaker similarity and subjective quality are not measured.'}
    write_json(output / 'evaluation.json', result)
    return result


def extract(request: dict, output: Path) -> dict:
    """One durable, bounded video chunk: download, diarize, and full-context transcript."""
    start = number(request.get('start', 0), 'start', 0, 86400)
    end = number(request['end'], 'end', start + .1, start + MAX_SECONDS)
    media_dir, analysis_dir = output / 'media', output / 'analysis'
    media_dir.mkdir()
    analysis_dir.mkdir()
    progress(output, 'downloading_chunk', source_start=start, source_end=end)
    downloaded = media({**request, 'mode': 'audio'}, media_dir)
    progress(output, 'analyzing_chunk', source_start=start, source_end=end)
    analyzed = analyze({'path': downloaded['path'], 'language': request.get('language')}, analysis_dir)
    # Preserve dialogue context, including turns omitted from single-speaker training clips.
    progress(output, 'transcribing_context', source_start=start, source_end=end)
    import mlx_whisper
    with gpu_work():
        full = mlx_whisper.transcribe(str(analysis_dir / 'analysis.wav'), path_or_hf_repo=ASR_MODEL,
                                    language=request.get('language'), word_timestamps=True, verbose=False)
    for segment in full.get('segments', []):
        segment['source_start'] = start + segment['start']
        segment['source_end'] = start + segment['end']
        for word in segment.get('words', []):
            word['source_start'] = start + word['start']
            word['source_end'] = start + word['end']
    full.update(source_url=request['url'], source_start=start, source_end=downloaded['end'],
                note='Automatic transcript. Local timestamps plus source_start/source_end preserve full-recording offsets.')
    transcript = output / 'transcript.json'
    write_json(transcript, full)
    review = output / 'roles.json'
    write_json(review, {'source_url': request['url'], 'source_start': start, 'source_end': downloaded['end'],
                        'labels': {speaker: {'actor': None, 'character': None, 'status': 'unresolved', 'evidence': []}
                                   for speaker in analyzed['speakers']},
                        'note': 'Labels are local to this chunk, not identities. Use dialogue, credits, source timestamps and listening to review actor/character assignments. One actor may voice multiple characters; one label may contain multiple roles. Do not merge chunk labels by number.'})
    return {'media': downloaded, **analyzed, 'transcript': str(transcript), 'roles': str(review),
            'source_start': start, 'source_end': downloaded['end']}


def stitch(request: dict, output: Path) -> dict:
    from lm_launcher.audio_mix import stitch as assemble
    return assemble(request, output, ffmpeg(), progress)


ACTIONS = {'extract': extract, 'stitch': stitch, 'media': media, 'analyze': analyze, 'dataset': dataset, 'train': train, 'render': render, 'evaluate': evaluate}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--job', type=Path, required=True)
    args = parser.parse_args()
    job = args.job.resolve(strict=True)
    request = json.loads((job / 'request.json').read_text())
    status = {'state': 'running', 'kind': request['kind'], 'pid': os.getpid(), 'started_at': time.time()}
    write_json(job / 'status.json', status)

    def cancel(_signum, _frame):
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, cancel)
    try:
        progress(job, request['kind'])
        result = ACTIONS[request['kind']](request, job)
        progress(job, 'completed')
        status.update(state='completed', result=result)
    except KeyboardInterrupt:
        status.update(state='cancelled')
    except Exception as exc:
        import traceback
        traceback.print_exc()
        status.update(state='failed', error=str(exc))
    finally:
        status['finished_at'] = time.time()
        write_json(job / 'status.json', status)
    if status['state'] != 'completed':
        raise SystemExit(130 if status['state'] == 'cancelled' else 1)


if __name__ == '__main__':
    main()
