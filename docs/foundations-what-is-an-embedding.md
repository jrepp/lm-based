# What Is an Embedding?

This is the foundational question for everything else in this book. Everything — retrieval,
reranking, memory, hybrid search, ANN indexes — is downstream of the answer.

Related documents:

- Tokenization: [tokenization.md](tokenization.md)
- Retrieval architectures that use embeddings: [retrieval-concepts.md](retrieval-concepts.md)
- Model selection: [embedding-model-selection.md](embedding-model-selection.md)

---

## The core problem

Computers are good at numbers. Language is not numbers. There is a gap.

The naive approach to bridging that gap is to assign each word an integer ID:

```
"cat"   → 4821
"dog"   → 9302
"feline" → 2201
```

This does not work for meaning-sensitive tasks. The number 4821 is not close to 2201. But
"cat" and "feline" mean nearly the same thing. The integer representation has destroyed all
information about semantic relationships.

An embedding is a different kind of representation: instead of one integer, each word or text
gets a **vector** — a list of floating-point numbers.

```
"cat"    → [0.21, -0.45, 0.03, 0.88, ...]  (1536 numbers)
"feline" → [0.23, -0.42, 0.01, 0.91, ...]  (1536 numbers)
"dog"    → [0.18,  0.31, 0.55, 0.12, ...]  (1536 numbers)
```

The key property: **similar meanings produce similar vectors**. "cat" and "feline" are close
in the vector space. "cat" and "carburetor" are far apart.

---

## What "similar vectors" means geometrically

Think of each vector as a point in a high-dimensional space. With 1536 dimensions you cannot
visualize it, but the geometry still works the same way as 2D or 3D:

- Two points can be **close** (nearby in space)
- Two points can be **far apart** (distant in space)
- A direction in space can represent a concept

The classic illustration uses word vectors trained on large text corpora:

```
vector("king") - vector("man") + vector("woman") ≈ vector("queen")
```

The direction from "man" to "woman" in the vector space captures the concept of gender. The
direction from "king" to "queen" goes the same way. The arithmetic works because the geometry
of the space reflects the structure of language.

This is not programmed in. It emerges from training.

---

## What training means

An embedding model is trained on a large corpus of text. The training process adjusts the
model's weights so that **texts that should be similar end up nearby in vector space**.

The most common training objective for modern embedding models is **contrastive learning**:

```
Given: (query, relevant_document, irrelevant_document)
Goal:  make vector(query) close to vector(relevant_document)
       make vector(query) far from vector(irrelevant_document)
```

This is called a **triplet** or **(anchor, positive, negative)** setup. The loss function
penalizes the model when it places a query closer to an irrelevant document than to a relevant
one.

The irrelevant documents matter a lot. Easy negatives (completely unrelated texts) produce
weak models. **Hard negatives** — documents that look relevant but are not — force the model
to learn fine-grained distinctions. Most state-of-the-art embedding models are trained with
carefully mined hard negatives.

After training on millions or billions of such triplets, the model has learned a vector space
where semantic similarity corresponds to geometric proximity.

---

## What the dimensions represent

This is a common point of confusion: no individual dimension means anything specific.

You cannot point to dimension 742 and say "this is the adjective-ness dimension." The model
learns a distributed representation where meaning is encoded across all dimensions
simultaneously. This is fundamentally different from a hand-crafted feature vector.

What the dimensions collectively encode is a **projection of meaning into a space optimized
for the similarity task the model was trained on**. The training corpus and training objective
together determine what the space looks like.

Practical consequence: embeddings from different models are **not comparable**. A vector from
`text-embedding-3-small` and a vector from `nomic-embed-text-v1.5` live in completely
different spaces. You cannot mix them in the same index.

---

## From words to sentences to documents

Early word embedding models (Word2Vec, GloVe) produced one vector per word. The same word
always got the same vector, regardless of context.

Modern embedding models (BERT, RoBERTa, and their successors) are **contextual**. The same
word gets a different vector depending on the surrounding text:

```
"bank" in "I went to the bank to deposit money"
    → vector reflecting financial institution

"bank" in "we sat on the bank of the river"
    → vector reflecting a riverbank
```

These models produce one vector per **token** (a subword unit — see
[tokenization.md](tokenization.md)), and then **pool** those token vectors into a single
vector representing the whole input.

Common pooling strategies:

| Strategy | What it does | Typical use |
|---|---|---|
| Mean pooling | Average all token vectors | Most embedding models |
| CLS pooling | Use the special [CLS] token vector | BERT-style models |
| Last-token pooling | Use the final token's vector | Decoder/causal models (Qwen3) |

The pooling strategy is baked into how the model was trained. Using the wrong pooling for a
given model degrades quality significantly.

---

## The difference between embedding models and generative models

This distinction matters for this repo because both types of model run on llama-server.

| | Embedding model | Generative model |
|---|---|---|
| Input | Text | Text (plus history, tools, etc.) |
| Output | A vector of numbers | More text |
| Purpose | Represent meaning for retrieval | Produce responses |
| Runs over input | Once (encode) | Autoregressively (token by token) |
| Typical size | 0.1B–8B params | 1B–400B+ params |
| Inference cost | One forward pass | Many forward passes (one per output token) |

An embedding model reads the input once and produces a fixed-size vector. It never generates
text. A generative model reads the input and then generates text one token at a time, with
each token depending on all previous tokens.

For RAG, both are needed: the embedding model retrieves relevant context; the generative model
uses that context to produce an answer.

---

## Bi-encoder vs cross-encoder

Both are transformer models, but they operate differently:

**Bi-encoder (embedding model):**
```
query  → [encoder] → query_vector
doc    → [encoder] → doc_vector
score  = similarity(query_vector, doc_vector)
```

The query and document are encoded independently. This is fast because document vectors can
be precomputed and stored in an index.

**Cross-encoder (reranker):**
```
[query + doc] → [encoder] → relevance_score
```

The query and document are read together. The model can reason about their interaction
directly. This is slower because it cannot be precomputed — you must run the model fresh for
every (query, candidate) pair at query time.

Bi-encoders retrieve at scale. Cross-encoders rerank at precision. The typical production
stack uses both in sequence: bi-encoder fetches top 50, cross-encoder reranks to top 5.

---

## Why high dimensionality?

Embedding dimensions range from 384 (small, fast models) to 3072 (large, high-quality models).
More dimensions means:

- More capacity to encode nuanced distinctions
- Larger index size (1536-dim float32 = 6KB per vector)
- Slower distance computation (mitigated by ANN algorithms)

The relationship is not linear. Going from 384 to 768 dims captures meaningfully more
information. Going from 1536 to 3072 dims produces smaller gains for most retrieval tasks.

Dimensionality reduction is possible: `text-embedding-3-small` and `text-embedding-3-large`
support a `dimensions` parameter that truncates the output while preserving most signal. This
is useful when index storage is the bottleneck.

---

## What makes a good embedding space for retrieval

The embedding space has to work for the query-document relationship, not just for
document-document similarity. A space that groups similar documents together is not
automatically good at matching short queries to long documents.

Key properties for retrieval:

- **Asymmetric matching**: short query ("python list sorting") should be close to long
  document explaining `list.sort()`, even though they're very different in length and style
- **Out-of-vocabulary robustness**: the model should handle domain-specific terms it has not
  seen exactly during training
- **Cross-lingual capability** (when needed): query in English, document in Chinese should
  still match if they say the same thing

This is why embedding benchmarks (MTEB, RTEB) test retrieval specifically, not just
semantic textual similarity. See [embedding-model-selection.md](embedding-model-selection.md).

---

## Summary

- An embedding turns text into a vector of numbers
- Similar meanings produce similar vectors; the geometry reflects semantics
- This emerges from contrastive training on (anchor, positive, negative) triplets
- Individual dimensions mean nothing; meaning is distributed across all of them
- Embeddings from different models are incompatible — never mix them in one index
- Pooling strategy (mean, CLS, last-token) is part of the model contract
- Bi-encoders are fast (precomputed vectors); cross-encoders are precise (joint reasoning)
- More dimensions = more capacity, larger storage, not always worth the cost
