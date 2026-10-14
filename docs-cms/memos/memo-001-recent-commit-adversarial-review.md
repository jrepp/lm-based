---
title: Recent commit review and regression fixes
author: Codex
created: 2026-10-14T04:23:55Z
tags: [memo, regressions, review]
id: memo-001
project_id: lm-based
doc_uuid: 1798c2d5-0a5f-4410-a2b0-2e5c480f74fc
---

# Overview

Reviewed the four implementation commits from `fa773f4` through `872a61b`.
Found five actionable issues. The user requested fixes and regression tests,
which are recorded in commit `69f12c0`. This memo records the findings and
subsequent live OCR validation.

# Context

The review focused on model download paths, swap setup, and the new Pi tools.
The baseline passed 59 selected Python tests and seven record-processing tests.
Those tests did not cover the failures below. New regression tests reproduced
the failures before the fixes were applied.

# Details

## P1: Snapshot downloads can overwrite project files

In `dd9588c`, `download_model.py` began using the project root for relative
artifact paths. MLX and Transformers snapshot anchors instead name a file inside
a model directory. A mocked download of kev, Bonsai, and Coder-480B confirmed
that each targeted the project root. Model README and config files could replace
project files, and the launcher would still miss its expected model directory.

Fixed snapshot destinations to use the anchor's parent for non-GGUF snapshots.
Explicit CLI output now takes precedence over sidecar destinations. Relative
sidecar destinations resolve from the project root. Sharded GGUF downloads keep
their Hub subdirectories. Tests exercise all current non-GGUF snapshot records
and preserve a sentinel project README.

## P1: Classification can destroy its source file

In `872a61b`, `decide_records` accepts an output equal to its input. A tool-level
reproduction replaced a JSONL source with decision answers. Symlinks and
hardlinks had the same effect.

The tool now rejects matching paths or file identities before classification
and checks again before publishing. Tests cover all three aliases and assert
that no classifier request occurs when an alias is rejected.

## P1: Cancellation can erase previous results

In `872a61b`, an aborted classification still reaches the final write. A
pre-aborted call replaced an existing results file with a single newline.
Mid-run cancellation can also replace complete prior results with partial ones.

The tool now checks cancellation before work and before publication. It stages
output in the destination directory, then renames it atomically. Cancelled runs
leave the prior output intact. Tests cover cancellation before and during work,
successful replacement, and staging cleanup.

## P2: CLI installation still requests the older swap release

`9728490` introduced v264 routing and changed the library default, but
`llama_swap/cli.py` still defaulted to v209. A mocked `cmd_ensure([])` confirmed
that the documented installation command requested v209.

The CLI now imports the library's default version. Tests cover that default
and an explicit version override. Existing binaries still require the documented
`--overwrite` option to be replaced.

## P2: The default OCR model is missing from the generated catalog

`872a61b` defaults `pdf_extract` to `glm-ocr-q8_0`. The model had neither a
sidecar nor an enabled policy entry. `9728490` also referenced it in the small
group. Generated config contained that group member but no matching model.

Added the model sidecar, enabled policy entry, conservative serving profile,
and projector support in the launcher. The sidecar includes both required
GGUF filenames and pins the upstream revision. Its provenance remains
`planned_download`. Tests cover model/group consistency, exclusion from the
chat picker, projector arguments, and rejection of a missing projector.

# Recommendations

The five code follow-ups were implemented during the review. The subsequent
live OCR smoke test below passed against the existing warm worker. Cold startup,
concurrent inference, and OCR quality on difficult scans remain follow-ups.
No weights were downloaded and local model hashes were not verified.

# References

- [Download regression tests](../../tests/test_download_model.py)
- [Swap installer regression tests](../../tests/test_llama_swap_cli.py)
- [OCR serving regression tests](../../tests/test_ocr_serving.py)
- [Classification execution tests](../../support/pi/extensions/decide/index.test.ts)
- [Pi setup and output behavior](../../docs/pi-local-model.md)
- [Upstream OCR artifacts at the pinned revision](https://huggingface.co/ggml-org/GLM-OCR-GGUF/tree/964d28c9e3c3330b0f322235abefdcdd29116eb7)

# Appendix

All download reproductions used mocked Hub calls. Tool-level reproductions used
a fake classifier and temporary files. No model binaries or run captures were
changed. The regression suites need neither model weights nor a live server.

Validation after the fixes: all 117 Python tests and 13 Pi extension tests pass.
The docs CMS validator passes. Routing configs were regenerated and the download
catalog lists the OCR slug. Repository-wide pre-commit found pre-existing
whitespace issues in unrelated files; its unrelated formatting edits were
reverted. Markdown lint passed in that run.

## Live OCR smoke test (2026-10-13 Pacific)

Invoked the actual `pdf_extract` extension against llama-swap at
`http://127.0.0.1:8081`, using its default `glm-ocr-q8_0` model. The worker was
already ready and advertised a 32768-token context. No service was restarted.
This validates the running worker and extension, not a cold launch of the
newly generated configuration.

Used a synthetic two-page PDF and a PNG rendering of its first page at 150 DPI.
Fixtures and raw OCR output remained outside the repository. This report retains
only test outcomes and timings, with no sample text or machine-specific paths.

| Request | Wall time | Result |
| --- | --- | --- |
| PNG image | 2.27 s | All five expected text fields found |
| Full two-page PDF | 2.17 s | Both pages recognized in order with page headings |
| PDF with `pages: "2"` | 0.15 s | Page 2 recognized; page 1 content absent |

Every expected string matched; only whitespace layout differed from the source.
The PDF requests exercised Ghostscript conversion and the extension's OCR HTTP
path. Repeated content may benefit from caching, so these timings are smoke-test
observations, not a throughput benchmark.

Before and after the requests, `/running` showed `glm-ocr-q8_0`,
`kev-4b-mlx-8bit`, and `qwen36-27b-q6k` all ready. OCR did not evict the other
workers. No simultaneous chat/classifier request was issued.
