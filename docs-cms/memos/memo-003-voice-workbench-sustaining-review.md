---
title: Voice workbench sustaining review
author: Codex
created: 2026-11-17T11:38:26Z
tags: [memo, operations, voice]
id: memo-003
project_id: lm-based
doc_uuid: ef4cff00-8081-44c7-ab4f-9bef5424af88
---

# Overview

The speech workflow produces usable experimental outputs, but its initial detached-job
implementation needs an operational owner before routine use. The user requested a
managed job service following this review. These findings describe the pre-service
snapshot; implementation and verification belong in the service reference documentation.

# Context

Read-only inspection found 36 recorded jobs: 28 completed, six failed, and two active
media downloads. Job files occupied approximately 10.07 GB, including four exported
checkpoints of approximately 2.50 GB each. This excludes Hugging Face and uv caches.
The six failures include already-addressed dependency/ffmpeg integration problems and
one unavailable source video; they are not six unresolved current defects.

The interview trial needed custom orchestration and speaker curation scripts outside
the tool surface. The subsequent documentary required manual interval splitting.
The latest render succeeded, but did not receive an ASR evaluation.

# Details

## P1: Job lifecycle and signal ownership

`support/pi/extensions/voice-workbench/jobs.ts` initially persisted a PID and later
signalled its process group without verifying process identity. PID reuse can target
an unrelated process. Failure between spawn and launch metadata publication can leave
an untracked child. Stale failure detection is returned to callers but not persisted.
Cancellation has no bounded escalation or durable cancelled state when Python has not
started. Background jobs survive Pi, but no service owns their recovery or deadlines.

Acceptance: persistent queue, one supervisor owning live child handles, cancellation
before and after startup, parent-death cleanup, bounded shutdown escalation, and
restart reconciliation without ever killing a PID read from disk.

## P1: Storage ownership and durable voice indexing

Datasets refer to clip files in analysis jobs; trained metadata refers to job checkpoints.
Blind age-based cleanup would break live voices. There is no retention policy, dependency
index, storage accounting, or durable trained-voice selection surface. The voice menu
only discovers saved reference clones; training requires an opaque metadata path.

Acceptance: indexed trained voices, explicit retention roots and transitive dependency
protection, dry-run cleanup, no deletion of legacy or external data, and tombstones for
expired jobs. Never delete models from shared caches or modify existing model binaries.

## P1: Resource scheduling and request admission

Workbench GPU jobs use a cooperative lock, but the resident speech API does not share
it. Its threading lock serializes generation while requests can accumulate and continue
after client timeout/disconnect. Memory-pressure checks are advisory, not reservations.

Acceptance: bounded service queue, predictable busy responses, per-job deadlines,
and documented limits on coordination with unrelated live inference servers. Add
speech API admission/cancellation separately; a job queue alone does not solve this.

## P2: Progress, recovery, and observability

Worker status has running/completed states but no structured stage or heartbeat.
Downloads suppress progress; analysis writes its manifest only after all clips complete.
Failure late in transcription loses reusable progress. The documentary was still
downloading at review time; this is not evidence of a hang. Existing 6000-byte log tails
bound responses, not log files on disk.

Acceptance: structured stage/progress, duration and queue metrics, bounded logs, health,
job listing, failure codes, and explicit interrupted state. Later add stage resume and
long-file segmentation with source offsets and per-chunk speaker-label scope.

## P2: Dataset and evaluation quality

`clean_regions` cuts long turns every 12 seconds, potentially through words. Single
speaker activity does not establish clean audio: music, bleed, and wrong labels remain.
The guest trial required transcript/context curation; it was not listening-verified.
Dataset manifests discard correction/review provenance. Validation JSONL is created but
not passed into training; external held-out generation must be run explicitly.

Both schedule samples received raw WER 0.17647 because Whisper formatted spoken numbers
as digits. Preserve raw WER, add a separately labelled normalization policy and word
alignment, and measure subjective quality separately. Do not treat WER zero as voice
similarity. Both rendering paths accept 4000 characters but cap output at 2048 tokens
without reporting a truncation condition; long-input completeness remains unverified.

Acceptance: speech-aware boundaries, review decisions and original/corrected transcripts
in manifests, novel and held-out regression fixtures, explicit output-completeness
checks, and documented subjective listening results.

## P2: Runtime reproducibility and maintainability

Top-level dependency pins leave transitive versions and model revisions unresolved.
Training needed an older isolated MLX Audio runtime after a real compatibility failure.
The monolithic worker mixes download, DSP, training, evaluation, and lifecycle code.
Model/voice constants and validation rules are repeated across Python and TypeScript.
Node emits module-type warnings on every invocation. Dropped-path parsing is supported
by cloning/workbench tools but not inline speak references; tilde paths are inconsistent.

Acceptance: centralized runtime definitions and recorded resolved environments/model
revisions, versioned manifests, separable worker actions, shared contracts, and fixtures
for path handling. Avoid turning the experimental trainer into a production dependency
without a reproducible smoke-training test and upgrade process.

# Recommendations

Implement the requested managed service per ADR-003, with the existing Pi tool names
as clients. Prioritize lifecycle and dependency-aware retention before broad automatic
cleanup. Preserve existing voices and live processes. Follow with unified voice selection,
quality review, resumable analysis, and speech API admission control.

# References

- [Voice workflow](../../docs/voice-workbench.md)
- [Speech backend](../../docs/qwen3-tts.md)
- [Managed process decision](../adr/adr-003-tmux-service-set-launcher.md)

# Appendix

Review checks: five Python workbench tests, six Python speech tests, eight Pi speech/
workbench tests, and two optional speech API tests passed. API tests used the isolated
speech runtime; normal project discovery skips them. No GPU models were loaded for
this review, and no existing services or artifacts were removed.
