# Embedding Model Selection

Context for this repo:

- local inference is centered on `llama.cpp` / `llama-server`
- the main compatibility target is an OpenAI-compatible local endpoint
- Open WebUI and similar clients are easiest to support when the embedding model can be served cleanly as a dedicated local embeddings endpoint

Background on benchmarks, metrics, and retrieval architectures: [embedding-concepts.md](embedding-concepts.md)

---

## Status

**Under re-evaluation.** The original recommendation (Qwen3-Embedding-4B) was based on MTEB scores. After reviewing RTEB research, the question of whether Qwen3-Embedding's rankings reflect genuine out-of-distribution generalization or benchmark proximity is open. See the RTEB section below before finalising a choice.

---

## Original Recommendation

Best overall fit for this repo (pending RTEB confirmation):

- `Qwen/Qwen3-Embedding-4B-GGUF`

Why it was selected:

- strong MTEB scores (4B: 69.45, 8B: 70.58 on multilingual leaderboard)
- official GGUF release with explicit `llama.cpp` / `llama-server` usage on the model card
- much more practical locally than the 8B model while still substantially stronger than tiny embedding models
- multilingual and code retrieval support

Best lightweight fallback:

- `Qwen/Qwen3-Embedding-0.6B-GGUF`

Best absolute-quality option if memory is less constrained:

- `Qwen/Qwen3-Embedding-8B-GGUF`

Related reranker family worth pairing with the embedding model:

- `Qwen/Qwen3-Reranker-0.6B`
- `Qwen/Qwen3-Reranker-4B`
- `Qwen/Qwen3-Reranker-8B`

Good retrieval systems often use both an embedding model for fast first-pass candidate retrieval and a reranker for slower but more accurate second-pass ordering. See [embedding-concepts.md — Retrieval Architectures](embedding-concepts.md#retrieval-architectures).

---

## RTEB Re-evaluation

### What RTEB is

RTEB (Retrieval-Focused Text Embedding Benchmark) was introduced in October 2025 by the MTEB team specifically to detect benchmark overfitting.

The problem it addresses: models that are trained on, or fine-tuned using data that overlaps with, MTEB test sets can achieve inflated public scores without actually generalising to new distributions. MTEB scores alone cannot reveal this because both the training data and the test data are public.

RTEB's approach:

- combines fully public datasets with **private held-out datasets** maintained by the MTEB team
- evaluates across enterprise domains (legal, finance, healthcare, code) in 20+ languages
- exposes a performance gap between open-data score and private-data score
- a model with a large open→private drop likely memorised benchmark-adjacent data; a model with a small or inverted gap likely generalises

References:

- https://huggingface.co/blog/rteb
- https://github.com/embedding-benchmark/rteb

### What RTEB shows about Qwen3-Embedding

Qwen3-Embedding does not have published first-party RTEB scores as of this writing.

That absence is the core problem with the original recommendation. MTEB rank-1 without a corresponding RTEB result means the generalization question is unanswered, not confirmed.

What the indirect evidence suggests:

- Octen-Embedding-8B, which is fine-tuned on Qwen3-8B base, scores **0.8045 on RTEB overall** and performs *slightly higher on private data than public* (0.8157 private vs 0.7953 public). That inverted gap is a strong generalization signal and suggests the Qwen3 foundation model itself is not poisoned.
- Qwen3-Embedding's three-stage training (contrastive pretraining on weakly supervised data → supervised fine-tuning → model merging) is designed for domain breadth, which is consistent with generalisation.
- Qwen3-Embedding outperforms BGE-M3 by ~18% on MTEB English v2 and ~8% on MMTEB, which is a larger margin than benchmark contamination alone would typically produce.

Tentative interpretation: Qwen3-Embedding is probably not severely contaminated, but "probably not" is not the same as confirmed. The gap is a known risk for any model released after MTEB became the dominant leaderboard.

### What to do before finalising the choice

1. Check whether Qwen3-Embedding RTEB scores have been published since this was written (the RTEB leaderboard is live and updated).
2. Run a small domain-specific internal eval against your actual retrieval corpus. Even 50–100 query-document pairs with manual relevance labels will reveal gross distribution mismatch.
3. If internal eval is not feasible, treat Qwen3-Embedding as the leading candidate but defer to RTEB-confirmed alternatives if they appear.

### RTEB-confirmed alternatives

| Model | RTEB score | Notes |
|-------|-----------|-------|
| Octen-Embedding-8B | 0.8045 | Fine-tuned on Qwen3-8B; best published RTEB result; not practical locally at 8B |
| Voyage-3-large | 0.7812 | API-only; no local serving |
| Gemini-embedding-001 | 0.7602 | API-only |
| BGE-M3 | not published | Strong multilingual; 8192-token context; GGUF available; 3× faster via ONNX |

For local llama.cpp serving specifically, BGE-M3 is the strongest RTEB-adjacent alternative:

- `BAAI/bge-m3` — GGUF quantizations available from community publishers
- supports dense, sparse (SPLADE), and ColBERT-style retrieval in a single model (see [embedding-concepts.md — Retrieval Architectures](embedding-concepts.md#retrieval-architectures))
- well-established generalization reputation predating the MTEB contamination era
- 8,192 token context vs Qwen3-Embedding's 32K (usually sufficient for chunked retrieval)

### Recommended next step

Run the RTEB leaderboard check first. If Qwen3-Embedding has an entry with a small open→private gap, confirm it and proceed. If it is still absent, run the domain eval or default to BGE-M3 as the conservative choice.

---

## Shortlist

### 1. Qwen3-Embedding-4B-GGUF

Hugging Face:

- https://huggingface.co/Qwen/Qwen3-Embedding-4B-GGUF

Key findings from the model card:

- 4B parameters
- 32k context length
- embedding dimension up to 2560 with configurable output dimensions from 32 to 2560
- 100+ language support
- official GGUF quantizations including `Q4_K_M`
- explicit `llama.cpp` usage with:
  `llama-embedding ... --pooling last`
  and
  `llama-server -m model.gguf --embedding --pooling last`
- the card reports `Qwen3-Embedding-4B` at `69.45` on multilingual MTEB and `74.60` on MTEB English v2
- the same card reports the 8B model at the top of the multilingual MTEB leaderboard as of June 5, 2025

Fit assessment:

- best balance of quality, local footprint, and implementation simplicity
- easiest path to adopt in this repo because it matches the existing `llama.cpp` serving model

Practical footprint:

- the model card lists `Q4_K_M` at about `2.5 GB`
- `F16` is about `8.05 GB`

## 2. Qwen3-Embedding-0.6B-GGUF

Hugging Face:

- https://huggingface.co/Qwen/Qwen3-Embedding-0.6B-GGUF

Key findings:

- 0.6B parameters
- 32k context length
- embedding dimension up to 1024
- 100+ language support
- official GGUF release
- same Qwen3 embedding family features: instruction awareness and configurable output dimension
- official model card exposes the same `llama.cpp`-friendly usage pattern

Fit assessment:

- strongest low-footprint candidate from the reviewed set
- best choice when memory or startup speed matters more than absolute retrieval quality

Practical footprint:

- the card lists `Q8_0` at about `639 MB`
- `F16` is about `1.2 GB`

## 3. Qwen3-Embedding-8B-GGUF

Hugging Face:

- https://huggingface.co/Qwen/Qwen3-Embedding-8B-GGUF

Key findings:

- 8B parameters
- official GGUF release
- `Q4_K_M` listed at about `4.68 GB`
- part of the same Qwen3 embedding family with multilingual, long-context, and code retrieval emphasis

Fit assessment:

- strongest quality option in the reviewed Qwen family
- probably overkill for a first local deployment unless retrieval quality is the top priority and the extra memory cost is acceptable

## 4. BAAI/bge-m3

Hugging Face:

- https://huggingface.co/BAAI/bge-m3

Key findings:

- supports dense, sparse, and multi-vector retrieval in one model
- supports more than 100 languages
- supports up to 8192 tokens
- the card explicitly recommends hybrid retrieval plus reranking for RAG

Fit assessment:

- technically very capable and still a strong retrieval baseline
- less natural fit for this repo than Qwen3 GGUF because the reviewed Hugging Face card is centered on the broader BGE ecosystem rather than a simple official GGUF + `llama-server` serving path

Inference:

- this looks strongest when you are prepared to build a richer retrieval stack around dense + sparse + reranking, not when you want the cleanest single-model local embeddings server

## 5. mixedbread-ai/mxbai-embed-large-v1

Hugging Face:

- https://huggingface.co/mixedbread-ai/mxbai-embed-large-v1

Key findings:

- strong English embedding model
- the card says retrieval queries should use the prompt
  `Represent this sentence for searching relevant passages:`
- supports Matryoshka representation learning and quantization
- the card reports strong March 2024 MTEB results and compares favorably with `text-embedding-3-large`

Fit assessment:

- still a serious option for English-heavy retrieval
- not the best fit for this repo because the reviewed usage path is centered on `sentence-transformers`, `transformers`, API serving, and Infinity rather than the repo's existing `llama.cpp`-first workflow

Inference:

- good model, but adopting it cleanly here would likely mean introducing a separate embeddings-serving stack instead of reusing the local GGUF tooling pattern

## 6. nomic-embed-text-v1.5-GGUF

Hugging Face:

- https://huggingface.co/nomic-ai/nomic-embed-text-v1.5-GGUF

Key findings:

- official GGUF release
- explicitly llama.cpp-compatible
- requires task instruction prefixes such as `search_query:`
- llama.cpp compatibility is called out directly in the model card
- the card notes llama.cpp defaults to 2048 context here unless you apply a context-extension method for the full 8192-token behavior
- very small quantized sizes, including `Q4_K_M` at roughly `81 MiB`

Fit assessment:

- very attractive if tiny footprint is the main requirement
- weaker choice than Qwen3 for a new deployment because it is older and its required task prefixes add operational sharp edges

Inference:

- this is a strong "small and easy to host" fallback, not the current best-quality option

## Summary Table

| Model | Strength | Weakness | Fit For This Repo |
|------|------|------|------|
| `Qwen3-Embedding-4B-GGUF` | Best balance of quality and local practicality | Heavier than tiny models | Best overall |
| `Qwen3-Embedding-0.6B-GGUF` | Strong lightweight option | Lower ceiling than 4B/8B | Best lightweight |
| `Qwen3-Embedding-8B-GGUF` | Highest quality of reviewed Qwen options | More memory | Best max-quality |
| `BAAI/bge-m3` | Dense + sparse + multilingual versatility | Less direct fit with current serving pattern | Good advanced option |
| `mxbai-embed-large-v1` | Strong English retrieval | Not GGUF-first in the reviewed path | Good if adding separate stack |
| `nomic-embed-text-v1.5-GGUF` | Extremely small and llama.cpp-friendly | Older and prefix-sensitive | Good tiny fallback |

## Final recommendation

If the goal is "state of the art and compatible for local use" in this repo, the best next move is:

1. adopt `Qwen/Qwen3-Embedding-4B-GGUF`
2. serve it separately from the chat model
3. expose it as the local embeddings endpoint for RAG and Open WebUI

Why this recommendation is defensible:

- Qwen's own Hugging Face cards present the strongest current benchmark story among the reviewed candidates
- the family has an official GGUF distribution
- the card explicitly documents `llama.cpp` / `llama-server` usage
- the 4B size is large enough to be serious and small enough to be practical

## Sources

- Qwen3-Embedding-4B-GGUF: https://huggingface.co/Qwen/Qwen3-Embedding-4B-GGUF
- Qwen3-Embedding-0.6B-GGUF: https://huggingface.co/Qwen/Qwen3-Embedding-0.6B-GGUF
- Qwen3-Embedding-8B-GGUF: https://huggingface.co/Qwen/Qwen3-Embedding-8B-GGUF
- BAAI/bge-m3: https://huggingface.co/BAAI/bge-m3
- mixedbread-ai/mxbai-embed-large-v1: https://huggingface.co/mixedbread-ai/mxbai-embed-large-v1
- nomic-embed-text-v1.5-GGUF: https://huggingface.co/nomic-ai/nomic-embed-text-v1.5-GGUF
