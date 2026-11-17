"""Bounded WAV assembly with per-clip dynamics and two-pass loudness normalization."""
from __future__ import annotations

import array
import json
import math
from pathlib import Path
import subprocess
import wave

RATE = 24000


def bounded(value, name, low, high):
    if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value) or not low <= value <= high:
        raise ValueError(f'{name} must be between {low} and {high}')
    return value


def extend_pauses(source: Path, target: Path, minimum_ms: float) -> dict:
    """Extend existing >=120 ms quiet runs; never invent arbitrary word boundaries."""
    inserted = count = 0
    with wave.open(str(source)) as audio, wave.open(str(target), 'wb') as out:
        out.setparams(audio.getparams())
        block_frames = round(RATE * .02)
        quiet = bytearray()
        heard_speech = False
        while block := audio.readframes(block_frames):
            samples = array.array('h', block)
            is_quiet = max((abs(v) for v in samples), default=0) < 328
            if is_quiet:
                quiet.extend(block)
                continue
            if quiet:
                frames = len(quiet) // 2
                extra = max(0, round(RATE * minimum_ms / 1000) - frames) if heard_speech and frames >= RATE * .12 else 0
                midpoint = (frames // 2) * 2
                out.writeframesraw(quiet[:midpoint])
                out.writeframesraw(b'\0\0' * extra)
                out.writeframesraw(quiet[midpoint:])
                inserted += extra
                count += bool(extra)
                quiet.clear()
            out.writeframesraw(block)
            heard_speech = True
        out.writeframesraw(quiet)  # Do not pad leading/trailing silence.
    return {'extended_pauses': count, 'added_seconds': inserted / RATE}


def stitch(request, output: Path, ffmpeg: str, progress=lambda *a, **k: None):
    paths = request.get('paths')
    if not isinstance(paths, list) or not 1 <= len(paths) <= 64 or any(not isinstance(p, str) for p in paths):
        raise ValueError('paths must contain 1–64 local WAV paths, in playback order')
    speed = bounded(request.get('speed', 1), 'speed', .75, 1.25)
    minimum_pause = bounded(request.get('min_pause_ms', 0), 'min_pause_ms', 0, 800)
    gap = bounded(request.get('gap_ms', 180), 'gap_ms', 0, 5000)
    target = bounded(request.get('target_lufs', -16), 'target_lufs', -30, -10)
    compress = request.get('compress', True)
    normalize = request.get('normalize', True)
    if not isinstance(compress, bool) or not isinstance(normalize, bool):
        raise ValueError('compress and normalize must be boolean')
    sources, seconds = [], 0.
    for value in paths:
        source = Path(value).expanduser().resolve(strict=True)
        if not source.is_file():
            raise ValueError('input must be a regular WAV file')
        # Validate before decoding; refuse very large or unbounded inputs.
        if source.stat().st_size > 512 * 1024**2:
            raise ValueError('each input must be at most 512 MiB')
        with wave.open(str(source)) as wav:
            duration = wav.getnframes() / wav.getframerate()
            if duration <= 0 or wav.getsampwidth() not in (1, 2, 3, 4):
                raise ValueError('input must contain PCM WAV audio')
            if wav.getnframes() * wav.getnchannels() * wav.getsampwidth() > source.stat().st_size:
                raise ValueError('truncated input WAV')
        seconds += duration
        sources.append(source)
    if seconds / speed + gap * (len(sources) - 1) / 1000 > 3600:
        raise ValueError('assembled audio is limited to one hour')
    compressor = 'acompressor=threshold=0.125:ratio=3:attack=20:release=250:makeup=1'
    timeline = []
    target_path = output / 'stitched.wav'
    temporary = output / 'stitched.partial.wav'
    try:
        with wave.open(str(temporary), 'wb') as assembled:
            assembled.setnchannels(1)
            assembled.setsampwidth(2)
            assembled.setframerate(RATE)
            for index, source in enumerate(sources):
                progress(output, 'mixing', completed=index, total=len(sources))
                filters = ['aresample=24000', 'aformat=channel_layouts=mono', f'atempo={speed}']
                if compress:
                    filters.append(compressor)
                measured = None
                if normalize:
                    probe = subprocess.run([ffmpeg, '-nostdin', '-hide_banner', '-i', str(source), '-vn', '-af',
                                            ','.join(filters + [f'loudnorm=I={target}:TP=-1.5:LRA=11:print_format=json']),
                                            '-f', 'null', '-'], capture_output=True, text=True, check=True, timeout=600)
                    start, end = probe.stderr.rfind('{'), probe.stderr.rfind('}')
                    if start < 0 or end < start:
                        raise ValueError('ffmpeg did not return loudness measurements')
                    measured = json.loads(probe.stderr[start:end + 1])
                    keys = ('input_i', 'input_tp', 'input_lra', 'input_thresh', 'target_offset')
                    if all(math.isfinite(float(measured[key])) for key in keys):
                        filters.append(f"loudnorm=I={target}:TP=-1.5:LRA=11:measured_I={measured['input_i']}:measured_TP={measured['input_tp']}:measured_LRA={measured['input_lra']}:measured_thresh={measured['input_thresh']}:offset={measured['target_offset']}:linear=true")
                    else:
                        # Silence cannot be loudness-normalized. Preserve it, don't amplify noise.
                        measured = {'note': 'not measurable; loudness normalization skipped'}
                # Safety ceiling with no automatic makeup gain, also when normalization is disabled.
                filters.append('alimiter=limit=0.841395:level=false:latency=true')
                clip = output / f'mix-{index:04d}.wav'
                try:
                    subprocess.run([ffmpeg, '-nostdin', '-hide_banner', '-v', 'error', '-n', '-i', str(source),
                                    '-vn', '-af', ','.join(filters), '-ac', '1', '-ar', str(RATE), '-c:a', 'pcm_s16le', str(clip)],
                                   check=True, timeout=600)
                    pause_stats = {'extended_pauses': 0, 'added_seconds': 0}
                    padded = output / f'pause-{index:04d}.wav'
                    if minimum_pause:
                        try:
                            pause_stats = extend_pauses(clip, padded, minimum_pause)
                            padded.replace(clip)
                        finally:
                            padded.unlink(missing_ok=True)
                    start_frame = assembled.getnframes()
                    with wave.open(str(clip)) as audio:
                        frames = audio.getnframes()
                        if (start_frame + frames) / RATE > 3600:
                            raise ValueError('paced output exceeds one hour')
                        while data := audio.readframes(8192):
                            assembled.writeframesraw(data)
                    timeline.append({'source': str(source), 'start': start_frame / RATE,
                                     'end': (start_frame + frames) / RATE, **pause_stats, 'loudness_measurement': measured})
                    if index < len(sources) - 1:
                        assembled.writeframesraw(b'\0\0' * round(RATE * gap / 1000))
                finally:
                    clip.unlink(missing_ok=True)
        temporary.replace(target_path)
    finally:
        temporary.unlink(missing_ok=True)
    result = {'path': str(target_path), 'sample_rate': RATE, 'channels': 1, 'format': 'PCM16 WAV',
              'compress': compress, 'normalize': normalize, 'speed': speed, 'min_pause_ms': minimum_pause, 'target_lufs': target if normalize else None,
              'peak_ceiling_dbfs': -1.5, 'gap_ms': gap, 'duration_seconds': timeline[-1]['end'], 'timeline': timeline}
    (output / 'mix.json').write_text(json.dumps(result, indent=2) + '\n')
    return result
