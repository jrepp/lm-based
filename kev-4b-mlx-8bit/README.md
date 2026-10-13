---
license: apache-2.0
base_model: jaredpalmer/kev-4b
base_model_relation: quantized
library_name: mlx
tags:
- mlx
- kev
- system-one
- typed-decisions
- 8-bit
- apple-silicon
model-index:
  - name: kev-4b-mlx-8bit
    results:
      - task: { type: text-classification, name: typed decision, 8-bit MLX }
        dataset: { type: mixed, name: "transfer-v4 development (656 questions; 8-bit, same Mac as bf16)" }
        metrics:
          - { type: accuracy, value: 0.817 }
          - { type: brier_score, value: 0.243 }
      - task: { type: text-classification, name: typed decision, 8-bit MLX }
        dataset: { type: mixed, name: "decision-v7 development (1,264 questions; 8-bit, same Mac as bf16)" }
        metrics:
          - { type: accuracy, value: 0.873 }
          - { type: expected_calibration_error, value: 0.010, name: "ECE, as served" }
      - task: { type: text-classification, name: typed decision, 8-bit MLX }
        dataset: { type: mixed, name: "hard-v1 development (1,083 questions; 8-bit, same Mac as bf16)" }
        metrics:
          - { type: accuracy, value: 0.786 }
          - { type: brier_score, value: 0.313 }
      - task: { type: text-classification, name: typed decision, 8-bit MLX }
        dataset: { type: mixed, name: "devtools-v1 development (1,074 questions; 8-bit, same Mac as bf16)" }
        metrics:
          - { type: accuracy, value: 0.746 }
          - { type: brier_score, value: 0.357 }
      - task: { type: text-classification, name: typed decision, 8-bit MLX }
        dataset: { type: mixed, name: "documents-v1 development (920 questions; 8-bit, same Mac as bf16)" }
        metrics:
          - { type: accuracy, value: 0.896 }
          - { type: brier_score, value: 0.173 }
---

# Kev-4B, merged and quantized to 8 bits for MLX

[Kev-4B](https://huggingface.co/jaredpalmer/kev-4b) by Jared Palmer, with its LoRA adapter already merged into
[Qwen3.5-4B-Base](https://huggingface.co/Qwen/Qwen3.5-4B-Base) and the result quantized to 8 bits, for Apple
silicon (MLX).

This is **not an official release** of Kev. It was built with, and for, [Qualm](https://github.com/RoderickQiu/qualm), a macOS app that uses Kev to
tell a lecture from a feed. Kev's own repository and model card are the reference.

This file is Kev-4B revision `139fdd94` (2026-09-24, temperature 2.41). It replaces the earlier file on this
repo, which was built from `485ace87`.

## Why this exists

Kev-4B ships as a LoRA adapter plus a pointer head. To run it on a Mac, you download the 8.7 GB bf16 base,
merge the adapter and, to fit next to everyday apps, quantize. This repository is the result of that, done
once:

| | Build it yourself | This repository |
|---|---|---|
| Download | 9.0 GB (base + adapter) | 4.5 GB |
| Bring-up, base already on disk | about 1 minute and a 15 GB peak to merge and quantize; a bf16 load peaks at 16 GB | about 4.8 GB |
| Memory while scoring | about 10 GB (bf16) | about 6.6 GB |

Measured on an M5 Pro with 24 GB, running macOS 27. The 8-bit process reached 8.5 GB during the longest suite.

## What's here

| File | What it is |
|---|---|
| `model.safetensors`, `config.json` | The merged backbone, 8-bit (group size 64), in mlx-lm's format (`"quantization"` in the config) |
| `head.pt` | Kev's pointer head and calibration (temperature 2.406), copied from `jaredpalmer/kev-4b` at `139fdd94` |
| tokenizer files | Unchanged from `jaredpalmer/kev-4b` |
| `provenance.json` | The exact revisions it was built from, the method, and the SHA-256 of `model.safetensors` |
| `LICENSE` | Apache-2.0 |

## How it was made: the changes from the originals

Built from `jaredpalmer/kev-4b` at revision `139fdd94f1b6a6ad80cc15e08fcb99cac885a101` and
`Qwen/Qwen3.5-4B-Base` at revision `1001bb4d826a52d1f399e183466143f4da7b741b`, with Kev's code at commit
`5920c5fe4ca8e0970ed4209ac2c9b8e18bea5109`:

1. **Merged.** The base was loaded in bf16 with mlx-lm, and the LoRA adapter was merged in fp32 on the CPU
   (`kev.mlx_model.merge_lora`: W + B·A·α/r), rounded once to bf16. This is Kev's own MLX loading path.
2. **Quantized.** `mlx.nn.quantize` with `bits=8, group_size=64`, on every Linear and Embedding layer whose
   input width divides by 64.
3. **Kept as is.** The pointer head in `head.pt` stays fp32, including the checkpoint's fitted temperature.
   Nothing was retrained.

`model.safetensors` is 4,469,640,165 bytes. SHA-256
`83adf34ef8f2433166225960d0f074def35d3de52449fa8861bc356398312d31`.

## Quality

`kev.benchmark` on the development split of five suites, this file against Kev's own MLX path in bf16, on the
same Mac. Both servers used this checkpoint's temperature. Clean-question accuracy and Brier:

| Suite | Questions | bf16 | This file | Same top answer |
|---|---:|---|---|---|
| transfer-v4 | 656 | 0.817 / 0.243 | 0.817 / 0.243 | 652 / 656 |
| decision-v7 | 1,264 | 0.873 / 0.183 | 0.873 / 0.183 | 1,262 / 1,264 |
| hard-v1 | 1,083 | 0.787 / 0.311 | 0.786 / 0.313 | 1,076 / 1,083 |
| devtools-v1 | 1,074 | 0.738 / 0.358 | 0.746 / 0.357 | 1,064 / 1,073 |
| documents-v1 | 920 | 0.893 / 0.173 | 0.896 / 0.173 | 918 / 920 |

`kev.compare`'s paired 95% intervals include zero for accuracy, Brier and NLL on transfer-v4 and decision-v7.
On hard-v1 the accuracy interval includes zero; the Brier and NLL intervals do not (this file is a little
worse, about +0.002 Brier and +0.003 NLL). On devtools-v1 the accuracy interval excludes zero in this file's
favour (+0.007); Brier and NLL include zero. On documents-v1 the accuracy interval touches zero and the Brier
and NLL intervals include zero. The devtools comparison drops one repeated example id, which is why that row
counts 1,073 answers. The paired intervals are in [jaredpalmer/kev#162](https://github.com/jaredpalmer/kev/issues/162).

The local bf16 run matches the accuracy on Kev-4B's own model card for transfer-v4 (0.817) and decision-v7
(0.873), and is within 0.002 on hard-v1, devtools-v1 and documents-v1.

These are development splits. The locked test splits were not scored.

On Qualm's 119 scripted trial pages, same checkpoint, 8-bit against bf16: page kind agrees on 117 of 119, purpose and the sensitive side on all 119, and no rule crosses its current threshold on a different page. The largest per-rule probability gap is 0.029.

## Use

This isn't a chat model. Kev answers typed questions (a choice, a yes/no, a score) with calibrated
probabilities, through its pointer head. The weights load with Kev's MLX model class. Take the tokenizer and
head metadata from the same Kev revision these weights were built from:

```python
from pathlib import Path
from huggingface_hub import snapshot_download
from kev.checkpoint import Checkpoint
from kev.mlx_model import MLXDecisionModel
from kev.model import PointerHead, load_tokenizer, pad_id

weights = Path(snapshot_download("RoderickQiu/kev-4b-mlx-8bit", allow_patterns=["config.json", "model.safetensors"]))
ck = Checkpoint("jaredpalmer/kev-4b@139fdd94f1b6a6ad80cc15e08fcb99cac885a101")
tok = load_tokenizer(ck.meta.base, revision=ck.meta.base_revision)
model = MLXDecisionModel(weights, pad_id(tok), head_dim=ck.meta.head_dim)
# The head is sized from the embedding width, which is packed in quantized weights: size it from the real one.
model.head = PointerHead(model.text.embed_tokens.dims, dp=ck.meta.head_dim).eval()
model.head.load_state_dict(ck.meta.head)
model.head.temperature = ck.meta.temperature
```

`model` then works wherever Kev's `DecisionModel` does, for example behind `kev.serve`'s `/v1/systemone`
endpoint.

Qualm downloads a pinned revision by itself on the first start. It checks `provenance.json` against the Kev
checkpoint it runs and the file's SHA-256, and builds the weights locally when they don't match.

## License and credits

Apache-2.0, like both originals:

- **Kev-4B:** the adapter, head and tokenizer, by Jared Palmer. [jaredpalmer/kev-4b](https://huggingface.co/jaredpalmer/kev-4b), [github.com/jaredpalmer/kev](https://github.com/jaredpalmer/kev). Apache-2.0.
- **Qwen3.5-4B-Base:** the backbone, by the Qwen team, Alibaba Cloud. [Qwen/Qwen3.5-4B-Base](https://huggingface.co/Qwen/Qwen3.5-4B-Base). Apache-2.0.

The modifications (merging and 8-bit quantization) are described above. All credit for the model belongs to
its authors; any errors in this conversion belong to this repository.
