# Chunking Strategies

Chunking is the process of splitting documents into smaller pieces before embedding and
indexing. It is one of the highest-leverage decisions in a RAG system — more so than model
choice in many cases. Poor chunking degrades retrieval quality regardless of how good the
embedding model is.

Related documents:

- Why chunks need to be embedded: [foundations-what-is-an-embedding.md](foundations-what-is-an-embedding.md)
- How chunks are indexed: [retrieval-concepts.md](retrieval-concepts.md)
- How memvid implements chunking: [retrieval-backends.md](retrieval-backends.md)

---

## Why chunk at all?

Two reasons force chunking:

**1. Token limits.** Embedding models have a maximum input length (typically 512–8,192
tokens). A document longer than that limit must be split before it can be embedded. Truncation
is the naive alternative — it silently discards everything past the limit.

**2. Retrieval precision.** A vector representing a 20,000-word document compresses too much
information into one point. When you retrieve that document in response to a specific question,
most of its content is irrelevant to the query. The retrieved context sent to the LLM is bloated
with noise.

Chunking trades recall (a whole document contains the answer somewhere) for precision (the
specific chunk most relevant to the query is returned).

### When not to chunk

Long-context generative models (Gemini 2.0, Claude with 200K context) can ingest entire
documents. If the corpus is small enough that all documents fit in the model's context window,
chunking adds complexity without benefit — you can just stuff all documents into the prompt.

Chunking makes sense when: the corpus is too large to fit in one prompt, retrieval must
select relevant content from many documents, or the LLM context budget is constrained.

---

## The chunk size tradeoff

Chunk size is the central tuning parameter:

| Smaller chunks | Larger chunks |
|---|---|
| Higher retrieval precision (more targeted match) | Higher recall (answer less likely to be cut across a boundary) |
| Less context per retrieved chunk → LLM has less to work with | More context per chunk → LLM gets richer surrounding text |
| More chunks to index and store | Fewer chunks, smaller index |
| Better for fact lookup, Q&A | Better for synthesis, summarization |
| Risk: answer split across chunk boundary | Risk: irrelevant content dilutes the chunk |

Typical defaults by use case:

| Use case | Chunk size |
|---|---|
| Q&A over technical docs | 256–512 tokens |
| General knowledge retrieval | 512–1024 tokens |
| Long-form synthesis | 1024–2048 tokens |
| Code retrieval | Function/class boundary (variable) |

There is no universal optimal. Test on representative queries from your domain.

---

## Strategy 1: Fixed-size chunking

Split every N characters (or tokens), regardless of content boundaries.

```
document = "The model uses attention mechanisms. Attention allows..."

chunk 1 = "The model uses attention mec"   ← breaks mid-word
chunk 2 = "hanisms. Attention allows..."
```

**Advantage:** Simple. Predictable chunk sizes. Easy to implement.

**Disadvantage:** Breaks at arbitrary points — mid-sentence, mid-word, mid-concept. The
chunks at split boundaries are incoherent.

Fixed-size chunking without overlap is rarely useful in practice.

---

## Strategy 2: Fixed-size with overlap

Like fixed-size, but each chunk shares some content with the previous and next chunk.

```
chunk_size = 500 tokens
overlap    = 100 tokens

chunk 1: tokens 0–499
chunk 2: tokens 400–899    ← shares 100 tokens with chunk 1
chunk 3: tokens 800–1299   ← shares 100 tokens with chunk 2
```

**Why overlap exists:** If the relevant answer spans a chunk boundary, overlap ensures the
answer appears whole in at least one chunk. Without overlap, a sentence split at the boundary
would be partially in chunk N and partially in chunk N+1, and neither chunk would retrieve
well.

**Disadvantage:** Increases index size (proportional to overlap fraction). Same content
appears multiple times in search results, requiring deduplication.

**Typical overlap:** 10–20% of chunk size. Higher overlap for fine-grained Q&A; lower for
storage-constrained deployments.

---

## Strategy 3: Sentence-boundary chunking

Accumulate text until reaching the size target, but only split at sentence boundaries (`.`,
`!`, `?`, paragraph breaks).

```
target = 400 tokens

chunk 1: [sentence 1] [sentence 2] [sentence 3]   → 395 tokens
chunk 2: [sentence 4] [sentence 5]                → 410 tokens
chunk 3: [sentence 6] [sentence 7] [sentence 8]   → 388 tokens
```

**Advantage:** Each chunk is semantically coherent. No broken sentences. Better embedding
quality because the model receives grammatically complete input.

**Disadvantage:** Chunk sizes vary. A single very long sentence can exceed the target.
Requires a sentence tokenizer (spaCy, NLTK, or heuristic regex).

This is the preferred baseline for most RAG systems. memvid approximates this with its
"natural breakpoint" look-ahead (finding sentence/paragraph endings near the target boundary).

---

## Strategy 4: Recursive character splitting

Split on the most natural boundary available, falling back to coarser splits only when
necessary.

```
Priority order: paragraph → sentence → word → character

1. Try splitting on "\n\n" (paragraph breaks)
2. If any resulting chunk is too large, split that chunk on ". " (sentences)
3. If still too large, split on " " (words)
4. If still too large, split on "" (characters)
```

This is the default strategy in LangChain and LlamaIndex. It preserves document structure
when possible and only resorts to arbitrary splits when forced.

**Advantage:** Produces coherent chunks across a wide range of document types without
per-format configuration.

**Disadvantage:** Chunk size is still ultimately bounded by a character/token target, which
can break logical units (a numbered list, a table row, a code block).

---

## Strategy 5: Structure-aware chunking

Use knowledge of the document's format to split on meaningful boundaries:

- **Markdown**: split on headers (`##`, `###`), preserve fenced code blocks and tables whole
- **HTML**: split on `<section>`, `<article>`, `<h2>` tags
- **PDF with structure**: split on section headers extracted from the PDF outline
- **Code**: split on function/class definitions, not arbitrary line counts
- **Tables**: keep each row (or the whole table) as a unit; propagate headers to every chunk

**Advantage:** Chunks align with the document's own logical structure. A chunk about "HNSW
parameters" starts and ends at the section boundary, not mid-sentence in the middle of a
table.

**Disadvantage:** Requires a parser per document type. Section-level chunks can be very long
or very short depending on the document.

memvid activates structure-aware mode when it detects Markdown tables or code fences,
propagating table headers to continuation chunks.

---

## Strategy 6: Semantic chunking

Split based on **topic shift** rather than size targets. Embed each sentence, compute
cosine similarity between adjacent sentence vectors, and insert a chunk boundary where
similarity drops sharply (a semantic "cliff").

```
sentence 1 → vector
sentence 2 → vector  similarity(1,2) = 0.92  → no split
sentence 3 → vector  similarity(2,3) = 0.89  → no split
sentence 4 → vector  similarity(3,4) = 0.41  → SPLIT HERE
sentence 5 → vector  similarity(4,5) = 0.88  → no split
```

**Advantage:** Chunk boundaries align with actual topic transitions. Each chunk has a single
coherent topic. Retrieval precision improves because retrieved chunks contain less off-topic
content.

**Disadvantage:** Requires running the embedding model during indexing (not just at query
time). Chunk sizes are unpredictable. Topic shifts within a long sentence are not detected.

Semantic chunking is most valuable for long, multi-topic documents (books, reports, wikis).
For short uniform documents (product descriptions, Q&A pairs) it adds cost without benefit.

---

## Strategy 7: Parent-child (small-to-big) chunking

Index small chunks for retrieval precision, but return the larger parent chunk to the LLM for
context richness.

```
Parent chunk:  full section (1200 tokens)  ← not directly indexed
Child chunks:  each paragraph (~200 tokens) ← these are embedded and indexed

Query → retrieve child chunks → return their parent to the LLM
```

**Why this works:** Small child chunks match queries precisely (embedding a 200-token paragraph
captures its topic tightly). But the LLM benefits from the broader context of the parent
section, which includes surrounding sentences that explain the child chunk.

**Variants:**
- Sentence → paragraph (retrieve sentences, return paragraphs)
- Paragraph → section (retrieve paragraphs, return sections)
- Chunk → full document (retrieve chunks, return whole document)

memvid implements this: `FrameRole::DocumentChunk` for child chunks, `FrameRole::Document`
for the parent, linked by `parent_id`.

**Disadvantage:** Doubles the storage (parent and child both stored). The parent context may
still include irrelevant content. Works best when document sections have natural boundaries.

---

## Strategy 8: Late chunking

An emerging strategy for ColBERT-style models. Rather than chunking before embedding, embed
the whole document and then extract chunk-level embeddings from the token-level outputs.

```
Document → [embedding model] → token vectors (one per token)
                              → pool each chunk's token range into one vector
```

This preserves full document context during embedding (each token sees the whole document)
while still producing chunk-level vectors for retrieval.

**Advantage:** Eliminates boundary artifacts — a sentence at the start of the document has
the same embedding quality as one in the middle. No information loss from chunking before
encoding.

**Disadvantage:** Requires a model that exposes token-level outputs (ColBERT-style or the
raw transformer outputs). Not supported by the standard OpenAI-compatible embeddings API.
Currently experimental.

---

## Overlap and its tradeoffs in depth

Overlap is a cost-quality trade-off:

```
100 chunks with 0% overlap  → 100 vectors, 100× storage
100 chunks with 20% overlap → ~125 vectors, 25% more storage
100 chunks with 50% overlap → ~200 vectors, 2× storage
```

At query time, overlapping chunks create duplicate results. If chunk 5 (tokens 400–899) and
chunk 4 (tokens 0–499) both contain the answer, both may be retrieved and passed to the LLM
— wasting context budget on repeated content. Deduplication (by `parent_id` or content hash)
is required.

Rule of thumb: start with 20% overlap. Reduce if index size is a concern. Increase if
questions frequently reference content near chunk boundaries.

---

## Metadata and chunk context

A retrieved chunk is more useful to the LLM when it carries context about where it came from:

```json
{
  "chunk_id": "doc-42-chunk-7",
  "parent_doc": "llama-server-cache-architecture-explainer.md",
  "section": "KV Cache Mechanics",
  "page": 3,
  "text": "The KV cache stores key and value tensors..."
}
```

Without source metadata, the LLM cannot cite the source or distinguish between conflicting
chunks from different documents.

Minimum useful metadata per chunk:
- Source document identifier (path, URI, or title)
- Section heading (if available)
- Creation or modification date (for recency-sensitive queries)
- Chunk position (paragraph number, page number) for reconstructing order

---

## How memvid handles chunking

memvid's chunking implementation (`src/memvid/chunks.rs`):

- Default: 1,200-character chunks with ±240-char look-ahead for natural breakpoints
- Documents under 2,400 chars are not chunked
- Structure-aware mode activates on detection of Markdown tables (`| ... |`) or code fences
- Tables: splits between rows, propagates headers to continuation chunks
- Code: keeps fenced blocks whole where possible
- Parent-child: `FrameRole::Document` links to `FrameRole::DocumentChunk` children via
  `parent_id`; `TextChunkManifest` records each child's `(start, end)` character range

Gaps: no overlap, no semantic chunking, no sentence-boundary splitting (heuristic only),
no recursive character fallback. These are reasonable defaults for a general-purpose embedded
store but may need supplementing for domain-specific corpora.

---

## Practical checklist

When designing a chunking strategy:

1. **Know your documents.** Short uniform records (product descriptions) behave differently
   from long heterogeneous documents (research papers). Sample 20–30 representative documents
   before choosing a strategy.

2. **Know your queries.** Fact-lookup queries ("what is the default chunk size in memvid?")
   benefit from small precise chunks. Synthesis queries ("summarize the tradeoffs of HNSW")
   benefit from larger chunks.

3. **Start simple.** Sentence-boundary chunks with 15% overlap is a good default. Measure
   retrieval quality before adding complexity.

4. **Measure chunk size distribution.** Check the p50, p95, and max chunk sizes. Outliers
   (single-sentence chunks, oversized sections) degrade retrieval differently than average
   chunks.

5. **Always store metadata.** At minimum: source, section, date. This is cheap to add and
   expensive to reconstruct later.

6. **Plan for re-chunking.** When you change chunking strategy or embedding model, the entire
   index must be rebuilt. Design ingestion pipelines so re-chunking is not a one-time manual
   operation.
