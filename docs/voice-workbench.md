# Pi video-to-voice workbench

The selected Pi chat/reasoning model drives a set of local tools. Give Pi a video
URL and an objective, such as:

```text
Download the first five minutes of this video as WAV. Identify the speakers,
transcribe their clean clips, and prepare a dataset for speaker 0. Review the
transcripts, fine-tune a voice named interview-voice, then generate a new sentence
for evaluation: <video URL>
```

Start the managed queue with `./up voice-jobs --add`, then launch with `./pi-local` and select your preferred tool-capable reasoning model
through `/model`. The extension adds workflow instructions to that model's system
prompt; it does not replace the chat model or start another reasoning server.
Existing Pi sessions need restarting to load newly registered extensions.

## Tools

| Tool | Input | Result |
| --- | --- | --- |
| `media_download` | URL; mode `info`, `audio` or `video`; optional start/end seconds | Metadata, mono 24 kHz PCM16 WAV, or video |
| `media_extract` | URL, start/end seconds, optional language | Durable chunk download, diarization, full-context transcript and role-review sheet |
| `voice_analyze` | Local audio path; optional language code | Speaker-labelled clips, timestamps, automatic transcripts, analysis JSON |
| `voice_dataset` | Analysis JSON, one speaker, selected clip IDs, optional transcript corrections | Training and validation JSONL with a consistent reference clip |
| `voice_train` | Dataset JSON, voice name, 1–10 epochs | New Qwen3-TTS CustomVoice checkpoint and trained-voice JSON |
| `voice_render` | Trained-voice JSON, new text, optional playback | WAV using the trained checkpoint |
| `voice_evaluate` | Generated WAV and expected text | Local ASR transcript and word error rate; does not measure speaker similarity |
| `voice_job` | Job ID; optional cancel | Status, structured progress, result paths, recent logs, or cancellation |
| `audio_stitch` | Ordered WAV paths, optional gaps/compression/loudness | Leveled, stitched WAV and source timeline |
| `voice_library` | `voices`, `jobs`, `health`, or `cleanup`; optional `dry_run` | Indexed voices, recent jobs, service status, or retention plan |

All workbench actions submit to the local managed service and return queued job IDs. Wait for `voice_job` to report
`completed` before using outputs. A failed download or training run is reported as
`failed` with its error and recent log. Cancellation goes through the service to its owned worker. Jobs continue when the initiating tool call returns or Pi exits. See [job service operations](voice-job-service.md) for lifecycle, indexing, and cleanup.

Jobs and outputs live under `.runtime/voice-workbench/jobs/`, outside tracked files
and `runs/`. No existing serving process is stopped or reconfigured. Model-heavy
jobs check system-wide free memory and acquire a workbench GPU lock; the service runs one job at a time and waits when an existing workbench GPU job holds the lock. Other model servers still
share this Mac's memory, so these checks do not reserve memory globally.

## Media and speaker processing

The downloader embeds the pinned yt-dlp Python package and uses a bundled ffmpeg
binary via `imageio-ffmpeg`; a system ffmpeg install is not needed. It handles one
finished video at a time, with at most a one-hour selected interval. Video mode
prefers a combined audio/video format up to 720p and falls back to a combined
format if that is unavailable. Available formats, network restrictions, deleted
videos, and site changes can cause downloads to fail. The tool does not expose
browser cookies, arbitrary yt-dlp flags, or playlist downloads.

Sortformer v2.1 identifies up to four speakers, labelled by number rather than real
identity. Overlapping speech is excluded, not acoustically separated. Clean turns
are split into 1–12 second clips and transcribed locally with Whisper Small.
Boundaries, speaker assignments, and transcripts are automatic estimates: Pi
should read `analysis.json`, select appropriate clips, and correct transcripts.
Long turns may be split mid-sentence; reject incomplete clips when preparing data.

`voice_dataset` accepts explicit clip IDs for one speaker. Optional `speaker_labels` maps provisional labels to reviewed names, allowing confirmed fragments of one speaker to be merged. `review_note`, original labels/transcripts, and corrections are retained in the dataset manifest. It reserves about 10%
for validation when at least five clips are selected; smaller sets have no held-out
split. The reference recording comes from the training subset. Two clips are enough
to exercise training, not enough to establish voice quality. For useful fine-tuning,
collect varied, clean speech and evaluate sentences outside the training set.

For a quick voice clone without training, use an extracted clip and its corrected
transcript with `clone_voice`, then `speak`. See [Qwen3-TTS](qwen3-tts.md).

## Runtimes and training

Runtime packages are installed in isolated uv environments on first use; model
weights are cached locally by Hugging Face. No cloud inference or external judge
is used. Dependencies and model downloads initially require network access.

- Media/analysis/render: Python 3.13, MLX Audio 0.6.6, SoundFile 0.13.1,
  imageio-ffmpeg 0.6.0; yt-dlp 2026.10.26 for downloads and mlx-whisper 0.4.3 for ASR.
- Training: Python 3.12, MLX Audio 0.3.1, mlx-lm 0.30.5, and the community
  [qwen-tts trainer](https://github.com/hewliyang/qwen-tts) pinned at
  `6c674c28c0426021df2d459f2b08de1b77b0813c`. Its dependency set uses a Transformers
  prerelease, resolved in the training environment only.
- Training base: `mlx-community/Qwen3-TTS-12Hz-0.6B-Base-bf16`.
- Diarization: `mlx-community/diar_streaming_sortformer_4spk-v2.1-fp16`.
- ASR: `mlx-community/whisper-small-mlx`.

Training uses LoRA rank 8, batch size 1, gradient accumulation 4, learning rate
`2e-5`, and three epochs by default. It exports merged weights into a **new** job
checkpoint directory; the base weights remain unchanged. Use `voice_render` to
load that checkpoint in an isolated process and optionally play it via macOS
`afplay`. Completed checkpoints are automatically indexed by the service. `voice_library` lists their IDs and names; `voice_render` accepts either (use the ID when names collide). They are not added to llama-swap's live configuration or the saved-reference `/speech-voice` menu.

Sortformer **v2.1** uses the [NVIDIA Open Model License](https://www.nvidia.com/en-us/agreements/enterprise-software/nvidia-open-model-license/),
which permits commercial use subject to its terms. Earlier v1 weights have a
noncommercial license; this pipeline does not use them. Dependency and source-media
licenses remain separate. Upstream: [yt-dlp](https://github.com/yt-dlp/yt-dlp),
[Sortformer v2.1](https://huggingface.co/nvidia/diar_streaming_sortformer_4spk-v2.1).

## Dialogue assembly and long recordings

`audio_stitch` accepts an ordered `paths` array of 1–64 PCM WAVs and produces a
mono 24 kHz PCM16 WAV plus `mix.json` with source timing. Defaults: 180 ms gaps,
gentle dynamic compression, per-clip two-pass normalization to -16 LUFS, and a
-1.5 dBFS safety ceiling. Set `gap_ms`, `compress`, `normalize`, or `target_lufs`
to override. Normalization matches perceived volume across speakers; dynamic
compression controls within-clip variation. This is not MP3 file compression.
Silent/unmeasurable clips skip loudness normalization. Inputs are never changed;
intermediate mix files are removed. The output is limited to one hour. Stitch
jobs retain dependency edges to every managed input clip for safe cleanup.

For long video extraction, inspect duration first, then enqueue `media_extract`
for each 10–20 minute interval using `url`, `start`, `end`, and optional Whisper
`language`. Each chunk is a durable job containing download, diarization and a
full-context transcript, including speech omitted from the single-speaker clips.
`transcript.json` preserves word/segment timestamps relative to both the chunk and
the source recording. `roles.json` starts with unresolved actor/character labels
and evidence fields for review. It does not assert identities automatically.

Keep a chunk plan containing each job ID and its original source interval. Numbered
speaker labels are independent across chunks; never merge them solely by label.
Use dialogue context, credits and listening to determine roles, retaining timestamped
evidence and uncertainty. Sortformer handles at most four speaker labels per chunk;
productions with larger casts need shorter, scene-aligned intervals and review.
Extraction does not authorize or trigger voice training.

For pacing comparisons, `audio_stitch` also accepts `speed` (0.75–1.25, default 1)
and `min_pause_ms` (0–800, default 0). Speed changes preserve pitch. Pause extension
only lengthens existing interior quiet runs of at least 120 ms below approximately
-40 dBFS; it does not infer word/phrase boundaries. Set `compress=false` to preserve
more of the original dynamics while retaining loudness normalization. These are
post-processing controls, not emotional or intonation conditioning. ASR word error
rate is not a naturalness metric; assess delivery by listening as well.
