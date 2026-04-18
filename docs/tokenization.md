# Tokenization

Tokenization is the process of splitting text into the discrete units a model processes.
Understanding it is essential for working with embedding models because token counts — not
character counts — determine whether a text fits in a model's context window, how chunking
interacts with model limits, and why costs and latency vary with input length.

Related documents:

- How tokens become embeddings: [foundations-what-is-an-embedding.md](foundations-what-is-an-embedding.md)
- How chunk sizes relate to token limits: [chunking-strategies.md](chunking-strategies.md)

---

## Why tokens, not words or characters?

Early NLP systems split on whitespace: each word is a unit. This breaks down on several
practical problems:

- **Vocabulary explosion.** English has hundreds of thousands of words, and new ones are
  coined constantly. A word-level vocabulary must either be huge or mark unknown words as
  `[UNK]`, losing all information about them.
- **Morphological variants.** "run", "runs", "running", "ran" are four different vocabulary
  entries that share almost all meaning. A word-level model treats them as unrelated.
- **Multilinguality.** Japanese and Chinese have no spaces. Arabic and Hebrew write without
  vowels. A word tokenizer that splits on spaces fails silently.

Character-level tokenization solves the vocabulary problem (26 letters + punctuation is a
tiny vocabulary) but produces very long sequences. Attention is O(n²) in sequence length, so
character sequences are expensive to process.

**Subword tokenization** — the dominant approach — sits between the two. Common words stay
as single tokens. Rare words are split into meaningful subword pieces. Sequences stay short
enough for efficient attention.

---

## BPE (Byte Pair Encoding)

BPE is the most widely used tokenization algorithm (GPT-2 through GPT-4o, LLaMA, Qwen, Mistral).

**How it works:**

1. Start with a vocabulary of individual characters (or bytes).
2. Count all adjacent pairs in the training corpus.
3. Merge the most frequent pair into a new token.
4. Repeat until the vocabulary reaches the target size (typically 32k–128k tokens).

**Example:**

Training text: `"low lower lowest lower low"`

```
Initial: l o w   l o w e r   l o w e s t   l o w e r   l o w
Step 1: merge 'l'+'o' → 'lo' (most frequent pair)
        lo w   lo w e r   lo w e s t   lo w e r   lo w
Step 2: merge 'lo'+'w' → 'low'
        low   low e r   low e s t   low e r   low
Step 3: merge 'low'+'e' → 'lowe'
        low   lowe r   lowe s t   lowe r   low
...and so on
```

After training on a large corpus, common words like "the", "is", "model" are single tokens.
Rare words split into recognizable subwords: "tokenization" → ["token", "ization"].
Truly novel words split further: "Qwen3Embedding" → ["Qw", "en", "3", "Embed", "ding"].

**The byte-level variant** (used by GPT-2 and descendants) operates on raw bytes rather than
characters. This ensures any Unicode text can be tokenized without an unknown-token fallback,
at the cost of longer sequences for non-Latin scripts.

---

## WordPiece

Used by BERT and its descendants (including many embedding models like BGE, nomic-embed-text).

Conceptually similar to BPE, but merges are chosen to maximize the likelihood of the training
data under a language model, not just by raw pair frequency. Subword pieces are prefixed with
`##` to indicate they are continuations rather than word starts:

```
"playing" → ["play", "##ing"]
"unplayable" → ["un", "##play", "##able"]
```

---

## SentencePiece

Used by LLaMA, Mistral, and many multilingual models. Operates directly on raw text without
pre-tokenization (no whitespace splitting required first). Handles languages without spaces
naturally. The underlying algorithm is typically BPE or Unigram.

---

## Token count vs character count

A critical practical point: **model limits are in tokens, not characters or words**.

Approximate conversions for English text:

| Unit | Typical ratio |
|---|---|
| 1 token | ~4 characters |
| 1 token | ~0.75 words |
| 100 tokens | ~75 words, ~400 characters |
| 1,000 tokens | ~750 words, ~3–4 paragraphs |

These ratios are for English. Other languages differ:

| Language | Tokens per word (approx) |
|---|---|
| English | 1.3 |
| Spanish / French | 1.4 |
| German | 1.5 (compound words split more) |
| Chinese | 1.5–2.5 (ideographs are often multi-byte, multiple tokens each) |
| Arabic | 1.5–2.0 |
| Code (Python) | 2–4 (identifiers, indentation, symbols each tokenize separately) |

Code tokenizes much less efficiently than prose. A 100-line Python function may consume
300–500 tokens. This matters for code retrieval use cases where chunk size must be set by
token count, not character count.

---

## How token limits affect chunking

Every embedding model has a maximum context length:

| Model | Max tokens |
|---|---|
| BGE-small-en-v1.5 | 512 |
| nomic-embed-text-v1.5 | 8,192 |
| text-embedding-3-small | 8,191 |
| text-embedding-3-large | 8,191 |
| Qwen3-Embedding series | 32,768 |

**What happens when input exceeds the limit** depends on the implementation:

- **Truncation:** the model silently discards tokens beyond the limit. The embedding
  represents only the first N tokens. Content in the truncated portion is invisible to
  retrieval.
- **Error:** the API or model raises an error. Callers must pre-split.

Truncation is the silent failure mode. If your chunks regularly exceed the model's token
limit, you are losing content without any warning.

**Chunk size should be set in tokens, not characters**, when precision matters. For a 512-
token limit model with ~15% safety margin, target 435-token chunks. Converted to characters
at 4 chars/token: roughly 1,740 characters. memvid's default of 1,200 characters is
conservative for 512-token models and well within limits for 8K+ token models.

---

## Tokens and embedding quality

Shorter inputs produce different embeddings than longer ones because pooling collapses all
token vectors into one. A 5-token chunk and a 500-token chunk are both represented by a
single 1536-dim vector, but the 500-token vector averages over far more content.

Implications:

- **Very short chunks** (1–3 sentences) embed well — the vector captures the specific topic
  of that chunk cleanly.
- **Very long chunks** produce embeddings that represent a blend of all topics in the chunk.
  They retrieve for any of those topics at reduced precision.
- **Asymmetric retrieval:** a 10-word query embedding will not be close to a 2,000-token
  document embedding even if the document contains the answer, because the document's vector
  is averaged over content unrelated to the query. This is why chunking exists.

---

## Special tokens

Most models use reserved tokens for structural purposes:

| Token | Meaning | Models |
|---|---|---|
| `[CLS]` | Classification / sentence start | BERT-style |
| `[SEP]` | Separator between segments | BERT-style |
| `[PAD]` | Padding to uniform length | All |
| `[UNK]` | Unknown token (rare in modern BPE) | All |
| `<s>` | Sequence start | LLaMA/Mistral |
| `</s>` | Sequence end | LLaMA/Mistral |
| `<\|endoftext\|>` | End of text | GPT-2/3/4 |

Special tokens consume context window budget. A BGE model with a 512-token limit uses 2
special tokens (`[CLS]` and `[SEP]`), leaving 510 tokens for content.

For **CLS pooling** models, the `[CLS]` token is the output used as the embedding. For
**last-token pooling** models (Qwen3), the final real token (before `</s>`) is used.

---

## Counting tokens without running the model

Counting tokens before sending text to a model is useful for:
- Ensuring chunks stay within limits
- Estimating API cost
- Debugging "why is this chunk being truncated?"

**Python (HuggingFace tokenizers):**

```python
from transformers import AutoTokenizer

tokenizer = AutoTokenizer.from_pretrained("BAAI/bge-small-en-v1.5")
tokens = tokenizer.encode("The quick brown fox")
print(len(tokens))  # 6
```

**Python (tiktoken, for OpenAI models):**

```python
import tiktoken

enc = tiktoken.get_encoding("cl100k_base")  # used by text-embedding-3-*
tokens = enc.encode("The quick brown fox")
print(len(tokens))  # 5
```

**Rule of thumb without a tokenizer:**
Divide character count by 4 for English prose. This is accurate to ±20% for most inputs.
For code, divide by 3. For non-Latin scripts, divide by 2.

---

## Practical takeaways

- Token limits are per-model and in tokens, not characters. Check the model card.
- English prose: ~4 characters per token. Code: ~3 chars per token. CJK: ~2 chars per token.
- Exceeding the limit silently truncates the input in most implementations.
- Set chunk size in tokens when working with models near their 512-token limit; character
  estimates are close enough for 8K+ token models.
- Short chunks embed their specific topic precisely; long chunks produce averaged embeddings.
- Special tokens consume 2–4 tokens of context budget per call.
