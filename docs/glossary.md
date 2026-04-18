# Glossary

Definitions for terms used across the embedding and retrieval documentation. Terms in
**bold** within a definition are themselves defined in this glossary.

---

## A

**ANN (Approximate Nearest Neighbor)**
A family of algorithms that find vectors close to a query vector without checking every
vector in the index. Trades a small amount of recall for large speedups over exact search.
Common algorithms: **HNSW**, **IVFFlat**. See [retrieval-concepts.md](retrieval-concepts.md).

**Asymmetric Distance Computation (ADC)**
A technique used with **Product Quantization** where the query vector is kept in full
precision but stored document vectors are quantized. The query is compared against lookup
tables of centroid distances rather than individual quantized vectors directly.

**Attention (self-attention)**
The core mechanism in transformer models. Each token in the input attends to (is influenced
by) all other tokens, weighted by learned relevance scores. Enables context-sensitive
representations: the same word gets different vectors depending on surrounding text.

---

## B

**Bi-encoder**
A retrieval architecture where query and document are encoded **independently** by the same
or compatible models, producing separate vectors. Similarity is computed between the two
vectors. Fast because document vectors can be precomputed. Contrast with **cross-encoder**.
See [foundations-what-is-an-embedding.md](foundations-what-is-an-embedding.md).

**BM25 (Best Match 25)**
A full-text ranking algorithm based on term frequency (**TF**), inverse document frequency
(**IDF**), and document length normalization. The standard algorithm behind Elasticsearch,
Lucene, Solr, and Tantivy. Excels at exact keyword matching and rare term retrieval. Contrast
with **dense retrieval** for semantic matching.
See [retrieval-concepts.md](retrieval-concepts.md).

**BPE (Byte Pair Encoding)**
A **tokenization** algorithm that iteratively merges the most frequent adjacent byte pairs
into a single token. Used by GPT-2, GPT-3, GPT-4, and most modern LLMs. Produces subword
tokens that balance vocabulary size against coverage of rare words.

---

## C

**Candidate pool**
The set of results returned by the first-stage retriever before reranking or filtering.
Larger candidate pools improve recall at the cost of more reranker inference.

**Chunking**
Splitting a document into smaller pieces before embedding and indexing. Necessary because
embedding models have token limits and because smaller chunks improve retrieval precision.
See [chunking-strategies.md](chunking-strategies.md).

**Chunk overlap**
The number of tokens or characters shared between adjacent chunks. Prevents answers from
being split across chunk boundaries. Typical range: 10–20% of chunk size.

**CLS token**
A special `[CLS]` token prepended to input in BERT-style models. The vector at this position
after encoding is commonly used as the sentence-level representation (**CLS pooling**).

**ColBERT**
A retrieval model that keeps one vector per token rather than collapsing to a single vector.
Similarity is computed via **MaxSim**: each query token finds its best-matching document
token. Higher recall on complex queries than single-vector models; larger index.
See [retrieval-concepts.md](retrieval-concepts.md).

**Contrastive learning**
A training objective where the model learns to bring similar examples close together and push
dissimilar examples apart in vector space. The dominant training approach for modern embedding
models. Uses **(anchor, positive, negative)** triplets.
See [foundations-what-is-an-embedding.md](foundations-what-is-an-embedding.md).

**Context window**
The maximum number of tokens a model can process in one forward pass. For generation models,
this limits the total input (system prompt + conversation + retrieved context + expected
output). For embedding models, this limits the maximum input text per embedding call.

**Cosine similarity**
A distance metric measuring the angle between two vectors, regardless of their magnitude.
Values range from -1 (opposite directions) to 1 (same direction). The standard metric for
most embedding models. Equivalent to **dot product** on unit-normalized vectors.

**Cross-encoder**
A model that reads query and document **together** as a single input, producing a single
relevance score. More accurate than **bi-encoders** because it can reason over query-document
interaction. Slower because it cannot precompute document representations.
Used as a **reranker** after first-stage retrieval.

---

## D

**Dense retrieval**
Retrieval using a single continuous vector per text. Query and document vectors are compared
by **cosine similarity** or **dot product**. Contrast with **sparse retrieval** and
**ColBERT**. See [retrieval-concepts.md](retrieval-concepts.md).

**Dimensionality**
The number of values in an embedding vector (e.g., 384, 768, 1536, 3072). Higher
dimensionality generally encodes more information but increases storage and computation.

**Dimensionality reduction**
Truncating an embedding vector to fewer dimensions while preserving most semantic signal.
Supported by `text-embedding-3-small` and `text-embedding-3-large` via the `dimensions`
parameter. Not available on `text-embedding-ada-002`.

**Distance metric**
A function measuring how far apart two vectors are. Common metrics: **L2 (Euclidean)**,
**cosine similarity**, **dot product**. The choice of metric must match how the embedding
model was trained.

**Dot product**
The sum of element-wise products of two vectors: `sum(a_i * b_i)`. Equivalent to cosine
similarity when vectors are unit-normalized. Some models are trained to maximize dot product
rather than cosine similarity — these should not be L2-normalized before storage.

---

## E

**ef (HNSW search parameter)**
The candidate pool size used during **HNSW** search. Higher ef = better recall, slower query.
Tunable at query time without rebuilding the index. Contrast with `ef_construction`.

**ef_construction (HNSW build parameter)**
The candidate pool size used during **HNSW** index construction. Higher ef_construction =
better graph quality, slower build. Fixed at index creation; cannot be changed without
rebuilding.

**Elbow cutoff**
An adaptive result truncation strategy that detects the point where retrieval scores drop
sharply (the "cliff") and returns only results above that point rather than a fixed top-k.
See [retrieval-concepts.md](retrieval-concepts.md).

**Embedding**
A fixed-size vector of floating-point numbers representing the semantic content of a text.
Produced by an embedding model. Similar texts produce similar vectors (close together in
vector space). See [foundations-what-is-an-embedding.md](foundations-what-is-an-embedding.md).

**Embedding model**
A model that maps text to a fixed-size vector. Trained with **contrastive learning** on
(anchor, positive, negative) triplets. Produces representations for retrieval, not text.
Contrast with **generative model**.

---

## F

**Faithfulness**
A RAG evaluation metric measuring whether the generated answer is supported by the retrieved
context, without introducing unsupported claims. High faithfulness = low hallucination.

**Fine-tuning (embedding)**
Continuing training of a pretrained embedding model on domain-specific data to improve
performance on in-domain queries. Uses the same contrastive objective as pretraining, with
domain-specific (query, positive, hard negative) triplets.

---

## G

**Generative model**
A model that produces text as output (LLM, chat model). Contrast with **embedding model**.
Uses autoregressive decoding: generates one token at a time, each conditioned on all previous
tokens. Inference cost scales with output length.

**GGUF**
A binary file format for quantized model weights, used by llama.cpp and llama-server. Enables
running large models on consumer hardware by reducing precision (e.g., Q4_K_M, Q8_0).

---

## H

**Hard negative**
A training example that appears relevant to the query but is actually not the correct match.
Hard negatives force the embedding model to learn fine-grained distinctions. Critical for
training high-quality embedding models.

**Hit rate**
A RAG evaluation metric measuring the fraction of queries for which the correct document or
chunk appears anywhere in the top-k retrieved results. Hit rate at k=5 = correct answer found
in the top 5 retrieved chunks.

**HNSW (Hierarchical Navigable Small World)**
The dominant **ANN** algorithm. Builds a multi-layer graph of vectors; upper layers are
sparse for long-range navigation, lower layers are dense for local search. Fast at query time;
memory-intensive (held in RAM). Key parameters: M, ef_construction, ef.
See [retrieval-concepts.md](retrieval-concepts.md).

**HyDE (Hypothetical Document Embedding)**
A query transformation technique: ask an LLM to write a hypothetical document that would
answer the question, then embed that document as the query vector. Bridges the vocabulary gap
between short queries and long documents.

**Hybrid search**
Combining multiple retrieval modalities (typically **BM25** and **dense retrieval**) and
fusing the results with **RRF** or other merging strategies. Consistently outperforms either
modality alone. See [retrieval-concepts.md](retrieval-concepts.md).

---

## I

**IDF (Inverse Document Frequency)**
A component of **BM25** that weights rare terms more heavily than common terms.
`IDF(t) = log((N - df(t) + 0.5) / (df(t) + 0.5))` where N is the document count and df(t)
is the number of documents containing term t.

**IVFFlat (Inverted File)**
An **ANN** algorithm that clusters vectors into Voronoi cells and searches only the nearest
cells at query time. Faster to build than **HNSW**, lower recall at the same speed. Used in
Faiss and pgvector.

---

## K

**k (RRF constant)**
The constant in **RRF** scoring (`1 / (k + rank)`). Dampens the advantage of rank 1 over
rank 2. Typical value: 60. Higher k = more equal weighting across ranks.

**k1 (BM25 parameter)**
Term frequency saturation constant in **BM25**. Controls how much weight additional
occurrences of a term add. Typical value: 1.2–2.0. Higher k1 = more weight to term frequency.

**KV cache**
In generation models: stored key and value tensors from previously processed tokens, enabling
efficient autoregressive generation without recomputing attention over the entire context.
Not directly related to vector embedding, but affects inference throughput.
See [llama-server-cache-architecture-explainer.md](llama-server-cache-architecture-explainer.md).

---

## L

**L2 distance (Euclidean distance)**
Straight-line distance between two vectors: `sqrt(sum_i (a_i - b_i)^2)`. Smaller = more
similar. Equivalent to cosine distance on unit-normalized vectors.
See [retrieval-concepts.md](retrieval-concepts.md).

**Late chunking**
Embedding the full document first to preserve context, then extracting chunk-level vectors
from the token-level outputs. Avoids boundary artifacts. Requires token-level model outputs.

**Late interaction**
The scoring mechanism used by **ColBERT**: query and document vectors interact at query time
(not at indexing time). The model stores per-token vectors but delays the similarity
computation until the query is known.

**Latent space**
Another term for the high-dimensional vector space produced by an embedding model. Each point
in latent space represents a text's position in the learned semantic geometry.

---

## M

**M (HNSW parameter)**
The maximum number of edges per node per layer in an **HNSW** graph. Higher M = better recall,
larger index, slower build. Typical value: 16.

**MAP (Mean Average Precision)**
A retrieval metric averaging precision across all relevant documents for a query. More
sensitive to recall than **nDCG**. Common in MTEB benchmarks.

**MaxSim**
The **ColBERT** scoring function: for each query token, find the maximum similarity with any
document token. Sum these per-query-token maxima.

**Mean pooling**
A **pooling** strategy that averages all token vectors from an encoder's output into a single
vector. The most common pooling for embedding models.

**MemoryCard**
A typed fact record in memvid's memory system. Types: Fact, Preference, Event, Relationship.
Built on top of **SPO** triplets. See [retrieval-backends.md](retrieval-backends.md).

**MTEB (Massive Text Embedding Benchmark)**
The primary benchmark suite for evaluating embedding models across multiple task types
(retrieval, classification, clustering, reranking, STS). High MTEB scores may reflect
benchmark proximity rather than out-of-distribution generalization.
See [embedding-concepts.md](embedding-concepts.md).

---

## N

**nDCG (Normalized Discounted Cumulative Gain)**
The primary metric in most retrieval benchmarks. Measures ranking quality: highly relevant
documents appearing earlier receive higher scores. `nDCG@10` = nDCG considering only the top
10 results. Values range from 0 to 1; 1 = perfect ranking.

**Normalization (vector)**
Scaling a vector to unit length: `v_normalized = v / ||v||`. After normalization, **cosine
similarity** equals **dot product**. Many embedding models require normalization before
storage; check the model card. See [foundations-what-is-an-embedding.md](foundations-what-is-an-embedding.md).

---

## O

**ONNX (Open Neural Network Exchange)**
A standard format for ML model weights that enables running models without the original
training framework. Used by memvid for local embedding inference via the ONNX Runtime.

**Overlap**
See **chunk overlap**.

---

## P

**Parent-child chunking**
A chunking strategy where small chunks (children) are indexed for retrieval precision but
the larger surrounding chunk (parent) is returned to the LLM for context richness.
See [chunking-strategies.md](chunking-strategies.md).

**Pooling**
The step that collapses per-token vectors from a transformer encoder into a single
document-level vector. Common strategies: **mean pooling**, **CLS pooling**, last-token
pooling. The pooling strategy is part of the model contract and must match what the model was
trained with. See [foundations-what-is-an-embedding.md](foundations-what-is-an-embedding.md).

**PQ (Product Quantization)**
A vector compression technique that splits each vector into M subspaces and quantizes each
subspace to one of k centroids. Reduces storage by 4–64× at the cost of some recall. Used in
Faiss, memvid (PQ96), and optionally in Qdrant.
See [retrieval-concepts.md](retrieval-concepts.md).

**Precision@k**
The fraction of top-k retrieved results that are relevant. High precision = few irrelevant
results in the top k. Contrast with **Recall@k**.

**Prompt caching**
Reusing KV cache from a previously processed prefix in the prompt. Reduces inference cost
when the same system prompt or context is reused across many queries.

---

## Q

**Query instruction**
A task-specific prefix added to the query before embedding (e.g., "Represent this question
for retrieving relevant answers: "). Improves retrieval quality by 1–5% on models trained
with instructions (Qwen3, nomic-embed-text).
See [embedding-concepts.md](embedding-concepts.md).

**Query transformation**
Modifying the raw query before retrieval to improve recall or precision. Techniques: **HyDE**,
query expansion, sub-question decomposition.

---

## R

**RAG (Retrieval-Augmented Generation)**
A pattern combining retrieval (finding relevant documents) with generation (producing an
answer). The LLM generates answers conditioned on retrieved context rather than relying
solely on parametric memory. See [rag-pipeline.md](rag-pipeline.md).

**Recall@k**
The fraction of all relevant documents that appear in the top-k retrieved results. High
recall = few relevant documents missed. Contrast with **Precision@k**.

**Reranker**
A **cross-encoder** model used as a second pass over candidates returned by first-stage
retrieval. Produces more accurate relevance scores by reading query and document together.
Slower than the first-stage retriever; applied to a small candidate pool (20–100 items).

**RRF (Reciprocal Rank Fusion)**
A method for merging multiple ranked result lists by position rather than score. Each result
scores `sum over lists of 1 / (k + rank_in_list)`. Requires no score normalization.
See [retrieval-concepts.md](retrieval-concepts.md).

**RTEB (Retrieval Text Embedding Benchmark)**
A benchmark designed to test embedding models on retrieval-specific tasks with held-out
evaluation datasets not seen during training. Intended to detect benchmark overfitting.
See [embedding-concepts.md](embedding-concepts.md).

---

## S

**Scalar quantization (SQ8)**
A vector compression technique that quantizes each float32 dimension to int8 (4× compression).
Simpler and less aggressive than **PQ**; lower recall loss. Supported by Qdrant.

**Semantic chunking**
A chunking strategy that splits on topic shifts detected via embedding similarity between
adjacent sentences, rather than fixed size targets.
See [chunking-strategies.md](chunking-strategies.md).

**Sentence transformer**
A class of **bi-encoder** models fine-tuned for producing sentence-level embeddings via
contrastive learning. The Sentence-BERT family. Many modern embedding models follow this
architecture.

**SPLADE**
A sparse retrieval model that produces learned sparse vectors (one weight per vocabulary
term) rather than dense vectors. Good at exact-match retrieval. Complementary to dense
retrieval in hybrid search.

**SPO (Subject-Predicate-Object)**
A structured representation of a fact as a triple: who (subject), what relationship
(predicate), to what (object). Used to build entity graphs in agent memory systems.
See [retrieval-concepts.md](retrieval-concepts.md).

**STS (Semantic Textual Similarity)**
A task measuring how well a model scores the similarity between sentence pairs. A component
of MTEB benchmarks. High STS scores do not directly imply good retrieval performance.

---

## T

**TF (Term Frequency)**
The count of how many times a term appears in a document. A component of **BM25**.

**Tokenization**
The process of splitting text into tokens — the basic units a model processes. Common
algorithms: **BPE**, WordPiece, SentencePiece. Determines how text maps to the model's
vocabulary and affects the token count of any input.

**Top-k**
The number of results returned by a retrieval query. Higher top-k = more context for the LLM,
more computation, larger context window usage.

**Transformer**
The neural network architecture underlying all modern embedding and generation models.
Introduced in "Attention Is All You Need" (Vaswani et al., 2017). Key components: multi-head
self-attention, feed-forward layers, positional encoding.

**Triplet (training)**
See **(anchor, positive, negative)** — the three-part training example used in **contrastive
learning**.

---

## V

**Vector**
A list of floating-point numbers representing a point in a high-dimensional space. In
embedding contexts, each vector represents the semantic content of a text. See **embedding**.

**Vector database**
A storage system optimized for storing and searching vectors. Typically supports **ANN** search,
metadata filtering, and vector CRUD operations. Examples: Qdrant, Weaviate, LanceDB, Chroma.

**Vector space**
The high-dimensional space in which embeddings live. Semantic relationships between texts
correspond to geometric relationships between their vectors (proximity, direction).

---

## W

**WAL (Write-Ahead Log)**
A data structure that records operations before they are applied to the main data store.
Enables crash recovery and atomic commits. Used by memvid to stage frames before materializing
them into the `.mv2` file.
