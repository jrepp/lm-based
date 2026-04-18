# The RAG Pipeline

Retrieval-Augmented Generation (RAG) is a pattern for answering questions against a corpus
too large to fit in a single LLM prompt. A retrieval system selects the relevant subset;
the LLM uses that subset to generate a grounded answer.

This document walks through the complete pipeline from raw document to final answer, covering
both the indexing phase (run once per document) and the query phase (run once per question).

Related documents:

- Foundational concepts: [foundations-what-is-an-embedding.md](foundations-what-is-an-embedding.md)
- Chunking decisions: [chunking-strategies.md](chunking-strategies.md)
- Index and search mechanics: [retrieval-concepts.md](retrieval-concepts.md)
- Storage backend selection: [retrieval-backends.md](retrieval-backends.md)

---

## Two phases

RAG has two distinct phases that run at different times and at different frequencies:

```
INDEXING PHASE (offline, once per document)
  Raw document → extract text → chunk → embed → store in index

QUERY PHASE (online, once per question)
  Question → embed → search index → retrieve chunks → assemble context → generate answer
```

The indexing phase is batch work: slow, expensive, done in advance. The query phase must be
fast: the user is waiting.

---

## Indexing phase

### Step 1: Document ingestion

Accept the raw document in its source format. Common formats:

- Plain text (`.txt`, `.md`)
- PDF — requires extraction (text layer vs. OCR for scanned docs)
- HTML — requires stripping tags and navigation chrome
- DOCX, XLSX — requires format-specific parsing
- Code — may want to preserve structure (function boundaries)

At this step, also extract metadata: source URL or path, title, author, creation date,
document type. This metadata travels with every chunk the document produces.

Failure modes:
- PDF with scanned images: text extraction returns nothing. Requires OCR.
- PDF with ligature fonts: some extractors corrupt `fi`, `fl` ligatures into garbage
  characters (e.g., "efficient" becomes "e cient").
- HTML with JavaScript-rendered content: static extraction misses content loaded dynamically.

### Step 2: Text cleaning

Before chunking, normalize the extracted text:
- Remove boilerplate (headers, footers, page numbers, navigation)
- Normalize whitespace and Unicode (ligatures, smart quotes, zero-width spaces)
- Optionally repair broken words from PDF column extraction

Cleaning quality directly affects embedding quality. Garbage in, garbage out: embedding a
chunk full of OCR artifacts produces a vector that does not cluster with clean content.

### Step 3: Chunking

Split the cleaned text into chunks sized for the embedding model's context window and the
retrieval precision you need. See [chunking-strategies.md](chunking-strategies.md) for the
full decision tree.

Key decisions at this step:
- Chunk size (characters or tokens)
- Overlap (0–20% is typical)
- Split strategy (fixed, sentence-boundary, structure-aware, semantic)
- Parent-child relationship (store parent for context, index children for retrieval)

Output: a list of `(chunk_text, chunk_metadata)` pairs.

### Step 4: Embedding

Pass each chunk through the embedding model to produce a vector.

```
chunk_text  → [embedding model] → [0.21, -0.45, 0.03, ...]
```

This is the most computationally expensive step. Strategies:

- **Batch embedding:** send multiple chunks per API call (up to 2,048 for OpenAI). Reduces
  round-trip overhead by orders of magnitude vs. one call per chunk.
- **Local vs. API:** local ONNX models (BGE, nomic-embed) have zero per-call cost but require
  GPU/CPU capacity. OpenAI API has per-token cost but no infrastructure overhead.
- **Caching:** if re-indexing a partially updated corpus, skip chunks whose text has not
  changed (hash the chunk text to detect unchanged content).

Output: a list of `(vector, chunk_text, chunk_metadata)` triples.

### Step 5: Storing in the index

Write each `(vector, chunk_text, chunk_metadata)` into the storage backend.

What gets stored:
- The vector (for ANN search)
- The chunk text (to return as context to the LLM)
- The metadata (for filtering and attribution)
- Optionally: a BM25 inverted index over the chunk text (for hybrid search)

The vector index structure (HNSW, flat scan) is either built incrementally or in a batch
rebuild at the end of ingestion, depending on the backend.

### Indexing pipeline summary

```
[raw docs]
    │
    ▼
[extract text]  ←── format-specific parsers
    │
    ▼
[clean text]    ←── normalize, strip boilerplate
    │
    ▼
[chunk]         ←── size, overlap, strategy choice
    │
    ▼
[embed]         ←── model choice, batch size, caching
    │
    ▼
[store]         ←── vector index + optional BM25 index
```

---

## Query phase

### Step 1: Receive the query

The user submits a question or search string. Before doing anything else, consider:

- **Query type:** Is this a factual lookup ("what is the default ef_construction for HNSW?"),
  a synthesis request ("explain the tradeoffs of different chunking strategies"), or a
  conversational follow-up ("what about the overlap setting?")?
- **Query transformation:** Should the query be rewritten before retrieval? Common techniques:
  - Hypothetical Document Embedding (HyDE): ask the LLM to write a hypothetical document that
    would answer the question, then embed that document instead of the bare query
  - Query expansion: append related terms to improve recall
  - Sub-question decomposition: split a complex query into simpler sub-questions, retrieve
    for each, then combine

### Step 2: Embed the query

Embed the query using the same model used to embed the documents. This is non-negotiable —
the query and document vectors must live in the same vector space.

```
query_text → [same embedding model] → query_vector
```

If query instructions are used (as with Qwen3-Embedding), wrap the query in the appropriate
instruction template before embedding. See [embedding-concepts.md](embedding-concepts.md).

### Step 3: Retrieve candidates

Search the index for the chunks most similar to the query vector. This has two sub-modes:

**Pure vector search:**
```
query_vector → ANN search → top-k chunks ranked by vector similarity
```

**Hybrid search (BM25 + vector):**
```
query_text   → BM25 search → lex_results (ranked by keyword relevance)
query_vector → ANN search  → vec_results (ranked by semantic similarity)
lex_results + vec_results   → RRF fusion → merged_results
```

Hybrid search consistently outperforms either modality alone, especially on:
- Queries with exact-match terms (version numbers, names, code identifiers)
- Queries where the vocabulary gap between query and document is small

### Step 4: Filter

Apply metadata filters to the candidate set:
- Date range ("only documents from the last 6 months")
- Source type ("only from the API documentation")
- Access control ("only documents this user can see")

Filtering is most efficient when done **during** ANN search (as supported by Qdrant and
MongoDB Atlas) rather than after (as in memvid). Post-filtering on a small top-k can
silently produce fewer results than requested if many candidates are filtered out.

### Step 5: Rerank (optional but recommended)

Pass the top candidates through a cross-encoder reranker to produce a more precise ordering.

```
(query, candidate_1) → [reranker] → 0.92
(query, candidate_2) → [reranker] → 0.87
(query, candidate_3) → [reranker] → 0.41
...
```

The reranker reads the query and each candidate together, producing a relevance score that
accounts for the full text interaction rather than vector proximity alone. See
[retrieval-concepts.md](retrieval-concepts.md) for the bi-encoder vs cross-encoder distinction.

Reranking is skipped when: latency is critical, the corpus is small enough that vector search
precision is already high, or no reranker model is available.

### Step 6: Assemble context

Select the top N chunks from the ranked candidates and concatenate them into a context block
for the LLM prompt.

**Context budget:** The LLM has a finite context window. The context block, system prompt,
user question, and expected answer all compete for that budget. A practical rule: reserve 30%
of the context window for the answer, 10% for the system prompt and question, 60% for
retrieved context.

**Ordering matters:** LLMs attend less reliably to content in the middle of long contexts
("lost in the middle" problem). Put the most relevant chunks first and last, not in the
middle.

**Attribution:** Include source metadata in the context block so the LLM can cite sources:

```
[Source: llama-server-cache-architecture-explainer.md, Section: KV Cache Mechanics]
The KV cache stores key and value tensors from previously processed tokens...

[Source: retrieval-concepts.md, Section: HNSW]
HNSW builds a multi-layer graph where each node is a document vector...
```

**Parent-child expansion:** If using parent-child chunking, swap retrieved child chunks for
their parent chunk at this step to give the LLM richer context.

### Step 7: Generate the answer

Construct the final prompt and call the LLM.

Typical prompt structure:
```
SYSTEM:
You are a helpful assistant. Answer questions using only the provided context.
If the context does not contain the answer, say so.

CONTEXT:
[assembled context block]

USER:
[original question]

ASSISTANT:
```

The system prompt should instruct the LLM to:
1. Use the provided context as the primary source
2. Acknowledge when the context does not contain the answer (rather than hallucinating)
3. Cite sources when the information is specific

### Query phase summary

```
[user question]
    │
    ▼
[query transformation?]  ←── HyDE, expansion, decomposition
    │
    ▼
[embed query]            ←── same model as indexing
    │
    ▼
[search index]           ←── vector, BM25, or hybrid
    │
    ▼
[filter]                 ←── metadata, date range, ACL
    │
    ▼
[rerank?]                ←── cross-encoder for precision
    │
    ▼
[assemble context]       ←── budget, ordering, attribution
    │
    ▼
[generate answer]        ←── LLM with context prompt
    │
    ▼
[response]
```

---

## Common failure modes

### Retrieval failures

**Symptom:** The LLM says "I don't know" but the answer is in the corpus.

Probable causes:
- Chunk boundary split the answer across two chunks; neither retrieved individually
- Query vocabulary doesn't match document vocabulary (semantic gap); try hybrid search or HyDE
- `top_k` too small; the right chunk is at rank 12 but only top 5 are retrieved
- Metadata filter too aggressive; filtered out the relevant chunk

**Symptom:** Retrieved chunks are consistently wrong (off-topic).

Probable causes:
- Chunks are too large; the relevant sentence is buried in an irrelevant chunk
- Embedding model is not well-suited to the domain; consider fine-tuning or a domain-specific model
- No reranker; vector proximity is imprecise for this query type

### Generation failures

**Symptom:** LLM ignores the context and answers from its parametric memory.

Probable causes:
- System prompt does not strongly instruct the model to use context
- Context block is too long; relevant chunks are in the "lost in the middle" zone
- Model temperature too high; try 0.0–0.3 for fact retrieval tasks

**Symptom:** LLM cites sources that are not in the context.

Probable causes:
- Model hallucinating citations; add explicit instruction "only cite sources from the provided context"
- Context metadata is missing or ambiguous; add clear source labels

### Indexing failures

**Symptom:** Re-indexing takes much longer than expected.

Probable causes:
- Embedding every chunk individually instead of batching
- No caching of embeddings for unchanged content

**Symptom:** Index quality degrades over time as documents are updated.

Probable causes:
- Stale vectors from old document versions still in the index
- Backend does not support correct deletions (see memvid HNSW limitation in
  [retrieval-backends.md](retrieval-backends.md))
- No mechanism to detect and re-embed changed content

---

## This repo's stack

In this repo, the RAG pipeline maps to the following components:

| Pipeline step | Component |
|---|---|
| Document ingestion | memvid readers (PDF, DOCX, XLSX) or direct `put_bytes()` |
| Chunking | memvid chunker (1,200 char, structure-aware) |
| Embedding | `llama-server --embedding` serving a GGUF embedding model, or OpenAI API |
| Storage | memvid `.mv2` file (vector + BM25 + metadata) |
| Query embedding | Same llama-server endpoint |
| Retrieval | memvid `ask()` — hybrid BM25 + vector with RRF |
| Reranking | Not yet integrated (planned: Qwen3-Reranker via llama-server) |
| Context assembly | memvid `AskResponse.context` field |
| Generation | llama-server chat completions or cloud provider via clawrouter |

The embedding model and generation model are served as separate llama-server instances.
Open WebUI routes embedding requests to the dedicated embeddings endpoint and generation
requests to the generation endpoint. clawrouter handles routing to local vs. cloud providers.
