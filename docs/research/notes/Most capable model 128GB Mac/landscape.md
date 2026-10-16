# Most Capable Open-Weight LLMs for Local Inference on a 128GB Mac (as of October 2026)

Methodology note: all specs, licenses, and GGUF file sizes below were pulled directly from the Hugging Face API and model cards / GGUF repo file listings on 2026-10-10. Anything not directly verified is labeled "est." (parameter-derived estimate) or listed under Gaps. "Params" = total parameters from the safetensors index; "active" = experts activated per token (MoE).

## Key Question 1: What are the most capable open-weight models as of October 2026?

### Takeaway
The 2025–2026 open-weight frontier is dominated by enormous MoE flagships (Qwen3.8-2.4T, Kimi K3 2.8T, DeepSeek-V4-Pro 1.6T, GLM-5.x 753B) that cannot fit in 128GB, but each lab also ships a mid-size "flash/air" MoE deliberately aimed at this class of hardware. For a 128GB Mac the practical frontier is: **Qwen3.8-Flash-Next (180B disk / 6B active), Qwen3.5-122B-A10B, DeepSeek-V4-Flash (284B/A13B, ~3-bit only), GLM-5.3-Flash (320B/A18B, ≤2.5-bit only), MiniMax-M2.5 (229B/A10B, ~3-bit)**, with **Qwen3-Coder-Next (80B/A3B)** as the coding specialist and **Qwen3.8-27B (dense, native vision)** as the fast general workhorse.

### Cited Findings

**Qwen (Alibaba)**
- Qwen3.5 family (Feb–Mar 2026): `Qwen3.5-122B-A10B` (125.1B total, Apache-2.0, native vision-language, 262,144 native context extensible to 1,010,000) and flagship `Qwen3.5-397B-A17B` (403.4B total, Apache-2.0) — [Qwen/Qwen3.5-122B-A10B](https://huggingface.co/Qwen/Qwen3.5-122B-A10B), [Qwen/Qwen3.5-397B-A17B](https://huggingface.co/Qwen/Qwen3.5-397B-A17B)
- Qwen3.5 also includes 35B-A3B, 27B, 9B, 4B, 2B, 0.8B dense/MoE variants, all with unsloth GGUFs — [unsloth Qwen3.5 repos](https://huggingface.co/unsloth)
- Qwen3.8 series (Aug 2026): `Qwen3.8-27B` (27.8B dense, Apache-2.0, 262k native ctx, native image+video understanding, thinking control via `reasoning_effort`) is the single most-downloaded new LLM of 2026 (6.77M downloads on the base repo, 6.45M on unsloth GGUF, 17.4k likes) — [Qwen/Qwen3.8-27B](https://huggingface.co/Qwen/Qwen3.8-27B), [unsloth/Qwen3.8-27B-GGUF](https://huggingface.co/unsloth/Qwen3.8-27B-GGUF)
- `Qwen3.8-Flash-Next` (Aug 2026): 180B on disk ("125B with 6B activated, plus 51B n-gram embedding and 4B MTP"), hybrid Gated DeltaNet + Qwen Sparse Attention (QSA) + n-gram embeddings, native vision, 262,144 native ctx extensible to 1M; license `qwen-community-1.0` (custom, not Apache). Card states "**Qwen3.8-Flash** is the official version based on Qwen3.8-Flash-Next with more production features (1M context, built-in tools)" — i.e., Flash-Next is the open-weights artifact of the Qwen3.8 flagship line — [Qwen/Qwen3.8-Flash-Next](https://huggingface.co/Qwen/Qwen3.8-Flash-Next)
- `Qwen3.8-2.4T-A95B`: 2.45T total, 512 experts / 10 active per tok (~95B active), license `other` — far beyond 128GB — [Qwen/Qwen3.8-2.4T-A95B](https://huggingface.co/Qwen/Qwen3.8-2.4T-A95B)
- `Qwen3-Coder-Next` (Sep 2025, still current coding specialist): 79.7B total, 512 experts / 10 active (A3B class), hybrid linear attention (Qwen3Next arch), Apache-2.0, official GGUF published by Qwen itself — [Qwen/Qwen3-Coder-Next](https://huggingface.co/Qwen/Qwen3-Coder-Next), [Qwen/Qwen3-Coder-Next-GGUF](https://huggingface.co/Qwen/Qwen3-Coder-Next-GGUF)
- Legacy coder models `Qwen3-Coder-30B-A3B-Instruct` (30.5B, Apache-2.0) and `Qwen3-Coder-480B-A35B` remain available; no "Qwen3.5-Coder" or "Qwen3.8-Coder" official release found as of 2026-10-10 (only community finetunes) — [Qwen3-Coder-30B-A3B-Instruct](https://huggingface.co/Qwen/Qwen3-Coder-30B-A3B-Instruct); HF search for Qwen3.5-Coder returned only third-party repos

**GLM (Zhipu / zai-org)**
- GLM-5 series (Feb 2026) → GLM-5.1 (Apr) → GLM-5.2 (Jun) → GLM-5.3 (Aug 2026): all ~753–754B total MoE (`GlmMoeDsaForCausalLM`, 8 experts/tok); GLM-5.2 is MIT; GLM-5.3 license listed as `other` in API metadata — [zai-org/GLM-5](https://huggingface.co/zai-org/GLM-5), [GLM-5.2](https://huggingface.co/zai-org/GLM-5.2), [GLM-5.3](https://huggingface.co/zai-org/GLM-5.3)
- `GLM-5.3-Flash` (Aug 2026): "**320B total parameters and just 18B active parameters**, outperforms GLM-5.2 across benchmarks at one-tenth [the cost]"; first natively multimodal model in the GLM-5 series; hybrid architecture; MIT license; supports `reasoning_effort` low/high/max — [zai-org/GLM-5.3-Flash](https://huggingface.co/zai-org/GLM-5.3-Flash)
- GLM-4.7 (Dec 2025, 358.3B, MIT) and `GLM-4.7-Flash` (Jan 2026, 31.2B MoE, 64 experts with 4 routed + 1 shared active, MIT, 202,752 ctx) — [zai-org/GLM-4.7](https://huggingface.co/zai-org/GLM-4.7), [GLM-4.7-Flash](https://huggingface.co/zai-org/GLM-4.7-Flash)
- GLM-4.6 (Sep 2025, 356.8B, MIT) is the previous 355B-class workhorse; GLM-4.5-Air (106B-A12B, MIT) remains a known 128GB-class option but is two generations old — [GLM-4.6](https://huggingface.co/zai-org/GLM-4.6), [GLM-4.5-Air](https://huggingface.co/zai-org/GLM-4.5-Air)

**DeepSeek**
- DeepSeek-V4 (Apr 2026): "**DeepSeek-V4-Pro with 1.6T parameters (49B activated)** and **DeepSeek-V4-Flash with 284B parameters (13B activated)**", MIT license; V4-Flash has **1M context** (config: 1,048,576 via YaRN ×16, 256 routed experts, 6 active + 1 shared, hybrid Compressed Sparse Attention + Heavily Compressed Attention); card claims V4-Pro-Max is "the best open-source model available" and benchmarks it vs Claude Opus 4.6 / GPT-5.4 / Gemini 3.1 Pro / Kimi K2.6 Thinking / GLM-5.1 — [deepseek-ai/DeepSeek-V4-Flash](https://huggingface.co/deepseek-ai/DeepSeek-V4-Flash)
- Mid-2026 refreshes: V4-Flash-0731 (Jul 31), V4-Pro-0813 (Aug 13), V4-Flash-Vision-Exp (Aug 2026, experimental vision), and **DeepSeek-V4.1-Flash (Sep 10, 2026): "552B backbone parameters," multimodal, 1M ctx, Causal Encoder-Decoder (CED) architecture, CSA2 attention**, MIT — [DeepSeek-V4.1-Flash](https://huggingface.co/deepseek-ai/DeepSeek-V4.1-Flash), [DeepSeek-V4-Flash-Vision-Exp](https://huggingface.co/deepseek-ai/DeepSeek-V4-Flash-Vision-Exp)
- DeepSeek-V3.2 (Dec 2025, 685B, MIT) and V3.2-Exp (Sep 2025, first CSA release) are the prior 671B-class generation; V3.1-Terminus (Sep 2025) — [DeepSeek-V3.2](https://huggingface.co/deepseek-ai/DeepSeek-V3.2)
- Also notable: DeepSeek-Math-V2 (Nov 2025), DeepSeek-OCR / OCR-2, and eagle3/dflash/dspark speculative-decoding draft modules for Qwen3/Gemma4 — [deepseek-ai org](https://huggingface.co/deepseek-ai)

**Kimi (Moonshot)**
- `Kimi-K3` (Jun 2026): "**2.8T-parameter** native multimodal agentic model… built on Kimi Delta Attention (KDA) and Attention Residuals (AttnRes), scales MoE sparsity with Stable LatentMoE, **activates 16 of 896 experts**"; license `kimi-k3` (custom); 11.6k likes, 1.16M downloads — the most-liked open model of 2026 — [moonshotai/Kimi-K3](https://huggingface.co/moonshotai/Kimi-K3)
- K2 lineage: K2-Instruct (1T/A32B, Jul 2025) → K2-Instruct-0905 → K2-Thinking (Nov 2025, 1.03T) → K2.5 (Jan 2026) → K2.6 (Apr 2026) → K2.7-Code (Jun 2026); all ~1.03T total (`KimiK25ForConditionalGeneration`), all far beyond 128GB — [Kimi-K2.5](https://huggingface.co/moonshotai/Kimi-K2.5), [Kimi-K2.6](https://huggingface.co/moonshotai/Kimi-K2.6), [Kimi-K2.7-Code](https://huggingface.co/moonshotai/Kimi-K2.7-Code)
- Smaller: Kimi-Linear-48B-A3B (hybrid linear attention, Oct 2025), Kimi-Dev-72B (coding), Kimi-VL-A3B — [Kimi-Linear-48B-A3B-Instruct](https://huggingface.co/moonshotai/Kimi-Linear-48B-A3B-Instruct)

**MiniMax**
- M2 lineage (all ~229B / 8 experts per tok): MiniMax-M2 (Oct 2025) → M2.1 (Dec 2025) → **M2.5 (Feb 2026, Modified-MIT)** → M2.7 (Apr 2026) — [MiniMaxAI/MiniMax-M2.5](https://huggingface.co/MiniMaxAI/MiniMax-M2.5), [MiniMax-M2.7](https://huggingface.co/MiniMaxAI/MiniMax-M2.7)
- `MiniMax-M3` (Jun 2026): 427B (`MiniMaxM3SparseForConditionalGeneration`), license `other` — [MiniMaxAI/MiniMax-M3](https://huggingface.co/MiniMaxAI/MiniMax-M3)
- `MiniMax-H3` (Jul 2026): 33.1B, 3.6M downloads, unsloth GGUF has 1.76M downloads — extremely popular, but its nature (text LLM vs media model) could not be confirmed from available data (see Gaps) — [MiniMaxAI/MiniMax-H3](https://huggingface.co/MiniMaxAI/MiniMax-H3)

**OpenAI gpt-oss**
- `gpt-oss-120b` (Aug 2025): 116.8B total / 5.1B active (4 experts/tok), Apache-2.0, native MXFP4; still in the top-3 most-downloaded open LLMs (3.85M downloads) but now ~14 months old and superseded by 2026 releases in capability — [openai/gpt-oss-120b](https://huggingface.co/openai/gpt-oss-120b)
- gpt-oss-safeguard-120b/20b (Sep 2025) are safety-classifier variants; no gpt-oss successor found as of Oct 2026 — [openai org](https://huggingface.co/openai)

**Meta Llama**
- No Llama 5 found: the newest meta-llama repos are from April 2025 (Llama 4). HF search for "Llama-5" returns only unrelated repos — [meta-llama org](https://huggingface.co/meta-llama), HF search "Llama-5"
- Llama-4-Scout-17B-16E (108.6B total / 17B active, Llama 4 Community License) and Maverick-17B-128E (~400B/17B active) from Apr 2025 are now two generations behind the Chinese 2026 releases — [Llama-4-Scout-17B-16E-Instruct](https://huggingface.co/meta-llama/Llama-4-Scout-17B-16E-Instruct)

**Google Gemma**
- Gemma 4 (Mar–Jun 2026): `gemma-4-31B-it` (31.3B dense, Apache-2.0), `gemma-4-26B-A4B-it` (25.8B MoE, Apache-2.0), gemma-4-12B-it, gemma-4-E2B/E4B; official QAT q4_0/w4a16 releases; 31B-it has 9.6M downloads — [google/gemma-4-31B-it](https://huggingface.co/google/gemma-4-31B-it), [gemma-4-26B-A4B-it](https://huggingface.co/google/gemma-4-26B-A4B-it)

**Mistral**
- `Mistral-Large-3-675B-Instruct-2512` (Dec 2025, 675B, Apache-2.0) — flagship, far beyond 128GB — [mistralai/Mistral-Large-3-675B-Instruct-2512](https://huggingface.co/mistralai/Mistral-Large-3-675B-Instruct-2512)
- `Mistral-Small-4-119B-2603` (Jan 2026): 119.4B **dense**, Apache-2.0, multimodal (text+image in), 256k context — [mistralai/Mistral-Small-4-119B-2603](https://huggingface.co/mistralai/Mistral-Small-4-119B-2603)
- `Mistral-Medium-3.5-128B` (Mar 2026): 127.7B dense, license `other` (Mistral research-style license expected, unverified) — [mistralai/Mistral-Medium-3.5-128B](https://huggingface.co/mistralai/Mistral-Medium-3.5-128B)
- Ministral-3 (3B/8B/14B, Oct 2025, with official Mistral GGUFs and Reasoning variants), Devstral-2-123B / Devstral-Small-2-24B (coding, Nov 2025), `Leanstral-1.5-119B-A6B` (Jul 2026, 119B MoE / 6B active, Apache-2.0) — [mistralai org](https://huggingface.co/mistralai)

**Microsoft Phi**
- No Phi-5 found as of Oct 2026; the notable recent Phi release is `Phi-4-reasoning-vision-15B` (15B, vision reasoning). Phi is no longer competitive at the 128GB scale — [microsoft/Phi-4-reasoning-vision-15B](https://huggingface.co/microsoft/Phi-4-reasoning-vision-15B)

### Inferences
- Benchmark fragments on the DeepSeek-V4 and GLM-5.3-Flash cards (SWE Verified ~80.6 for V4-Pro-Max; Terminal-Bench 2.x, DeepSWE, FrontierSWE evals at 1M context) indicate the 2026 frontier models are explicitly positioned as coding/agentic models evaluated with Claude-Code-style harnesses — the same use case as this repo's local assistant.
- The "flash/air" tier (GLM-5.3-Flash A18B, DeepSeek-V4-Flash A13B, Qwen3.8-Flash-Next A6B, Qwen3.5-122B A10B, MiniMax-M2.5 A10B-class) is where the 128GB class now lives; each flagship family has a corresponding mid-size member.
- Qwen3.8-27B's extraordinary download numbers (6.4M+ GGUF downloads within ~2 months) suggest it is the consensus "best small local model" of late 2026, analogous to Qwen3-30B-A3B in 2025.
- Wildcard community quant "GSQ-RCO" (ISTA-DASLab) with millions of downloads on Qwen3.8 models implies a new popular quant format in 2026; its exact meaning could not be verified (see Gaps).

### Gaps
- Exact benchmark scores (SWE-bench Verified, LCB, etc.) for Qwen3.5/Qwen3.8/GLM-5.3-Flash were not extracted (cards embed scores in HTML tables); only relative claims were captured.
- GLM-5.3's exact active parameter count and official context length; GLM-5.3's license terms (API says `other` while GLM-5.2 is MIT).
- What MiniMax-H3 is (text LLM vs. media model) — 33B with massive downloads and LoRA ecosystems suggesting video; unconfirmed.
- r/LocalLLaMA sentiment and HN discussion for "best model for 128GB Mac in 2026" were not queried (tool-call budget); download/like counts were used as popularity proxies instead.
- No official "Qwen3.5-Coder"/"Qwen3.8-Coder" or Llama 5 / DeepSeek-R2 branding found; absence verified only via HF search, not announcements.

## Key Question 2: Per-model specs — params, active params, context, license, GGUF availability, quant file sizes

### Takeaway
Every relevant 2026 model has unsloth GGUFs (bartowski covers the Qwen3.5/GLM families too; Qwen publishes official GGUF for Qwen3-Coder-Next). Real file sizes at Q4_K_M: **Qwen3.5-122B ≈ 76.5GB, Qwen3.8-Flash-Next ≈ 111GB (UD-Q4_K_XL), MiniMax-M2.5 ≈ 138GB, DeepSeek-V4-Flash ≈ 137–155GB, GLM-5.3-Flash ≈ 157–200GB**, vs 16.5GB for Qwen3.8-27B and 48.4GB for Qwen3-Coder-Next.

### Cited Findings
Verified GGUF file sizes (unsloth / official repos, 2026-10-10):

| Model (total/active) | License | Q4 class | Q5 class | Q6 class | Q8 class | GGUF source |
|---|---|---|---|---|---|---|
| Qwen3.5-122B-A10B (125B/A10B) | Apache-2.0 | Q4_K_M **76.5GB**; MXFP4_MOE 74.7; UD-Q4_K_XL 77.0; IQ4_XS 60.2 | Q5_K_M 91.5; UD-Q5_K_XL 91.9 | Q6_K 101.0; UD-Q6_K_XL 112.4 | Q8_0 129.9 | [unsloth/Qwen3.5-122B-A10B-GGUF](https://huggingface.co/unsloth/Qwen3.5-122B-A10B-GGUF) (also [bartowski](https://huggingface.co/bartowski/Qwen_Qwen3.5-122B-A10B-GGUF), MTP variant) |
| Qwen3.8-Flash-Next (180B disk / 6B active + n-gram) | qwen-community-1.0 | UD-Q4_K_XL **111.3GB**; UD-IQ4_XS 93.7 | UD-Q5_K_XL 158.3 | UD-Q6_K_XL 169.2 | Q8_0 188.2 | [unsloth/Qwen3.8-Flash-Next-GGUF](https://huggingface.co/unsloth/Qwen3.8-Flash-Next-GGUF) (incl. MTP draft modules for spec. decoding) |
| Qwen3-Coder-Next (79.7B/A3B-class) | Apache-2.0 | Q4_K_M **48.4GB** | Q5_K_M 56.7 | Q6_K 65.5 | Q8_0 84.8 | [Qwen/Qwen3-Coder-Next-GGUF](https://huggingface.co/Qwen/Qwen3-Coder-Next-GGUF) (official) |
| MiniMax-M2.5 (228.7B / ~10B-class, 8 experts/tok) | Modified-MIT | Q4_K_M **138.3GB**; IQ4_XS 121.9; MXFP4_MOE 123.8 | Q5_K_M 162.3 | Q6_K 187.8 | Q8_0 243.1 | [unsloth/MiniMax-M2.5-GGUF](https://huggingface.co/unsloth/MiniMax-M2.5-GGUF) (low: Q3_K_M 109.3, UD-Q3_K_XL 101.3, UD-TQ1_0 55.8) |
| DeepSeek-V4-Flash-0731 (284B/A13B) | MIT | UD-IQ4_XS **136.7GB**; UD-Q4_K_XL 155.1 | — | — | UD-Q8_K_XL 161.9 | [unsloth/DeepSeek-V4-Flash-0731-GGUF](https://huggingface.co/unsloth/DeepSeek-V4-Flash-0731-GGUF) (low: UD-IQ3_S 116.1, UD-Q3_K_XL 128.2, UD-Q2_K_XL 96.8; +dspark draft 10.9GB) |
| GLM-5.3-Flash (320B/A18B) | MIT | UD-IQ4_XS **156.8GB**; UD-Q4_K_XL 199.7 | UD-Q5_K_XL 240.3 | UD-Q6_K_XL 291.8 | Q8_0 341.0 | [unsloth/GLM-5.3-Flash-GGUF](https://huggingface.co/unsloth/GLM-5.3-Flash-GGUF) (low: UD-IQ3_XXS 120.4, UD-Q2_K_XL 108.7, UD-IQ2_XXS 101.8, UD-IQ1_M 97.6; mmproj vision files incl.) — also [bartowski BF16 repo](https://huggingface.co/bartowski/GLM-5.3-Flash-BF16-GGUF) |
| Qwen3.8-27B (27.8B dense) | Apache-2.0 | Q4_K_M **16.5GB**; Q4_K_XL 17.6 | Q5_K_M 19.8 | Q6_K 22.0 | Q8_0 29.0 | [unsloth/Qwen3.8-27B-GGUF](https://huggingface.co/unsloth/Qwen3.8-27B-GGUF) (27 quants incl. UD + QAT-style variants; mmproj vision files) |

Source URLs for specs: [Qwen3.5-122B-A10B](https://huggingface.co/Qwen/Qwen3.5-122B-A10B), [Qwen3.8-Flash-Next](https://huggingface.co/Qwen/Qwen3.8-Flash-Next), [Qwen3-Coder-Next](https://huggingface.co/Qwen/Qwen3-Coder-Next), [MiniMax-M2.5](https://huggingface.co/MiniMaxAI/MiniMax-M2.5), [DeepSeek-V4-Flash](https://huggingface.co/deepseek-ai/DeepSeek-V4-Flash), [GLM-5.3-Flash](https://huggingface.co/zai-org/GLM-5.3-Flash), [Qwen3.8-27B](https://huggingface.co/Qwen/Qwen3.8-27B), [gpt-oss-120b](https://huggingface.co/openai/gpt-oss-120b), [Mistral-Small-4-119B-2603](https://huggingface.co/mistralai/Mistral-Small-4-119B-2603), [gemma-4-31B-it](https://huggingface.co/google/gemma-4-31B-it), [Kimi-K3](https://huggingface.co/moonshotai/Kimi-K3).

Additional model facts (from HF API metadata + cards):
- Context windows (verified): Qwen3.5-122B-A10B 262,144 native → ~1.01M extended; Qwen3.8-Flash-Next 262,144 native → 1M; DeepSeek-V4-Flash 1,048,576; MiniMax-M2.5 196,608; GLM-4.7-Flash 202,752; Mistral-Small-4 256k; gpt-oss-120b 131k (Aug 2025 launch spec).
- Active parameters (verified from cards): GLM-5.3-Flash 18B; DeepSeek-V4-Flash 13B; DeepSeek-V4-Pro 49B; Qwen3.8-Flash-Next 6B (+51B offloadable n-gram embedding, +4B MTP); Kimi K3 = 16 of 896 experts of 2.8T; Qwen3.5-122B = A10B (name); gpt-oss-120b = 5.1B; Llama-4-Scout = 17B.
- GGUF ecosystem breadth: unsloth ships GGUF for GLM-5/5.1/5.2/5.3(-Flash), DeepSeek-V4-Flash(0731)/Pro-0813/Vision-Exp, all Qwen3.5 sizes (+MTP speculative variants), Qwen3.8-27B/Flash-Next/2.4T, MiniMax-M2/M2.1/M2.5/M2.7/M3/H3, Kimi-K3/K2.x/K2-Thinking — [unsloth](https://huggingface.co/unsloth); bartowski covers Qwen3.5 family and GLM-5.3-Flash-BF16 among others — [bartowski](https://huggingface.co/bartowski)

### Inferences
- Estimated sizes for models whose GGUF files were not directly listed (using the measured ratio from Qwen3.5-122B: Q4_K_M ≈ 0.61, Q5_K_M ≈ 0.73, Q6_K ≈ 0.81, Q8_0 ≈ 1.04 GB/param): Mistral-Small-4-119B ≈ 73 / 87 / 97 / 124GB; Mistral-Medium-3.5-128B ≈ 78 / 93 / 103 / 133GB; gpt-oss-120b ≈ 63GB at native MXFP4 (known) and ≈ 121GB at Q8; Llama-4-Scout ≈ 66 / 79 / 88 / 113GB; Gemma-4-31B ≈ 19GB at Q4; GLM-4.7-Flash ≈ 19GB at Q4; Qwen3.5-35B-A3B ≈ 22GB at Q4. All "est." values.
- GLM-4.7-Flash (31B MoE with only 4+1 experts active of 64, 2048 hidden size) is likely the GLM-4.5-Air/30B-A3B successor class, i.e., ~2–3B active — very fast on Apple Silicon (est.).

### Gaps
- GLM-5.3-Flash context window not stated in the captured card text (evals reference 400K and 1M contexts); GLM-4.x heritage suggests ≥200K (unverified).
- Kimi K3 / K2.5 exact context window and license terms (custom `kimi-k3` license) not captured — irrelevant for 128GB fit anyway.
- Unsloth "UD-*" and new-format quants (MXFP4_MOE folders, UD-TQ1_0 ternary, "GSQ-RCO") — exact llama.cpp version requirements unverified.
- Qwen3-Coder-Next official GGUF lacks UD dynamic quants from Qwen (only standard Q4_K_M–Q8); unsloth dynamic-quant version not confirmed to exist.

## Key Question 3: What fits in ~100–120GB of unified memory on a 128GB Mac?

### Takeaway
**Comfortable fits at usable (≥Q4) quant: Qwen3.5-122B-A10B (76–112GB), Qwen3-Coder-Next (48–85GB), Qwen3.8-27B, GLM-4.7-Flash, Gemma-4-31B/26B-A4B, Qwen3.5-35B-A3B, gpt-oss-120b (~63GB), Mistral-Small-4-119B (~73–97GB, est.), Llama-4-Scout (~66–88GB, est.), and — the capability ceiling — Qwen3.8-Flash-Next at UD-Q4_K_XL (111.3GB, tight). Borderline: MiniMax-M2.5 (Q3-class only, 101–122GB), DeepSeek-V4-Flash (IQ3_S 116GB, tight). Effectively does not fit at usable quality: GLM-5.3-Flash (needs ≤2.5-bit for ~100–120GB). Completely impossible: all ≥355B flagships (GLM-4.6/4.7/5.x, Kimi K2.x/K3, DeepSeek V3.2/V4-Pro/V4.1, Qwen3.5-397B/Qwen3.8-2.4T, MiniMax-M3, Mistral-Large-3-675B, Llama-4-Maverick).**

### Cited Findings
- macOS does not make all 128GB available to the GPU/model (default wired limit is ~75% ≈ 96GB, adjustable via `iogpu.wired_limit_mb`); practical weight budget with KV cache is ~100–120GB (platform knowledge; not source-verified in this research).
- Verified sizes driving the verdicts: Qwen3.5-122B Q4_K_M 76.5GB / Q6_K 101.0GB / Q8_0 129.9GB — [unsloth repo](https://huggingface.co/unsloth/Qwen3.5-122B-A10B-GGUF); Qwen3.8-Flash-Next UD-Q4_K_XL 111.3GB / UD-IQ4_XS 93.7GB — [unsloth repo](https://huggingface.co/unsloth/Qwen3.8-Flash-Next-GGUF); MiniMax-M2.5 Q4_K_M 138.3GB but Q3_K_M 109.3GB / UD-Q3_K_XL 101.3GB / IQ4_XS 121.9GB — [unsloth repo](https://huggingface.co/unsloth/MiniMax-M2.5-GGUF); DeepSeek-V4-Flash-0731 UD-IQ3_S 116.1GB / UD-Q3_K_XL 128.2GB / IQ4_XS 136.7GB — [unsloth repo](https://huggingface.co/unsloth/DeepSeek-V4-Flash-0731-GGUF); GLM-5.3-Flash UD-IQ1_M 97.6 / IQ2_XXS 101.8 / Q2_K_XL 108.7 / IQ3_XXS 120.4 / IQ4_XS 156.8GB — [unsloth repo](https://huggingface.co/unsloth/GLM-5.3-Flash-GGUF); Kimi-K3 2.78T total (even ~1-bit would exceed 300GB; no quant listed below the mmproj files in the captured listing) — [unsloth/Kimi-K3-GGUF](https://huggingface.co/unsloth/Kimi-K3-GGUF), [moonshotai/Kimi-K3](https://huggingface.co/moonshotai/Kimi-K3)
- Flagship sizes that rule them out: GLM-5.3/GLM-5.2/GLM-5 = 753–754B; GLM-4.7/4.6 = 358/357B; DeepSeek-V4-Pro = 1.6T; V4.1-Flash = 552B backbone (763B w/ vision per API); V3.2 = 685B; Kimi K2.5/K2.6/K2.7 = 1.03T; K3 = 2.78T; Qwen3.5-397B = 403B; Qwen3.8-2.4T = 2.45T; MiniMax-M3 = 427B; Mistral-Large-3-675B; Llama-4-Maverick ≈ 400B — all with HF API param counts cited in Key Q1.
- MoE active parameters (the driver of Apple Silicon generation speed): Qwen3.8-Flash-Next 6B active is the fastest frontier-class option; A10B-class (Qwen3.5-122B, MiniMax-M2.5) mid; A13B (V4-Flash), A17B (Scout/Maverick), A18B (GLM-5.3-Flash) slower per token; dense 119–128B Mistral models slowest of the fitting set (~5–8× fewer FLOPs-efficient than A10B MoE) — active counts cited in Key Q1/Q2.

### Inferences
- Recommended shortlist for this repo's llama-server use case (coding/agentic + general): (1) **Qwen3.8-Flash-Next** at UD-Q4_K_XL/IQ4_XS for maximum capability in budget; (2) **Qwen3.5-122B-A10B** at Q4_K_M–Q6_K as the Apache-2.0 all-rounder with vision and room for large KV cache; (3) **Qwen3-Coder-Next** at Q6_K/Q8 as a dedicated fast coder; (4) **Qwen3.8-27B** at Q6_K as the low-latency daily driver; (5) MiniMax-M2.5 UD-Q3_K_XL / DeepSeek-V4-Flash UD-IQ3_S only if ~3-bit quality is acceptable.
- GLM-5.3-Flash at 2-bit (108.7GB UD-Q2_K_XL) likely loses more quality than the 3-bit DeepSeek/MiniMax alternatives; on a strict 128GB machine it is dominated by Qwen3.8-Flash-Next — but on a 192GB+ machine it becomes the top pick (MIT, A18B, native multimodal).
- MTP/speculative-decoding artifacts shipped inside unsloth GGUF repos (Qwen3.5 MTP-GGUF variants, Qwen3.8-Flash-Next MTP modules, DeepSeek dspark drafts) imply 2026 llama.cpp supports MTP-style speculative decoding — a significant Apple-Silicon speed lever (support level unverified, see Gaps).

### Gaps
- No measured tok/s numbers on M2/M3/M4 Ultra hardware were collected (no benchmark source fetched); speed statements are inferences from active-parameter counts.
- llama.cpp version support matrix for `qwen4_exp` (Qwen3.8-Flash-Next), `glm5_next`, `deepseek_v4`, and `kimi_k3` architectures was not verified against the llama.cpp repo — presence of unsloth GGUFs implies support but merge dates/issues were not checked.
- Exact KV-cache GB per token at 128–256k context for the shortlist models was not computed.

## Key Question 4: Multimodal (vision) capability

### Takeaway
2026 mid-size flagships are natively multimodal out of the box: **Qwen3.5-122B-A10B, Qwen3.8-Flash-Next (and Qwen3.8-27B), GLM-5.3-Flash, DeepSeek-V4.1-Flash, and Kimi K3** all ship vision (K3 and Qwen3.8 also video) — with mmproj files included in the unsloth GGUFs for llama.cpp vision support. DeepSeek's base V4-Flash is text-only, with vision only in the experimental `V4-Flash-Vision-Exp` snapshot; Mistral-Small-4 is text+image-in; Gemma 4 continues Gemma's vision tradition (not individually re-verified).

### Cited Findings
- Qwen3.5-122B-A10B: "Unified Vision-Language Foundation: early fusion training… outperforms Qwen3-VL models" and card lists extensive Vision-Language benchmarks; unsloth GGUF includes mmproj-BF16/F16 files — [model card](https://huggingface.co/Qwen/Qwen3.5-122B-A10B), [unsloth GGUF](https://huggingface.co/unsloth/Qwen3.5-122B-A10B-GGUF)
- Qwen3.8-Flash-Next: "Type: Causal Language Model with Vision Encoder," with VL benchmark tables; Qwen3.8-27B: "Native support for image and video understanding, from STEM diagrams and documents to hour-scale videos"; both GGUFs include mmproj files — [Qwen3.8-Flash-Next](https://huggingface.co/Qwen/Qwen3.8-Flash-Next), [Qwen3.8-27B](https://huggingface.co/Qwen/Qwen3.8-27B), [unsloth GGUFs](https://huggingface.co/unsloth/Qwen3.8-27B-GGUF)
- GLM-5.3-Flash: "the first natively multimodal model in the GLM-5 series"; unsloth GGUF includes mmproj-BF16/F16 — [GLM-5.3-Flash](https://huggingface.co/zai-org/GLM-5.3-Flash)
- DeepSeek-V4.1-Flash: "a multimodal MoE model with 552B backbone parameters… natively processes image[s]"; base DeepSeek-V4-Flash card describes text-only MoE, vision exists only as `DeepSeek-V4-Flash-Vision-Exp` (Aug 2026) — [V4.1-Flash](https://huggingface.co/deepseek-ai/DeepSeek-V4.1-Flash), [V4-Flash-Vision-Exp](https://huggingface.co/deepseek-ai/DeepSeek-V4-Flash-Vision-Exp)
- Kimi-K3: "open-weight, native multimodal agentic model" (2.8T, video-capable per K3 family marketing; too large for 128GB regardless) — [Kimi-K3](https://huggingface.co/moonshotai/Kimi-K3)
- Mistral-Small-4-119B: "Multimodal input: accepts both text and image input, with text output," 256k ctx — [model card](https://huggingface.co/mistralai/Mistral-Small-4-119B-2603)
- Dedicated small vision models remain separate: GLM-4.6V/GLM-4.5V (vision GLMs), Qwen3-VL lineage superseded by unified Qwen3.5, Gemma-4 (31B/26B/12B), Phi-4-reasoning-vision-15B — [GLM-4.6V](https://huggingface.co/zai-org/GLM-4.6V), [Phi-4-reasoning-vision-15B](https://huggingface.co/microsoft/Phi-4-reasoning-vision-15B)

### Inferences
- For a single-model 128GB setup, vision now comes free with Qwen3.5-122B-A10B or Qwen3.8-Flash-Next (mmproj included in llama.cpp GGUFs), removing the need to swap in a separate VL model for screenshot/image understanding in an agentic workflow.
- Text-only outliers worth knowing: DeepSeek-V4-Flash (vision only in an experimental branch) and Qwen3-Coder-Next (pure coder).

### Gaps
- Whether Gemma-4's llama.cpp GGUF vision (mmproj) support is on par with Qwen/GLM was not verified.
- Exact vision benchmark scores for the fitting models were not extracted (HTML table extraction skipped).
- MiniMax-H3's modality (and thus its relevance) unconfirmed.

## Secondary note: MLX

- MLX conversions of the 2026 models exist in the community (e.g., `mlx-community/gemma-4-12b-coder…4bit`, `snsnc/qwen3.5-4B-super-coder-MLX-4bit`); MLX can offer higher tok/s on Apple Silicon than llama.cpp for supported architectures, but this research focused on llama.cpp/GGUF per the assignment; new 2026 architectures (qwen4_exp, glm5_next, deepseek_v4) may land in GGUF/llama.cpp before MLX — [mlx-community](https://huggingface.co/mlx-community), [snsnc MLX example](https://huggingface.co/snsnc/qwen3.5-4B-super-coder-MLX-4bit)
