# Retrieval Concepts

Reference for retrieval algorithms, index structures, and scoring mechanics.

Related documents:

- Embedding model evaluation and selection: [embedding-concepts.md](embedding-concepts.md)
- Storage backend comparison: [retrieval-backends.md](retrieval-backends.md)

---

## Retrieval Architectures

Embedding models can produce different kinds of representations. The architecture determines
what kind of index you build and how query-document similarity is computed.

### Dense retrieval

The standard approach. One vector per text.

```
query  → [single vector]
doc    → [single vector]
score  = dot_product(query_vec, doc_vec)
```

Fast at query time. Index is compact. Works well when queries and documents are semantically
similar in the embedding space.

Weakness: a single vector must compress all meaning. Queries that need to match multiple
distinct aspects of a document can lose signal.

### Sparse retrieval (SPLADE)

Instead of a dense vector, the model outputs a sparse weighted term vocabulary — like a
learned BM25.

```
query → {term: weight, term: weight, ...}  (most weights ~0)
doc   → {term: weight, term: weight, ...}
score = sum of overlapping weighted terms
```

Good at exact and near-exact term matching. Complements dense retrieval on queries where
lexical specificity matters (version numbers, proper nouns, code tokens).

BGE-M3 includes a sparse retrieval head alongside its dense head.

### ColBERT (multi-vector / late interaction)

ColBERT keeps one vector per token rather than collapsing to a single vector.

```
query: [what]  [is]  [the]  [capital]
          ↓      ↓     ↓       ↓
          q1     q2    q3      q4

doc:  [Paris] [is] [a] [city] [in] [France]
          ↓      ↓   ↓    ↓      ↓     ↓
          d1     d2  d3   d4     d5    d6
```

Similarity (MaxSim):

```
score = sum over each qi of: max(dot(qi, dj) for all dj)
```

Each query token independently finds its best matching document token, then scores are summed.

Why it matters:

- "bank of a river" and "bank loan" map to the same dense vector in ambiguous models; ColBERT
  keeps them distinct because `river` and `loan` match different document tokens
- multi-aspect queries ("fast AND cheap AND local") get each aspect separately matched rather
  than compressed into one average direction
- exact token sensitivity: "Python 3.11 migration" won't match a document about "Python 2.7"
  because `3.11` and `2.7` pull in different directions

Tradeoffs:

| | Dense | Sparse | ColBERT |
|---|---|---|---|
| Index size | small | medium | large (tokens × docs) |
| Query speed | very fast | fast | slower |
| Recall on complex queries | good | good for lexical | better |
| Typical use | first-stage retrieval | hybrid retrieval | reranking or dedicated index |

### Hybrid retrieval

Most production systems combine modes rather than choosing one:

1. Dense retrieval → top-k candidates (fast, high recall)
2. Sparse/ColBERT reranking → reorder top-k (slower, higher precision)

BGE-M3 is notable because it runs all three modes (dense, sparse, ColBERT) from a single set
of weights, making hybrid pipelines cheaper to operate than maintaining separate models.

---

## ANN — Approximate Nearest Neighbor Search

### The problem with exact search

Given a query vector and a corpus of N document vectors, exact nearest neighbor search
computes the distance between the query and every document, then sorts. This is O(N × d)
where d is the dimensionality. At 1M documents with 1536-dim vectors, that is ~1.5B float
multiplications per query — too slow for interactive use.

**ANN** trades a small amount of recall for a large speedup. Instead of finding the provably
closest k vectors, it finds a very-probably-close k with much less computation.

### HNSW (Hierarchical Navigable Small World)

The dominant ANN algorithm in production vector stores (Qdrant, pgvector, memvid, Weaviate).

The core idea: build a multi-layer graph where each node is a document vector. Upper layers
are sparse long-range connections (like highways); lower layers are dense local connections
(like local roads). At query time, navigate top-down from the sparse layer to the dense layer,
greedily following edges toward the query vector.

```
Layer 2 (sparse):  A ─────────────────── E
Layer 1 (medium):  A ──── B ──── D ───── E
Layer 0 (dense):   A ─ B ─ C ─ D ─ E ─ F ─ G
                               ↑
                           query lands here
```

Key parameters:

| Parameter | What it controls | Typical value |
|---|---|---|
| `M` | Max edges per node per layer. Higher = better recall, larger index | 16 |
| `ef_construction` | Candidate pool size during build. Higher = better graph quality, slower build | 200 |
| `ef` (search) | Candidate pool size during query. Higher = better recall, slower query | 50–200 |

memvid hardcodes M=16, ef_construction=200 with no runtime override. Qdrant and pgvector
expose these as configurable at index creation time.

**Recall vs. speed trade-off:** HNSW at ef=50 typically achieves 95–99% recall@10 (meaning
95–99% of the true top-10 nearest neighbors are in the returned set) at 10–100× the speed of
brute-force scan. Raising ef improves recall at the cost of latency.

**Memory requirement:** HNSW graphs are in-memory structures. At 1536 dims × float32 × 1M
vectors = ~6GB just for raw vectors, plus graph overhead. This is the primary scaling ceiling
for memvid and pgvector — they are RAM-bound. Qdrant and LanceDB use disk-based HNSW with
memory-mapped pages.

### Flat scan (brute force)

At small scale (< ~10k vectors), linear scan with SIMD-accelerated distance computation is
often faster than HNSW because there is no graph traversal overhead. memvid uses flat scan
below 1,000 vectors. Most vector DBs also fall back to exact scan at small collection sizes.

### IVFFlat (Inverted File)

An older algorithm used in Faiss and pgvector. Clusters vectors into `nlist` Voronoi cells
during build. At query time, only searches the `nprobe` nearest cells. Faster to build than
HNSW, less memory, but lower recall at the same speed.

pgvector supports both IVFFlat and HNSW. HNSW is generally preferred for recall quality;
IVFFlat is useful when build time or memory is the constraint.

### Product Quantization (PQ)

PQ compresses vectors to reduce memory. The vector space is split into M subspaces; each
subspace is quantized to one of k centroids. A 1536-dim float32 vector (6,144 bytes) can be
compressed to M bytes (one centroid ID per subspace).

memvid's PQ96 splits into 96 subspaces × 256 centroids of 4 dims each → 96 bytes per vector
(64× compression of the quantized portion). Search uses Asymmetric Distance Computation (ADC)
with lookup tables — the query is not quantized, only the stored vectors are.

Trade-off: PQ degrades recall compared to exact vectors. The more aggressive the compression,
the larger the recall loss. PQ is typically combined with HNSW: HNSW navigates the graph,
distances are computed via ADC.

Qdrant's scalar quantization (SQ8) is a simpler alternative — quantize each dimension from
float32 to int8 (4× compression, lower recall loss than PQ).

---

## Ranking vs Re-ranking

This distinction is one of the most important things to understand when choosing an embedding
stack.

### Ranking

Ranking is the initial ordering produced by the retriever.

In an embedding pipeline, the usual process is:

1. embed the query
2. embed all documents or chunks ahead of time
3. compute similarity
4. return the top `k` nearest items

This stage is fast, scalable, and approximate.

Why it is fast: document embeddings are precomputed; nearest-neighbor search can be indexed
efficiently.

Why it is approximate: the retriever compares fixed vectors, not full query-document reasoning.

### Re-ranking

Re-ranking is a second pass over the candidate set returned by the retriever.

Typical process:

1. retriever returns top 20, 50, or 100 candidates
2. reranker reads the query plus each candidate together
3. reranker assigns a more exact relevance score
4. candidates are reordered before being passed to generation

This stage is slower, more expensive, and usually more accurate, because the reranker can
reason over the direct query-document interaction rather than coarse vector proximity.

### Why not rerank everything

Reranking does not scale to a large corpus. If you have 1M chunks, you can vector-search them
efficiently, but you do not want to run a cross-encoder reranker over all 1M. So the pattern
is: retrieve broadly, rerank narrowly.

### Practical retrieval stack

A strong modern local retrieval stack:

1. Embedding model generates query and document vectors
2. ANN index (HNSW or similar) returns top 20–100 candidates
3. Reranker rescoring narrows to best top 5–10
4. Only the highest-ranked chunks go into the final LLM prompt

### What each model is optimizing for

| Stage | Goal |
|---|---|
| Embedding model | Maximize semantic recall at scale; good-enough ranking |
| Reranker | Maximize precision at the top of the list |

Embedding and reranking scores should not be treated as interchangeable.

Source annotations:
- Qwen retrieval stack framing: https://huggingface.co/Qwen/Qwen3-Embedding-4B-GGUF
- Retrieval-benchmark framing: https://huggingface.co/blog/rteb

---

## BM25 (Best Match 25)

BM25 is the dominant full-text ranking algorithm used in search engines (Elasticsearch,
Lucene, Solr, Tantivy). It scores documents against a query based on term frequency and
inverse document frequency with saturation corrections:

```
score(D, Q) = sum over query terms t of:
  IDF(t) * (tf(t,D) * (k1 + 1)) / (tf(t,D) + k1 * (1 - b + b * |D| / avgdl))
```

Where:
- `tf(t, D)` — how many times term `t` appears in document `D`
- `IDF(t)` — how rare the term is across all documents (log-scaled)
- `k1` — term frequency saturation (typically 1.2–2.0); prevents a term appearing 100× from
  dominating
- `b` — length normalization (typically 0.75); penalizes long documents
- `avgdl` — average document length in the corpus

**Why BM25 matters for RAG:** Vector search finds semantically similar content but can miss
exact keyword matches (names, version numbers, code identifiers, rare technical terms). BM25
excels at exact match and rare term recall. Hybrid search combines both.

Implementation notes: memvid uses Tantivy's BM25. MongoDB Atlas Search uses Lucene's. Qdrant
uses FastEmbed's sparse encoding which approximates BM25.

---

## RRF (Reciprocal Rank Fusion)

When you run both BM25 and vector search on the same query, you get two ranked lists. The
lists contain overlapping but not identical results with incomparable scores (BM25 scores are
not in the same range as cosine similarity values).

RRF merges them by rank position, not by raw score:

```
RRF_score(doc) = sum over each ranked list L of:
  1 / (k + rank_in_L(doc))
```

Where `k` is a constant (typically 60). The `k` value dampens the advantage of rank 1 over
rank 2 — it prevents a single list from dominating just because one result was ranked first.

Example with k=60 and two lists:

```
doc A: rank 1 in BM25, rank 4 in vector  → 1/61 + 1/64 = 0.0321
doc B: rank 2 in BM25, rank 2 in vector  → 1/62 + 1/62 = 0.0323
doc C: rank 1 in vector, not in BM25     → 0    + 1/61 = 0.0164
```

Doc B wins because consistent top performance across both lists beats a single dominant rank.
Doc C is penalized for appearing in only one list.

RRF requires no calibration of score scales across different retrieval systems — only ranks
matter. This makes it robust for combining any retrieval methods without normalization.

---

## L2 Distance (Euclidean Distance)

L2 distance measures the straight-line distance between two points in vector space:

```
L2(a, b) = sqrt( sum_i (a_i - b_i)^2 )
```

For embedding search, a smaller L2 distance means the vectors are more similar.

Some backends convert L2 to a similarity score via `similarity = 1.0 - distance`. This only
makes sense when vectors are L2-normalized (unit length), because on the unit hypersphere L2
distance and cosine distance are monotonically related:

```
L2(a, b)^2 = 2 * (1 - cosine_similarity(a, b))
```

If vectors are not normalized, `1.0 - L2_distance` produces incorrect similarity scores —
values can go negative, and the scale is arbitrary. Callers must normalize embeddings before
storing them if they want cosine-equivalent ranking from L2 search.

**Cosine similarity** is what most embedding models are trained with. It measures the angle
between vectors regardless of magnitude. For retrieval, cosine and dot product are equivalent
on normalized vectors. Most backends (Qdrant, MongoDB Atlas) expose the distance metric as a
first-class parameter; memvid hardcodes L2.

---

## Elbow Cutoff (Score Cliff Detection)

When an ANN search returns a ranked list of results, not all of them are useful. The score
distribution typically looks like:

```
rank:  1     2     3     4     5     6     7     8
score: 0.91  0.88  0.86  0.85  0.51  0.49  0.47  0.44
```

There is a sharp drop between rank 4 and rank 5. Everything from rank 5 onward is a different
cluster of relevance — probably noise or tangentially related documents.

The **elbow** (or cliff) is that drop point. Rather than returning a fixed `top_k`, adaptive
retrieval detects where the score curve bends sharply and truncates there.

The motivation is that `top_k` is a blunt instrument. A query that matches 3 highly relevant
documents should not be forced to return 10. A query that matches 20 equally-good documents
should not be truncated at 3. Adaptive cutoff adjusts dynamically.

Common cutoff strategies (as implemented in memvid's `AdaptiveConfig`):

- `AbsoluteThreshold` — drop everything below a fixed score (e.g., 0.6)
- `RelativeThreshold` — drop everything below `ratio × top_score` (e.g., 0.5 × 0.91 = 0.455)
- `ScoreCliff` — stop when the score drops more than X% from the previous result
- `Elbow` — automatic knee-detection in the score curve (derivative-based)
- `Combined` — run multiple strategies; first one to trigger wins

---

## SPO (Subject-Predicate-Object) and Entity Graphs

**SPO triplets** are a way to represent facts as structured relationships:

```
Subject        Predicate       Object
───────────    ─────────────   ──────────────
Alice          works_at        Acme Corp
Bob            lives_in        San Francisco
project-X      depends_on      library-Y
```

SPO extraction parses free text and produces a graph of entities and their relationships.
In retrieval systems, this enables queries that pure vector search cannot handle well:

- "who works at Acme Corp" — entity lookup, not semantic similarity
- "what does project-X depend on" — graph traversal
- "find all relationships involving Alice" — entity-centric search

**MemoryCards** (as implemented in memvid) are typed records built on top of SPO:

- `Fact` — a general assertion ("Paris is the capital of France")
- `Preference` — a user preference ("user prefers dark mode")
- `Event` — a timestamped occurrence ("meeting with Alice on 2026-03-15")
- `Relationship` — a link between entities ("Alice reports to Bob")

In agent memory systems, the SPO graph complements vector search: vector search finds
semantically similar content, graph search finds structured facts about known entities.
