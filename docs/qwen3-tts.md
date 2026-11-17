# Qwen3-TTS on Apple Silicon

Two individual speech models use the dedicated `mlx-qwen3-tts` backend:

| Slug | Purpose |
| --- | --- |
| `qwen3-tts-0.6b-customvoice-8bit` | Preset speakers; default `ryan` |
| `qwen3-tts-0.6b-base-8bit` | Voice cloning from a reference WAV and its transcript |

Both use MLX Audio 0.6.6, Metal acceleration, 8-bit weights, resident model loading,
and serialized inference. The runtime uses a separate uv Python 3.13 environment.
A local smoke test on 2026-11-17 generated 6.4 seconds of preset audio in 8.29
seconds and 4.32 seconds of cloned audio in 3.62 seconds. Those single-request
measurements include client overhead and exclude model loading (3.02 / 2.02 seconds).
The clone used the generated preset sample as its reference. Both WAVs passed muted
`afplay` playback. This checks the pipeline, not subjective voice similarity or a
representative performance benchmark. Downloaded artifacts are not checksum-verified.

## Setup and standalone use

Download the desired model (or both):

```bash
./download_model.py --model qwen3-tts-0.6b-customvoice-8bit
./download_model.py --model qwen3-tts-0.6b-base-8bit
```

Before loading, check `memory_pressure` and llama-swap `/running`, including other
servers sharing GPU memory. Start an individual worker with:

```bash
./up qwen3-tts-0.6b-customvoice-8bit
./speak-local --endpoint http://127.0.0.1:8001/v1 --play "Hello from this Mac."
```

For proxy serving, add both speech slugs to `models.enabled` in your gitignored
`serve-policy.local.yaml` and add a `speech` routing group under
`swap.routing.router.settings.groups`:

```json
"speech": {
  "swap": true,
  "exclusive": false,
  "persistent": false,
  "members": [
    "qwen3-tts-0.6b-customvoice-8bit",
    "qwen3-tts-0.6b-base-8bit"
  ]
}
```

Keep your existing enabled models in that list: overlay arrays replace the defaults.
The speech group swaps independently of the main chat group. Regenerate config
with `./llama-swap-runner.py config`; apply it only during an operator-approved
service restart. Adding these files does not change a running proxy.

Once the proxy has the new configuration:

```bash
./speak-local --list-models
./speak-local --voice aiden --play "Hello from Qwen."
./speak-local --ref-audio reference.wav --ref-text "The words in the recording." \
  --output .runtime/speech/cloned.wav --play "This uses the reference voice."
```

The CLI automatically selects Base when `--ref-audio` is supplied. `--model` selects
an individual model explicitly. References must be mono PCM16 WAV, 1–30 seconds,
at most 4 MiB; the transcript is literal text. All samples in an utterance are
combined into one WAV. Playback uses `/usr/bin/afplay` and the macOS default audio
output selected in System Settings. Playback waits for synthesis to finish;
streaming, microphone capture, and device selection are not implemented.

## Pi tool and model selection

`./pi-local` registers the `speak` extension automatically. In Pi:

```text
/speech-model
/speech-model qwen3-tts-0.6b-base-8bit
```

Select a pre-trained voice interactively or by name:

```text
/speech-voice
/speech-voice aiden
```

Available voices are `ryan`, `aiden`, `vivian`, `serena`, `uncle_fu`, `dylan`,
`eric`, `ono_anna`, and `sohee`. The `speak` tool exposes these as explicit `voice`
choices. For example, ask Pi: “Use speak with voice aiden to read this paragraph.”
Selecting a voice switches to CustomVoice and sets the default for the current
session. Set `LM_BASED_SPEECH_VOICE` before launching Pi to choose a launch default
(otherwise `ryan`). A per-call `voice` overrides the selection without changing it
and selects CustomVoice unless `model` is explicitly supplied. Combining a preset
voice with Base or reference-audio cloning is rejected. The selected preset is
never added to Base requests.

The menu selects the speech model for the current Pi session. Set
`LM_BASED_SPEECH_MODEL` for a launch default. Each `speak` invocation can override
`model`; Base requires `ref_audio` and `ref_text`, while CustomVoice accepts `voice`.
For example, ask Pi to use `speak` to read a paragraph aloud, or to clone a voice
from a specified WAV and transcript. To save silently, supply `output` and
`play=false`. Existing output files are refused by the tool. Relative paths resolve
against Pi's workspace. Cancellation aborts the client and playback; an inference
already running on the server may finish.

Qwen3-TTS is selectable as a **speech model**, not as Pi's chat `/model`: it does
not implement chat completion or agent tool calling. It is excluded from Pi and
OpenCode chat catalogs. The menu lists the two supported models even before they
are downloaded; the serving endpoint must be configured separately.

`LM_BASED_SPEECH_URL` overrides the speech API base (including `/v1`), otherwise Pi
uses `LM_BASED_SWAP_URL` plus `/v1`. `LM_TTS_API_KEY` supplies optional bearer auth.
In a microVM, use a reachable host endpoint and `play=false`; `afplay` runs on the
client host, and is not available inside Linux guests.

## Clone a dropped WAV in Pi

Drag a WAV file into Pi's terminal, then ask:

```text
Clone this voice as my-voice: /path/to/my-recording.wav
The exact words in the recording are: "Your recording's transcript."
```

The `clone_voice` tool accepts the local file path, a name, and `ref_text`. Quoted
paths, terminal-escaped spaces, and `file://` paths are supported. The terminal
must make the file's local path available; this does not add a binary attachment
interface to Pi. The agent must ask for a transcript when it does not have one;
for automatic transcription and multi-speaker analysis, use the separate
[Pi voice workbench](voice-workbench.md).

Use 1–30 seconds of clean speech from one speaker. macOS `afconvert` normalizes
stereo/float WAV recordings to mono PCM16 as needed, without changing the source.
Imports accept WAV files up to 32 MiB; the normalized reference must fit 4 MiB.
Existing voice names are refused. References and transcripts are saved privately
under the repository's ignored `.runtime/voices/` directory, or
`LM_BASED_VOICES_DIR` if set. Saved profiles persist across Pi restarts and contain
recordings, not newly trained weights.

Ask Pi to call `speak` with `cloned_voice: "my-voice"`, or select it as the default:

```text
/speech-voice clone:my-voice
```

The `/speech-voice` menu includes saved clones alongside preset speakers. Saved
clones automatically use Base; selecting a preset switches back to CustomVoice.

## API

`GET /health`, `GET /v1/models`, and `POST /v1/audio/speech` are supported. Speech
requests use `model`, `input`, optional `voice`, `language`, and
`response_format: "wav"`. Base requests use `ref_audio` (base64 WAV bytes) and
`ref_text`. No server-local reference paths or URLs are accepted. The response is
`audio/wav`; only speed 1 and non-streaming WAV are supported. The 0.6B preset model
does not support style instructions. Input is limited to 4,000 characters and
generation to 2,048 audio tokens. Long text may need splitting into separate calls.

Upstream: [MLX Audio Qwen3-TTS](https://github.com/Blaizzy/mlx-audio/tree/main/mlx_audio/tts/models/qwen3_tts),
[Qwen3-TTS Base](https://huggingface.co/Qwen/Qwen3-TTS-12Hz-0.6B-Base).
