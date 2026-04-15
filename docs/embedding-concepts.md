# Embedding Concepts

Background reference for embedding model evaluation, retrieval architectures, and benchmark interpretation.

For model selection and comparison: [embedding-model-selection.md](embedding-model-selection.md)

---

## Qwen3 Series Explainer

The Qwen3 Embedding and Qwen3 Reranker series are designed as a matched retrieval stack rather than isolated single-purpose models.

The key idea is:

- embedding models turn queries and documents into vectors
- vector similarity is used to cheaply retrieve the top candidate documents
- reranker models then read the query and each candidate document together and assign a more precise relevance score

That is why the Qwen cards emphasize both embedding and ranking tasks.

### What the Qwen3 embedding series is trying to be good at

The official Qwen model cards and paper describe the series as targeting:

- text retrieval
- code retrieval
- text classification
- text clustering
- bitext mining

These tasks are related, but they are not identical.

### Text retrieval

This is the most common RAG-style use case.

Question:

- given a query, can the model retrieve the most relevant passages or documents?

Embedding models help here because they allow:

- precomputing vectors for the corpus
- fast nearest-neighbor search
- scalable retrieval over many chunks

### Code retrieval

This is retrieval where the query, the target, or both involve code.

Examples:

- find the code snippet that matches a natural-language question
- find documentation relevant to a code fragment
- find similar functions across repositories

This matters for this repo because many local-model workflows eventually grow into code or documentation retrieval.

### Text classification

Here the question is not "what passage should I retrieve?" but:

- can the embedding space separate documents by label or intent?

Examples:

- classify support requests
- cluster logs by incident type
- separate model-card notes by category

A good embedding model often makes simple downstream classifiers work better because semantically similar texts land near each other.

### Text clustering

Clustering asks:

- if you group texts without labels, do the groups line up with real semantic structure?

This is useful for:

- corpus exploration
- topic discovery
- de-duplication workflows

### Bitext mining

Bitext mining is a multilingual retrieval problem:

- given texts in two different languages, can the model find translation-equivalent or semantically matching pairs?

This is a strong test of multilingual semantic alignment.

If a model performs well here, it is usually a good sign for:

- multilingual search
- cross-lingual retrieval
- translation-memory style systems

## MTEB Explainer

MTEB stands for `Massive Text Embedding Benchmark`.

Official references:

- https://embeddings-benchmark.github.io/mteb/
- https://github.com/embeddings-benchmark/mteb
- https://huggingface.co/mteb

At a high level, MTEB is a benchmark suite for evaluating embedding models across many task families rather than only one retrieval dataset.

That is why it is useful, and also why it is easy to overread.

### What MTEB measures

MTEB evaluates models across a mix of task categories such as:

- retrieval
- reranking
- classification
- clustering
- semantic textual similarity
- pair classification
- summarization-related matching
- bitext mining

The exact benchmark composition depends on which leaderboard slice you are looking at, such as:

- English MTEB
- multilingual MTEB or MMTEB
- code-focused subsets such as MTEB-Code

So a single leaderboard score is a compressed summary across many task types, domains, and datasets.

### Enumerating the main MTEB task benchmarks

The official MTEB task taxonomy includes these core text task families:

- `Retrieval`
  Retrieve relevant documents for a query from a corpus.
- `Reranking`
  Reorder a candidate list for better top-of-list relevance.
- `Classification`
  Assign a label to a text.
- `MultilabelClassification`
  Assign multiple labels to a text.
- `Clustering`
  Group texts by semantic similarity without labels.
- `PairClassification`
  Classify the relationship between two texts.
- `STS`
  Semantic textual similarity between two texts.
- `Summarization`
  Evaluate summary-document semantic correspondence.
- `BitextMining`
  Find semantically matching sentence pairs across languages.
- `InstructionRetrieval`
  Retrieval tasks where instruction prompting is part of evaluation.
- `InstructionReranking`
  Reranking tasks where instruction prompting is part of evaluation.

For your local use case, these are the most important by priority:

1. `Retrieval`
2. `Reranking`
3. `InstructionRetrieval`
4. `InstructionReranking`
5. `BitextMining` if multilingual search matters

Everything else is useful background signal, but it is not the center of gravity for a local RAG stack.

### Examples of retrieval and reranking benchmarks inside MTEB

The exact task list evolves, but official MTEB retrieval and reranking pages include examples such as:

- retrieval:
  `GermanQuAD-Retrieval`, `GermanDPR`, `XMarket`, `GerDaLIR`
- reranking:
  `MIRACLReranking`

And the broader benchmark catalog now includes retrieval-heavy subsets and benchmarks like:

- `RTEB(beta)`
- `RTEB(eng, beta)`
- code and domain-specific retrieval slices

That matters because MTEB is not one monolithic test. It is a framework spanning many concrete datasets and benchmark bundles.

### How to read an MTEB score

A high MTEB score generally means:

- the model is broadly capable across many embedding tasks

It does not automatically mean:

- it is best for your exact workload
- it is fastest
- it is the easiest to serve locally
- it is best for first-stage retrieval versus reranking

For this repo, MTEB should be treated as:

- a strong screening benchmark
- not the only decision criterion

### Common MTEB metrics

MTEB does not use one single metric for every task. It uses task-appropriate metrics, then aggregates results.

The most important ones to understand are:

### What `@k` means

When you see metrics like:

- `nDCG@10`
- `Recall@20`
- `Precision@5`
- `pass@1`
- `pass@3`

the `@k` part means:

- evaluate only the top `k` ranked items
- or, for generation-style metrics, evaluate success within `k` attempts

So:

- `nDCG@10` means "score the ranking quality of only the top 10 retrieved items"
- `Recall@20` means "how many relevant items were captured inside the top 20"
- `pass@1` means "did the first attempt succeed?"
- `pass@3` means "did any of the first 3 attempts succeed?"

For retrieval work, `@k` is very important because real systems almost never use the entire ranked list.

They usually use:

- top 5
- top 10
- top 20

That is why metrics with `@k` are often more meaningful than a metric over an unbounded ranking.

#### nDCG

`nDCG` means `normalized Discounted Cumulative Gain`.

This is a ranking metric.

Intuition:

- it rewards returning relevant items near the top
- it rewards putting the most relevant items earlier in the list
- it penalizes good results that are buried lower in the ranking

This makes nDCG especially useful for:

- retrieval
- reranking
- search quality

Why it matters:

- if your application only shows the top few hits, ranking quality near the top matters a lot

### nDCG deep dive

`nDCG` is one of the most important retrieval metrics because it measures not just:

- whether relevant documents were found

but also:

- whether they were ranked high enough to be useful

This makes it especially well suited to:

- search systems
- first-stage retrieval evaluation
- reranking evaluation
- RAG pipelines where only the top few chunks are passed downstream

#### The pieces: DCG and IDCG

`nDCG` is built from two pieces:

- `DCG`
  Discounted Cumulative Gain
- `IDCG`
  Ideal Discounted Cumulative Gain

Then:

- `nDCG = DCG / IDCG`

That normalization step is what makes scores more comparable across different queries.

#### Step 1: Gain

Each result gets a relevance value.

That relevance can be:

- binary
  relevant or not relevant
- graded
  for example `0`, `1`, `2`, `3`

Graded relevance is important because in many search tasks, some documents are:

- somewhat relevant
- strongly relevant
- ideal

`nDCG` can reward the system more for ranking the highest-value result first.

#### Step 2: Discount by position

The key idea behind DCG is that relevance counts less as the item moves lower in the ranking.

Intuition:

- a relevant result at rank 1 is much better than the same result at rank 10

So the gain is discounted by rank position.

A common graded-relevance formulation is:

```text
DCG@k = sum_{i=1..k} (2^rel_i - 1) / log2(i + 1)
```

You will also sometimes see simpler variants that use `rel_i` directly instead of `(2^rel_i - 1)`.

For this document, the important idea is not the notation choice. It is that both formulations encode the same ranking preference:

- high-ranked relevant items matter more
- lower-ranked items still count, but less

#### Step 3: Compare to the ideal ordering

Different queries have different numbers of relevant documents and different relevance distributions.

So raw `DCG` is not enough by itself.

To normalize it:

1. take the same set of relevance judgments
2. sort them into the best possible ranking
3. compute `IDCG@k`
4. divide actual `DCG@k` by `IDCG@k`

That gives:

```text
nDCG@k = DCG@k / IDCG@k
```

Result:

- `1.0` means the ranking is ideal at cutoff `k`
- lower values mean the ranking is worse than ideal

#### Worked example

The earlier short example is directionally correct, but it is easier to understand `nDCG` with the arithmetic shown.

Assume we use graded relevance and this DCG formula:

```text
DCG@k = sum_{i=1..k} (2^rel_i - 1) / log2(i + 1)
```

Now suppose the top 5 retrieved documents have relevance labels:

```text
A = [3, 2, 0, 1, 0]
```

Interpretation:

- rank 1 has relevance `3`
- rank 2 has relevance `2`
- rank 3 has relevance `0`
- rank 4 has relevance `1`
- rank 5 has relevance `0`

Then:

```text
DCG_A@5
= (2^3 - 1)/log2(2)
+ (2^2 - 1)/log2(3)
+ (2^0 - 1)/log2(4)
+ (2^1 - 1)/log2(5)
+ (2^0 - 1)/log2(6)
```

Numerically:

```text
= 7/1
+ 3/1.585
+ 0/2
+ 1/2.322
+ 0/2.585
≈ 7 + 1.893 + 0 + 0.431 + 0
≈ 9.324
```

Now compare that with a worse ordering of the same relevance labels:

```text
B = [0, 1, 2, 3, 0]
```

Then:

```text
DCG_B@5
= (2^0 - 1)/log2(2)
+ (2^1 - 1)/log2(3)
+ (2^2 - 1)/log2(4)
+ (2^3 - 1)/log2(5)
+ (2^0 - 1)/log2(6)
```

Numerically:

```text
= 0/1
+ 1/1.585
+ 3/2
+ 7/2.322
+ 0/2.585
≈ 0 + 0.631 + 1.5 + 3.014 + 0
≈ 5.145
```

So ranking `A` is much better than ranking `B`, even though both contain the exact same set of documents.

That is the key point:

- `nDCG` cares about order, not just membership

#### Computing IDCG in the same example

To normalize, we compare against the ideal ranking for these same relevance labels.

The ideal ordering is:

```text
[3, 2, 1, 0, 0]
```

So:

```text
IDCG@5
= 7/log2(2)
+ 3/log2(3)
+ 1/log2(4)
+ 0/log2(5)
+ 0/log2(6)
≈ 7 + 1.893 + 0.5
≈ 9.393
```

Now the normalized scores are:

```text
nDCG_A@5 = 9.324 / 9.393 ≈ 0.993
nDCG_B@5 = 5.145 / 9.393 ≈ 0.548
```

That makes the interpretation much clearer:

- ranking `A` is almost ideal
- ranking `B` is much worse

even though both rankings retrieved the same relevant items.

That is exactly why `nDCG` is so useful for retrieval and reranking.

#### Why nDCG is better than plain recall for ranking quality

Recall asks:

- did the system retrieve relevant items?

It does not strongly care whether:

- the best item was rank 1
- or rank 10

`nDCG` does care.

This is why:

- recall is often more important for stage-1 candidate generation
- nDCG is often more important for top-of-list quality and reranking

#### Why `@10` is common

`nDCG@10` is common because many applications only care about the first screenful or first prompt window of results.

For example:

- a user may only inspect the first 10 search results
- a RAG pipeline may only pass the top 5 to top 10 chunks into generation

So `nDCG@10` maps well to practical use.

If your system only ever uses the top 5 chunks, then:

- `nDCG@5` may be even more informative for your internal evals

#### nDCG with binary vs graded judgments

With binary judgments:

- `nDCG` still works
- it mostly reflects whether relevant items are ranked early

With graded judgments:

- `nDCG` becomes more expressive
- it can reward systems that rank the very best documents above merely acceptable ones

This makes graded `nDCG` especially valuable for reranking benchmarks.

#### What nDCG does not tell you

`nDCG` is very useful, but it is not the whole story.

It does not directly tell you:

- whether your retriever found all relevant items in the corpus
- how expensive the retrieval system is
- whether the retrieved text is actually the best chunking strategy for generation
- whether your model generalizes outside the benchmark

That is why `nDCG` should usually be read together with:

- `Recall@k`
- domain-specific benchmark slices
- private or internal evaluation

#### Practical rule for your local retrieval stack

For your likely use case:

- use `Recall@k` to judge whether your first-stage embedding retriever is finding enough candidates
- use `nDCG@k` to judge whether the highest-ranked candidates are in the right order
- use reranking to improve `nDCG@k` after retrieval if recall is already good

#### MAP

`MAP` means `Mean Average Precision`.

Intuition:

- it measures how well relevant items are retrieved across the ranking
- it is sensitive to whether relevant results appear early, not just whether they appear somewhere

MAP is often used when there may be multiple relevant documents per query.

#### Recall@k

`Recall@k` asks:

- among all relevant items, how many were captured in the top `k` results?

This is a retrieval coverage metric.

It is less concerned with the exact order inside the top `k` than nDCG.

This matters when your pipeline does:

- first-stage retrieval with a generous top-k
- second-stage reranking later

In that setup, high recall at the retrieval stage is often more important than perfect ranking at that stage.

#### Accuracy and F1

These are common in classification and pair-classification tasks.

Intuition:

- accuracy asks how often the model got the label right
- F1 balances precision and recall, which matters when classes are uneven

#### Spearman or Pearson correlation

These often appear in semantic textual similarity tasks.

Intuition:

- the model assigns similarity scores to text pairs
- the benchmark checks how well those scores track human judgments

#### Clustering metrics

Clustering tasks often use metrics such as `v-measure` or `NMI`.

Intuition:

- if the embedding space is good, unsupervised clusters should align better with real semantic categories

### Which MTEB metrics matter most for RAG

If your practical use case is local RAG, the most important categories are usually:

- retrieval metrics like nDCG and Recall@k
- reranking metrics if you plan to add a reranker
- multilingual retrieval metrics if your corpus or queries span multiple languages

For a two-stage retrieval pipeline:

- stage 1 embedding retriever should have strong recall
- stage 2 reranker should improve top-of-list ordering, often reflected by stronger nDCG-style behavior

## RTEB Explainer

If retrieval is your main use case, RTEB is more relevant than the overall MTEB aggregate.

RTEB stands for `Retrieval Embedding Benchmark`.

Official references:

- https://huggingface.co/blog/rteb
- https://embeddings-benchmark.github.io/mteb/overview/available_benchmarks/

The Hugging Face launch post was published on October 1, 2025.

### What RTEB is trying to fix

RTEB was introduced because broad public retrieval leaderboards have a known problem:

- models get repeatedly tested against the same public datasets
- training data can overlap with benchmark data
- leaderboard gains can partly reflect benchmark familiarity rather than true retrieval generalization

The RTEB authors frame this as a generalization gap between:

- public benchmark performance
- performance on new, unseen retrieval problems

The Hugging Face post also makes a useful distinction between:

- leaderboard score
- "zero-shot" score

The point is that a model can look strong on a familiar public benchmark while still generalizing poorly to new retrieval tasks. The benchmark designers explicitly argue that developers should care about that generalization gap, not just the leaderboard headline.

So RTEB is explicitly trying to be:

- retrieval-first
- more realistic
- more resistant to benchmark overfitting

### Why RTEB matters more than generic MTEB for local RAG

Your actual local use case is not:

- broad embedding capability across classification, clustering, STS, and bitext mining

It is:

- can this model retrieve the right chunks for my queries?

That makes RTEB a better decision aid because it focuses on:

- retrieval quality
- domain realism
- multilingual and specialized search settings

### The core design: open + private datasets

RTEB uses a hybrid benchmark design:

- open datasets
  fully public and reproducible
- private datasets
  evaluated by the maintainers to test generalization to unseen data

This is probably the most important thing to understand about RTEB.

Why it matters:

- strong public-only performance can be misleading
- if a model drops sharply on the private side, that suggests benchmark overfitting or weak generalization

So for retrieval selection, RTEB is valuable not just because it has retrieval tasks, but because it tries to measure whether those retrieval results survive contact with unseen data.

The Hugging Face article is explicit that the private side is not opaque in the useless sense. For transparency, the maintainers provide:

- descriptive statistics
- dataset descriptions
- sample `(query, document, relevance)` triplets

That matters because the benchmark is trying to balance:

- reproducibility
- anti-overfitting protection

### Default metric: nDCG@10

The RTEB material explicitly states that the default leaderboard metric is:

- `nDCG@10`

That is a strong choice for retrieval because it emphasizes:

- whether relevant documents appear near the top
- whether the best documents appear early enough to matter in a search UI or RAG pipeline

For local RAG, top-of-list quality matters a lot more than broad semantic elegance.

If your application only passes the top 5 or top 10 chunks into the final prompt, nDCG@10 is directly relevant.

### What kinds of retrieval RTEB covers

RTEB is not one dataset. It is a retrieval benchmark family spanning multiple domains and languages.

The benchmark documentation highlights:

- legal
- finance
- healthcare
- code
- multilingual retrieval

The Hugging Face post adds several concrete design points:

- datasets are organized into simple groups rather than a complicated hierarchy
- one dataset can belong to multiple groups
  for example, a German legal dataset can count as both `german` and `legal`
- the benchmark currently covers 20 languages
- datasets are intended to be meaningfully sized without becoming operationally absurd to run
  the launch post describes a minimum target of about `1,000` documents and `50` queries

Examples from the current benchmark listing include:

- `HumanEvalRetrieval`
- `MBPPRetrieval`
- `WikiSQLRetrieval`
- `FreshStackRetrieval`
- `FinanceBenchRetrieval`
- `ChatDoctorRetrieval`
- `MIRACLRetrievalHardNegatives`

The Hugging Face article also gives concrete open-dataset examples across domains, including:

- legal:
  `AILACasedocs`, `AILAStatutes`, `LegalSummarization`, `LegalQuAD`
- finance:
  `FinanceBench`, `HC3Finance`, `FinQA`
- code:
  `HumanEval`, `MBPP`, `APPS`, `DS1000`, `WikiSQL`
- healthcare:
  `ChatDoctor_HealthCareMagic`, `HC3 Medicine`, `Cure`, `TripClick`
- multilingual and general retrieval:
  `MIRACLHardNegatives`, `JaQuAD`, `FreshStack`

That is a more useful picture than thinking of RTEB as just "one retrieval score."

This is important because retrieval quality is highly domain-sensitive.

A model that looks good on generic QA-style retrieval may not be the best model for:

- code search
- technical docs
- multilingual knowledge bases
- legal or medical corpora

### How to read RTEB for your use case

You should not ask:

- which model is #1 on RTEB overall?

You should ask:

- which model performs well on the RTEB slice closest to my workload?

For example:

- if your corpus is mostly English docs, `RTEB(eng, beta)` matters more than the multilingual aggregate
- if your main problem is code retrieval, the code-heavy tasks matter more than the finance or legal tasks
- if your content spans multiple languages, the multilingual and language-specific slices matter more than English-only results

### RTEB slices that matter most for this repo

For likely local usage in this repo, the most relevant slices are:

- `RTEB(beta)`
  broad retrieval signal across domains
- `RTEB(eng, beta)`
  best general-purpose check if most of your material is English
- code-heavy tasks
  especially if you expect to retrieve source code, documentation, or engineering notes
- multilingual retrieval tasks
  if your knowledge base or queries are not strictly English

The MTEB benchmark page also lists narrower domain subsets such as:

- `RTEB(Law, beta)`
- `RTEB(Health, beta)`
- language slices like `RTEB(deu, beta)`, `RTEB(fra, beta)`, and `RTEB(jpn, beta)`

From the Hugging Face article, that grouping philosophy is intentional: the benchmark is trying to let you inspect the slice closest to your real workload instead of forcing every model comparison through one single global number.

### What RTEB still does not solve

RTEB is better aligned with retrieval than the broad MTEB aggregate, but it is not perfect.

The official RTEB launch notes several current limitations:

- it is still beta
- it is text-only today
- language coverage is still expanding
- about half of the current retrieval datasets are repurposed from QA datasets

The Hugging Face post also acknowledges an important realism issue:

- some retrieval benchmarks derived from QA data can still be useful, but they are not the same as production retrieval datasets designed from the start for search evaluation

That is one reason the benchmark emphasizes enterprise-oriented domains and ongoing dataset expansion.

That last point matters because QA-derived retrieval can favor lexical overlap more than true production retrieval sometimes does.

So even with RTEB, your own retrieval eval still matters.

### Practical takeaway

For choosing a local embedding model in this repo:

- use MTEB as broad background context
- use RTEB as the more relevant public benchmark family
- prefer models that look strong on retrieval-specific slices, not just overall embedding aggregates
- if available, prefer evidence that performance holds on both open and private RTEB-style evaluation

If I were choosing for a local RAG-first setup, I would trust:

1. domain-relevant RTEB retrieval results
2. then broader retrieval metrics like MTEB retrieval subsets
3. then the overall MTEB aggregate

in exactly that order

### What this means for this repo

For this repo, the practical lesson from the Hugging Face RTEB article is:

- if you are choosing a local embeddings model for retrieval, a broad "good embedding model" story is not enough
- you want evidence that the model performs well on retrieval-specific benchmarks
- you especially want evidence that retrieval quality holds up outside familiar public datasets

So the right benchmark-reading order for this repo is:

1. RTEB slices that match your workload
2. retrieval-specific MTEB tasks
3. broader MTEB aggregate results
4. only then secondary task families like clustering or classification


---

## Retrieval Architectures

Embedding models can produce different kinds of representations. The architecture determines what kind of index you build and how query-document similarity is computed.

### Dense retrieval

The standard approach. One vector per text.

```
query  → [single vector]
doc    → [single vector]
score  = dot_product(query_vec, doc_vec)
```

Fast at query time. Index is compact. Works well when queries and documents are semantically similar in the embedding space.

Weakness: a single vector must compress all meaning. Queries that need to match multiple distinct aspects of a document can lose signal.

### Sparse retrieval (SPLADE)

Instead of a dense vector, the model outputs a sparse weighted term vocabulary — like a learned BM25.

```
query → {term: weight, term: weight, ...}  (most weights ~0)
doc   → {term: weight, term: weight, ...}
score = sum of overlapping weighted terms
```

Good at exact and near-exact term matching. Complements dense retrieval on queries where lexical specificity matters (version numbers, proper nouns, code tokens).

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

Each query token independently finds its best matching document token, then the scores are summed.

Why it matters:

- "bank of a river" and "bank loan" map to the same dense vector in ambiguous models; ColBERT keeps them distinct because `river` and `loan` match different document tokens
- multi-aspect queries ("fast AND cheap AND local") get each aspect separately matched rather than compressed into one average direction
- exact token sensitivity: "Python 3.11 migration" won't match a document about "Python 2.7" because `3.11` and `2.7` pull in different directions

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

BGE-M3 is notable because it runs all three modes (dense, sparse, ColBERT) from a single set of weights, making hybrid pipelines cheaper to operate than maintaining separate models.

## Ranking vs Re-ranking

This distinction is one of the most important things to understand when choosing an embedding stack.

### Ranking

Ranking is the initial ordering produced by the retriever.

In an embedding pipeline, the usual process is:

1. embed the query
2. embed all documents or chunks ahead of time
3. compute similarity
4. return the top `k` nearest items

This stage is:

- fast
- scalable
- approximate

Why it is fast:

- document embeddings are precomputed
- nearest-neighbor search can be indexed efficiently

Why it is approximate:

- the retriever compares fixed vectors, not full query-document reasoning

### Re-ranking

Re-ranking is a second pass over the candidate set returned by the retriever.

Typical process:

1. retriever returns top 20, 50, or 100 candidates
2. reranker reads the query plus each candidate together
3. reranker assigns a more exact relevance score
4. candidates are reordered before being shown or passed to generation

This stage is:

- slower
- more expensive
- usually more accurate

Why it is more accurate:

- the reranker can reason over the direct query-document interaction
- it does not rely only on coarse vector proximity

### Why not rerank everything

Because reranking does not scale well to a huge corpus.

If you have:

- 1 million chunks

you can vector search them efficiently, but you usually do not want to run a cross-encoder style reranker over all 1 million.

So the common pattern is:

- retrieve broadly
- rerank narrowly

### Practical retrieval stack

A strong modern local retrieval stack often looks like this:

1. embedding model generates query and document vectors
2. vector DB or ANN index returns top 20 to top 100 candidates
3. reranker rescoring narrows this to the best top 5 to top 10
4. only those highest-ranked chunks go into the final LLM prompt

### What each model is optimizing for

Embedding model goal:

- maximize semantic recall and good-enough ranking at scale

Reranker goal:

- maximize precision at the top of the list

That is why embedding and reranking scores should not be treated as interchangeable.

## Query Instruction Explainer

The Qwen embedding cards include guidance like this:

> Tip: We recommend that developers customize the instruct according to their specific scenarios, tasks, and languages. Our tests have shown that in most retrieval scenarios, not using an instruct on the query side can lead to a drop in retrieval performance by approximately 1% to 5%.

What this means in practice:

- the query should often be wrapped in a task-specific instruction
- the document usually stays as plain document text
- the model is being told what kind of similarity problem it is solving

### Why query-side instructions help

Embedding models are not only learning generic "semantic similarity." They are also learning task-conditioned similarity.

Those are different questions:

- "what texts are generally similar?"
- "what documents answer this search query?"
- "what code snippet is relevant to this bug report?"
- "what multilingual passage best matches this English question?"

An instruction helps disambiguate the retrieval intent.

Without an instruction, the model may optimize for a vaguer notion of semantic closeness.

With an instruction, the model can better align the query embedding toward the retrieval objective you actually care about.

That is why the Qwen team reports a measurable retrieval drop when the query-side instruction is omitted.

### The basic pattern

The usual pattern is:

- query side: add an instruction prefix
- document side: embed the raw document or chunk

Conceptually:

```text
Query embedding input:
"Instruct: Given a web search query, retrieve relevant passages that answer the query.
Query: how does KV cache reuse work in llama.cpp?"

Document embedding input:
"KV cache reuse in llama.cpp allows ..."
```

The instruction tells the model what "relevant" means for this query.

### Why not instruct both sides

Usually you do not want to add the same instruction to every document chunk because:

- it adds noise and wasted tokens
- document embeddings are often precomputed once and reused many times
- the task conditioning is usually needed most on the query side

The query is where the ambiguity lives.

### What "customize the instruct" really means

It does not mean you need a different prompt for every single query.

It usually means:

- choose a stable instruction template for each retrieval use case
- adapt it to your language and domain
- keep it consistent during indexing and evaluation

Examples of retrieval modes that may want different instructions:

- documentation search
- code search
- support-ticket retrieval
- multilingual knowledge-base retrieval
- legal or medical retrieval with specialized vocabulary

### Example instruction templates

General documentation retrieval:

```text
Instruct: Given a question, retrieve passages that best answer it.
Query: {query}
```

Code retrieval:

```text
Instruct: Given a software engineering question, retrieve code or documentation relevant to solving it.
Query: {query}
```

Multilingual retrieval:

```text
Instruct: Given a multilingual search query, retrieve passages with the most relevant semantic meaning, even across languages.
Query: {query}
```

Internal knowledge-base retrieval:

```text
Instruct: Given an internal operations question, retrieve documents that directly help answer the question.
Query: {query}
```

### What the reported 1% to 5% drop means

That reported drop should be interpreted as:

- not catastrophic
- but large enough to matter in retrieval systems

Why it matters:

- a few percentage points in retrieval can be the difference between the right chunk appearing in the top 5 versus disappearing below the cutoff
- once a relevant document misses the first-stage retrieval window, reranking cannot recover it

So even a modest drop at the embedding stage can have a noticeable end-to-end effect on RAG quality.

### Operational implication

If you adopt a Qwen3 embedding model in this repo, you should plan for:

1. a consistent query instruction template
2. a retrieval-specific evaluation pass using your own corpus
3. measuring top-k recall before and after changing the instruction

This matters more than chasing leaderboard decimals, because the best instruction for:

- your language mix
- your chunking strategy
- your domain vocabulary
- your query style

may differ from the default examples in the model card.

### Practical rule

For a first deployment:

- start with a simple, stable query instruction
- do not instruct documents
- benchmark retrieval quality on your own data
- only then tune the instruction wording

That is the low-complexity path to capturing most of the benefit the Qwen guidance is pointing at.

## How `llama-embedding` works

`llama-embedding` is the llama.cpp command-line tool for generating embeddings directly from a model instead of generating text.

Conceptually, it does this:

1. load an embedding-capable model
2. tokenize the input text
3. run a forward pass through the model
4. extract a vector representation from the model output
5. optionally normalize or format that vector for downstream use

So instead of returning:

- next-token probabilities
- generated text

it returns:

- a numeric vector that represents the semantic meaning of the input

### What embedding generation means at the model level

A transformer processes input tokens into hidden states.

An embedding model then turns those hidden states into a single fixed-size vector.

That vector is what you store in a vector index and compare during retrieval.

The key challenge is:

- token sequences have variable length
- vector search wants a fixed-size output

So the tool needs a pooling strategy.

### Why pooling matters

Pooling is the method used to collapse token-level hidden states into one embedding vector.

Common pooling strategies include:

- `last`
- `mean`
- `cls`

For Qwen3 embedding GGUF models, the official card explicitly uses:

```text
--pooling last
```

That means the final embedding is derived from the last token representation in the way the model was trained to expect.

This matters because using the wrong pooling mode can degrade retrieval quality even if the model "runs."

So for Qwen3 embedding models, `last` is not just an implementation detail. It is part of using the model correctly.

### `llama-embedding` vs `llama-server --embedding`

These serve different roles.

`llama-embedding`:

- one-shot CLI tool
- useful for local experiments
- useful for benchmarking
- useful for generating vectors offline in scripts or batch jobs

`llama-server --embedding`:

- long-running service
- exposes an HTTP endpoint
- better for OpenAI-compatible clients and apps like Open WebUI
- better when embeddings need to be requested repeatedly

So the rough split is:

- use `llama-embedding` to inspect and test
- use `llama-server --embedding` to serve a real application

### Why embedding models are often served separately

A chat model server and an embedding model server usually have different jobs:

- chat generation wants `/v1/chat/completions`
- embedding search wants `/v1/embeddings`

They may also need:

- different models
- different ports
- different throughput assumptions
- different memory budgets

That is why a dedicated embedding server is usually cleaner than trying to make one chat model do everything.

### What gets indexed

In a retrieval workflow, you usually do not embed the entire corpus at query time.

Instead:

1. split documents into chunks
2. run `llama-embedding` or an embedding server over those chunks once
3. store the vectors in a vector DB or ANN index
4. at query time, embed only the query
5. compare query vector to stored document vectors

This is what makes embedding retrieval scalable.

### Why normalization matters

Vector similarity is often computed with:

- cosine similarity
- dot product
- inner product

Many retrieval systems either explicitly normalize vectors or assume a similarity convention that effectively depends on normalization behavior.

The practical takeaway is:

- keep the indexing and query pipelines consistent
- do not change vector post-processing halfway through a deployment

If query vectors and document vectors are produced differently, retrieval quality can silently degrade.

### Why embedding performance differs from generation performance

Embedding throughput and chat-generation throughput are not the same thing.

Embedding workloads are more like:

- encode text
- return one vector

Generation workloads are:

- repeatedly decode tokens step by step

So a model that feels fine for embedding may be much too slow for chat generation, and vice versa.

That is another reason embedding-specialized models are valuable.

### Minimal mental model

If you want the simplest way to think about `llama-embedding`, use this:

- `llama-embedding` turns text into vectors
- pooling decides how token states become one vector
- vector similarity powers retrieval
- `llama-server --embedding` is the service form of the same idea

### Practical implication for this repo

If this repo adopts `Qwen3-Embedding-4B-GGUF`, the most likely operational pattern is:

1. use `llama-embedding` to validate quality and inspect behavior locally
2. serve the model with `llama-server --embedding --pooling last`
3. point Open WebUI or another RAG client at that dedicated embeddings endpoint
4. later add a reranker if top-of-list quality becomes the bottleneck

## Implication For This Repo

If you only add one model first, the embedding model is the right first step because:

- it gives you the core `/v1/embeddings` capability
- it is the prerequisite for scalable corpus search
- Open WebUI and RAG systems can already benefit from it

If retrieval quality later becomes the bottleneck, the next upgrade should be:

- add a Qwen3 reranker as a second-stage model

That is the cleanest path from:

- simple local embeddings

to:

- serious retrieval quality

