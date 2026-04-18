# Retrieval Backends

Comparison of storage backends for medium-scale RAG and agent memory use cases.
Primary reference: analysis of `~/d/memvid` (memvid-core v2.0.139, Rust) conducted April 2026.

For embedding model selection: [embedding-model-selection.md](embedding-model-selection.md)
For retrieval algorithms and index structures: [retrieval-concepts.md](retrieval-concepts.md)

---

## memvid v2 — Deep Analysis

### What It Is

A single `.mv2` binary file containing everything: compressed payloads (zstd/lz4), a WAL,
a Tantivy BM25 index, an HNSW or flat vector index (bincode-serialized), a time index,
a CLIP visual index, an SPO entity-relationship graph, and typed "MemoryCard" facts.
No sidecar files. The entire corpus is one portable, optionally-encrypted artifact.

The name is a metaphor — there is no video codec. "Frames" are immutable append-only content
units inspired by video frame semantics. The v1 library (deprecated Python) actually used QR
codes embedded in MP4 files; v2 discards that entirely.

### Storage and Embedding Mechanics

Embeddings are stored as raw `Vec<f32>` in the WAL at ingest time, materialized into the
vector index on `commit()`.

Index selection at build time:
- **< 1,000 vectors** → flat scan (bincode `Vec<VecDocument>`, linear L2 with SIMD)
- **≥ 1,000 vectors** → HNSW (M=16, ef_construction=200, hardcoded constants)
- **Optional PQ96** → 16× compression via product quantization, needs ≥ 100 vectors

Distance metric is **L2 (Euclidean)** throughout. Similarity score = `1.0 - distance`.
Callers must normalize vectors externally for cosine equivalence.

Supported embedding sources:
- Local ONNX (BGE-small 384d, BGE-base 768d, nomic-embed-text 768d, gte-large 1024d)
- OpenAI API (text-embedding-3-small 1536d, text-embedding-3-large 3072d, ada-002 1536d)
- CLIP visual (MobileCLIP-S2, 512d)
- Whisper audio (transcription → text → embed)
- Caller-provided `Vec<f32>` via `put_with_embedding()`

### Chunking

Default: 1,200-char chunks with ±240-char slack to find natural sentence/paragraph breaks.
Documents shorter than 2,400 chars are not chunked. Structure-aware mode activates on
Markdown tables and code fences, preserving table rows and code blocks as atomic units.

Parent frame (`FrameRole::Document`) links child chunks (`FrameRole::DocumentChunk`) via
`parent_id`. A `TextChunkManifest` on the parent records each chunk's character range.

No semantic splitting, no sentence-transformer-based chunking, no recursive character
splitting. Purely character-boundary + structural heuristics.

### Retrieval Patterns

| Method | What it does |
|---|---|
| `search()` / `search_lex()` | BM25 via Tantivy with sketch pre-filter, date range filter, ACL filter |
| `search_vec()` | Pure ANN (flat or HNSW), returns distance scores |
| `vec_search_with_embedding()` | Vector search with snippet extraction |
| `search_adaptive()` | Vector with score cutoff strategies (cliff, elbow, relative, absolute) |
| `ask()` | Hybrid BM25 + vector with RRF (k=60), intent detection (aggregation/recency/analytical) |
| `search_clip()` | Visual similarity over CLIP embeddings |
| `graph_search()` | Entity-relationship pattern matching over SPO MemoryCards |
| `timeline()` | Chronological retrieval; supports `as_of_frame` / `as_of_ts` time-travel |

Query operators in `search()`: implicit AND, `OR` explicit, field filters (`title:foo`,
`uri:bar`), date range (`date:2024-01`). Multi-word queries require all terms by default.

`ask()` adjusts `top_k` multipliers by intent: 1× (default), 2× (recency), 3× (aggregation),
5× (analytical). Uses OR-broadened queries for recall on aggregation/analytical intents.

### Memory and Agent Features

`MemoryCard` types: facts, preferences, events, relationships. Populated via:
- Explicit `put_memory_card()` API call
- Auto-extraction by enrichment workers (background, feature-gated)
- SPO triplet extractor (`TripletExtractor`) that parses Subject-Predicate-Object from content

`MemoriesTrack` and `Logic-Mesh` (entity graph) enable `graph_search()` for natural language
entity queries ("who works at", "who likes", "lives in").

Temporal track: NLP date extraction, regex for date patterns, resolved to UTC via `interim`
crate. Default timezone hardcoded to `America/Chicago` — bug for non-US deployments.

### Configuration Knobs

**Per-document (`PutOptions`):**
- `auto_tag`, `extract_dates`, `extract_triplets` — enrichment toggles (default: all on)
- `enable_embedding` — on-device ONNX embedding (default: off)
- `instant_index` — soft Tantivy commit after WAL append (default: on)
- `dedup` — skip insert if BLAKE3 hash exists (default: off)
- `no_raw` — store text only, discard binary payload (default: off)
- `extraction_budget_ms` — PDF extraction time limit (default: 350ms)

**Batch mode (`PutManyOpts`):**
- `compression_level` — 0=none, 1=fast, 3=default, 11=max
- `disable_auto_checkpoint` — caller-driven commits only (default: on in batch mode)
- `skip_sync` — skip fsync, not crash-safe (default: off)
- `wal_pre_size_bytes` — pre-allocate WAL

**`AdaptiveConfig`:** `max_results` (default 100), `min_results` (1), `normalize_scores`,
`strategy` (relative threshold 0.5 default).

**`VectorCompression`:** `None` (default) or `Pq96`.

### Performance Profile

From their own benchmarks on local retrieval:
- P50: **0.025ms**, P99: **0.075ms**
- HNSW threshold and PQ minimums are hardcoded (1,000 and 100 vectors respectively)

### Hard Limitations

| Limitation | Impact |
|---|---|
| HNSW deletions are no-ops | Deleted frames remain in vector index; corpus drifts on eviction |
| Cannot retrieve original embedding from HNSW/PQ index | No embedding export or re-indexing without full rebuild |
| PQ96 and HNSW params hardcoded | No recall/speed tuning |
| No pre-filtering during ANN | Metadata filters applied after retrieval only |
| Fully synchronous API | Requires `spawn_blocking` in async Rust |
| Batch mode: embedding/tagging "not yet implemented" | Bulk ingestion loses semantic indexing |
| Temporal TZ hardcoded to `America/Chicago` | Incorrect timestamps for non-US deployments |
| No distributed mode | Single-machine ceiling |
| `pdf_oxide` feature disabled | Panics on ligature fonts; falls back to `pdf-extract` |

The HNSW deletion no-op is the most significant production concern. Any corpus needing
forgetting/eviction semantics must call `finalize_indexes()` (full-scan rebuild) to actually
purge deleted embeddings.

---

## Backend Comparison

### Scope

Medium-scale RAG + memory: 1M–50M chunks, hybrid search, local or self-hosted preferred,
agent memory semantics valued.

### Matrix

| | **memvid v2** | **Qdrant** | **LanceDB** | **MongoDB Atlas** | **pgvector** | **Chroma** | **sqlite-vec** |
|---|---|---|---|---|---|---|---|
| **Deployment** | Single `.mv2` file | Docker | Embedded / S3 | Atlas cloud or mongot sidecar | PostgreSQL extension | Server or embedded | SQLite extension |
| **Self-hosted simplicity** | Trivial | Easy | Trivial | Moderate (mongot sidecar required) | Easy | Easy | Trivial |
| **Language** | Rust | Rust | Rust (Arrow/Lance) | C++ (server) | C (PG extension) | Python | C |
| **Hybrid search** | BM25 + vector (RRF built-in) | Sparse + dense (BM25F + vector) | Vector only (Tantivy add-on) | Lucene BM25 + HNSW (RRF via pipeline) | Manual FTS + vector | Vector only | Vector only |
| **Pre-filter during ANN** | No (post-filter only) | Yes (inline payload filter) | Yes | Yes | Approximate (IVFFlat) | Metadata filter (post) | SQL WHERE |
| **Deletion correctness** | No — HNSW immutable | Yes | Yes (Lance versioned) | Yes | Yes | Yes | Yes |
| **Full CRUD** | Logical only for vectors | Yes | Yes | Yes | Yes | Yes | Yes |
| **Schema flexibility** | Fixed frame schema + MemoryCards | JSON payload metadata | Columnar, Arrow schema | Fully schemaless documents | Metadata dict | Metadata dict | Tables |
| **Agent/memory features** | MemoryCards, SPO graph, timeline, time-travel | None | None | DIY via document model | None | None | None |
| **Transactions** | WAL, single-writer | None (eventual) | Versioned snapshots | ACID multi-document | Full ACID | None | SQLite ACID |
| **Vector compression** | PQ96 (16× if ≥100 vecs) | SQ8, PQ, Binary (configurable) | PQ via Lance format | Scalar, Binary (Atlas) | None | None | None |
| **Async API** | No | Yes (REST/gRPC) | Yes (Rust + Python) | Yes (drivers) | Yes | Yes | SQLite-level |
| **Scale** | ~5–20M (RAM-bound HNSW) | 100M+ (disk-based) | 100M+ (disk-based) | 100M+ (Atlas) | 50M+ (tuned) | <5M practical | <10M practical |
| **Multi-tenancy** | One file per tenant | Named collections + namespaces | Multiple tables/datasets | Collections + databases | Collections | Collections | Tables |
| **Observability** | `stats()`, `verify()`, doctor report | Prometheus + REST | Lance stats | Atlas monitoring | Limited | Limited | None |

### Qdrant — Key Details

Self-hosted via Docker, Rust-native, disk-based HNSW with correct deletions. Inline payload
filtering during ANN search (exact pre-filter at small scale, sampling at large scale). Sparse
+ dense hybrid search using FastEmbed for on-device BM25. Named collections map cleanly to
per-model or per-agent namespaces.

Quantization options are configurable at index creation time (scalar int8, PQ, binary).
REST and gRPC APIs. Strong operational tooling (Prometheus, dashboard).

Best fit for: medium-scale RAG with frequent updates, metadata-filtered ANN, self-hosted.

### LanceDB — Key Details

Embedded (zero server), Rust-based, Apache Arrow + Lance columnar format. Supports S3 and
local disk. Versioned snapshots give correct delete/update semantics without a separate
server process. Python and Rust APIs both async.

Scale ceiling is much higher than memvid (100M+ vectors) with disk-based storage. Does not
include BM25 natively — Tantivy integration is an optional add-on, not first-class.

Best fit for: large-scale RAG, columnar/tabular data, S3-backed or edge deployment, zero ops.

### MongoDB Atlas — Key Details

Vector search (`$vectorSearch` aggregation stage) requires Atlas cloud or the `mongot`
sidecar process. **Not available in community `mongod`.** This is the primary gate for
local-first deployments.

When available: HNSW with configurable similarity metrics and scalar/binary quantization.
Full-text via Atlas Search (Lucene-based BM25, facets, fuzzy). Hybrid retrieval via
`$unionWith` + RRF scoring pipeline. ACID multi-document transactions for atomic memory ops.

Strongest advantage is schema flexibility — heterogeneous memory shapes (conversation turns,
tool outputs, facts, embeddings) coexist in one collection without schema migrations.
Aggregation pipeline supports complex retrieval logic not expressible in simpler vector DBs.

Best fit for: heterogeneous memory shapes, complex query logic, teams already using Atlas,
willing to accept cloud dependency or mongot operational overhead.

### pgvector — Key Details

PostgreSQL extension. Adds `vector` type, `<=>` cosine operator, IVFFlat and HNSW indexes.
Standard SQL for filtering, joining, and ranking. Full-text search via `pg_trgm` or
`tsvector`/`tsquery` (not BM25-grade but usable).

Strengths: familiar SQL interface, ACID, row-level security, existing PG ecosystem. Weakness:
vector indexes are in-memory (HNSW) or approximate (IVFFlat) and require tuning at scale.
Pre-filtering quality depends on planner; not as reliable as Qdrant's inline ANN filtering.

Best fit for: teams already running Postgres, structured metadata + vector hybrid queries,
medium scale (<50M vectors with tuning).

---

## Decision Guide

| Scenario | Pick |
|---|---|
| Agent long-term memory, time-travel, portable, air-gapped | **memvid** |
| Medium-scale RAG, updates/deletes, metadata-filtered ANN, self-hosted | **Qdrant** |
| Large-scale RAG, columnar, S3-backed, zero-server | **LanceDB** |
| Heterogeneous memory shapes, complex queries, Atlas acceptable | **MongoDB Atlas** |
| Existing Postgres infrastructure | **pgvector** |
| Prototype or small-scale Python RAG | **Chroma** |
| Ultra-lightweight single-file + SQL | **sqlite-vec** |

### Stacking memvid with another backend

memvid's agent memory features (MemoryCards, SPO graph, timeline, time-travel) are unique and
not easily replicated. Its RAG limitations (HNSW deletion no-op, no pre-filtering) are real.

A viable hybrid: use **memvid for agent memory** (structured facts, conversation history,
time-travel replay) and **Qdrant for document RAG** (large corpus, filtered ANN, correct
deletes). Route queries through clawrouter with memory context injected from memvid alongside
document context from Qdrant.

