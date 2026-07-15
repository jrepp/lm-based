---
title: Adopt docs-cms (docuchango) for structured decision records
status: Accepted
created: 2026-07-15T06:57:19Z
deciders: maintainer
tags: [agents, documentation, process]
id: adr-001
project_id: lm-based
doc_uuid: 466790b3-31b8-46f7-9262-deb2cab739a5
---

# Context

The repository has grown a large body of *reference* documentation under
`docs/` (architecture, credentials, serving design, model cards), but it has no
structured way to record *why* a decision was made, what alternatives were
rejected, or when a prior decision was superseded.

This matters more now because the stack is converging on a multi-component
serving control plane (`serve-manager`, `llama-swap`, `run-server.py`, stats,
dashboard, `./up`) where decisions accumulate and where AI agents do much of the
implementation work. Without a decision log, agents re-derive (or quietly
contradict) prior choices on every pass.

# Decision

Adopt [docuchango](https://github.com/jrepp/docuchango) and the `docs-cms`
pattern at `docs-cms/`, with four document types:

| Type | Use for |
| --- | --- |
| ADR | decisions that have been made or are being proposed |
| RFC | proposals and design discussions needing review |
| Memo | investigation results, status, meeting outcomes |
| PRD | product requirements |

`docs-cms/` is kept separate from `docs/`: `docs/` remains the reference /
how-to tree; `docs-cms/` is the versioned decision log. Both are validated
(`docuchango validate` for the CMS; `markdownlint-cli2` via pre-commit for all
Markdown).

# Consequences

## Positive

- Decisions are versioned, searchable, and citable by ADR number.
- Agents ground their work in the CMS instead of inferring intent from code.
- Frontmatter schema validation catches missing fields and broken links.

## Negative

- Two documentation trees to keep coherent; cross-references must be maintained.
- Extra frontmatter discipline (fresh `doc_uuid` per document, status lifecycle).
- `docuchango validate` requires Python >= 3.10; the system install on Python
  3.9 is broken (`TypeGuard` import). Run it through uv (see AGENTS.md).

## Neutral

- The CMS does not replace `docs/` reference material; it complements it.

# Alternatives Considered

## Plain Markdown in docs/

Rejected: no schema, no validation, decisions drift and contradict silently.

## A wiki / external CMS

Rejected: not in version control, not agent-readable, not reproducible.

## No decision log

Rejected: agent-driven iteration without a decision record re-derives prior
choices and erodes architectural coherence over time.

# References

- Setup: `docuchango init`, `docuchango bootstrap`
- Guides: `docuchango bootstrap --guide {bootstrap,agent,best-practices}`
- Config: `docs-cms/docs-project.yaml`
