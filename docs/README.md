# docs/

Reference documentation for the lm-based local LLM stack.

## Infrastructure

| Document | Contents |
|---|---|
| [architecture.html](architecture.html) | Full stack diagram: L0 ingress → L1 agent → L2 router → L3 local → L4 cloud |
| [local-llm-routing-architecture.md](local-llm-routing-architecture.md) | ClawRouter design, routing decisions, model tiers |
| [clawrouter-operations.md](clawrouter-operations.md) | Generating and validating `clawrouter.json`, provider status |
| [credentials.md](credentials.md) | API key env vars, direct vs. x402 proxy routing |
| [open-webui-local-server.md](open-webui-local-server.md) | Open WebUI setup, embedding backend config |

## Models

| Document | Contents |
|---|---|
| [model-card-index.md](model-card-index.md) | Index of all sidecar-registered models |
| [qwen-run-stats.md](qwen-run-stats.md) | Observed runtime stats for Qwen models |

## llama-server

| Document | Contents |
|---|---|
| [llama-server-cache-architecture-explainer.md](llama-server-cache-architecture-explainer.md) | KV cache, prompt caching, context management |
| [llama-server-stats-faq.md](llama-server-stats-faq.md) | Stats endpoint fields, interpreting metrics |

## Embeddings and Retrieval — Foundations

| Document | Contents |
|---|---|
| [foundations-what-is-an-embedding.md](foundations-what-is-an-embedding.md) | What embeddings are, training objectives, vector spaces, bi-encoder vs cross-encoder, pooling |
| [tokenization.md](tokenization.md) | BPE, WordPiece, token vs character counts, model limits, practical counting |
| [chunking-strategies.md](chunking-strategies.md) | Fixed-size, sentence-boundary, semantic, structure-aware, parent-child, overlap tradeoffs |
| [rag-pipeline.md](rag-pipeline.md) | Complete indexing and query pipeline, context assembly, prompt construction, failure modes |

## Embeddings and Retrieval — Concepts

| Document | Contents |
|---|---|
| [embedding-model-selection.md](embedding-model-selection.md) | Model recommendation, RTEB re-evaluation, shortlist, summary table |
| [embedding-concepts.md](embedding-concepts.md) | MTEB / RTEB benchmark explainers, metrics (nDCG, MAP), query instructions, llama-embedding internals |
| [retrieval-concepts.md](retrieval-concepts.md) | Retrieval architectures (dense / sparse / ColBERT), ANN (HNSW / PQ / IVFFlat), ranking vs re-ranking, BM25, RRF, L2, elbow cutoff, SPO |
| [retrieval-backends.md](retrieval-backends.md) | memvid deep analysis, backend comparison (Qdrant / LanceDB / MongoDB / pgvector), decision guide |

## APIs

| Document | Contents |
|---|---|
| [openai-api-explainer.md](openai-api-explainer.md) | OpenAI-compatible endpoints: chat completions, embeddings, streaming, tools |

## Reference

| Document | Contents |
|---|---|
| [glossary.md](glossary.md) | Definitions for all terms used across the embedding and retrieval docs |
