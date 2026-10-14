# Small Open-Weight Document/PDF-Parsing Models — Landscape as of October 2026

Research date: 2026-10-13. Scope: dedicated + general models usable for PDF-page → markdown/structured parsing, ≤10B params preferred ≤8B, targeting a local stack of llama.cpp/GGUF (+mmproj) and MLX on Apple Silicon (M5 Max, 128GB).

Primary sources: Hugging Face model cards and API metadata (downloads/likes/dates pulled 2026-10-13), llama.cpp `docs/multimodal.md`, Datalab Surya/Chandra model cards (which reproduce olmOCR-bench and OmniDocBench tables). Reddit could not be fetched (HTTP 403) — community-consensus findings are inferred from HF download/like counts + published benchmark tables instead.

---

## Key Question 1: Which dedicated document-parsing models are current in late 2026, and what are their specs (params, arch, license, output, GGUF/MLX, runtime)?

### Takeaway
The field was reshuffled twice: a late-2025 wave (DeepSeek-OCR, PaddleOCR-VL, olmOCR-2, MinerU2.5, Nanonets-OCR2, Granite-Docling) followed by a 2026 wave (GLM-OCR, DeepSeek-OCR-2, Chandra-OCR-2, Surya-OCR-2, dots.mocr, Baidu Unlimited-OCR, PaddleOCR-VL-1.5/1.6, MinerU2.5-Pro/Flash). By Oct 2026 the quality frontier per olmOCR-bench is Chandra-OCR-2 (5.3B, 85.9), and the small-model sweet spot is held by GLM-OCR (0.9B, #1 OmniDocBench V1.5), Surya-OCR-2 (0.65B, 83.3 olmOCR-bench) and PaddleOCR-VL-1.6 (~0.9B) — all three with official GGUF and llama.cpp support. Most 2026-era dedicated models now run on llama.cpp with mmproj; the ones that still need custom NVIDIA-centric runtimes are DeepSeek-OCR-2 and Baidu Unlimited-OCR (pinned transformers/flash-attn, custom logit processors).

### Cited Findings

**2026-generation dedicated parsers (all verified on HF this session):**

| Model | Org / date | Params | Base arch | License | Output | GGUF | MLX | llama.cpp |
|---|---|---|---|---|---|---|---|---|
| GLM-OCR | zai-org, 2026-01-30 | 0.9B (CogViT encoder + GLM-0.5B decoder) | `glm_ocr` | MIT | text/table/formula prompts, JSON-schema IE; layout via PP-DocLayoutV3 in SDK | Official: ggml-org/GLM-OCR-GGUF | mlx-community/GLM-OCR-4bit | Yes (PR #19677) |
| DeepSeek-OCR-2 | deepseek-ai, 2026-01-27 | not stated on card (DeepSeek-OCR lineage MoE) | `deepseek_ocr2` (custom code; community transformers-native port exists) | Apache-2.0 | `<\|grounding\|>` markdown w/ layout, "Free OCR" | none found | none found | Unverified (PR #17400 covers DeepSeek-OCR v1 only) |
| Chandra-OCR-2 | datalab-to, 2026-03-16 | 5.3B | Qwen3.5 (`qwen3_5`) | Apache-2.0 code / modified OpenRAIL-M weights (free research/personal/startups <$2M; no competing with Datalab API) | markdown, HTML, JSON w/ layout bboxes | Community: prithivMLmods/chandra-ocr-2-GGUF | none found | via community GGUF (Qwen3.5 arch); unverified quality |
| dots.mocr | dots-studio, 2026-03-19 | 3.0B (per olmOCR-bench table) | `dots_mocr` (custom code) | MIT | layout/table/formula, document-parse JSON | none found | none found | None found (dots.ocr v1 = PR #17575) |
| Surya-OCR-2 | datalab-to, 2026-05-14 | 0.65B | Qwen3.5-style VLM + EfficientViT detector | Apache-2.0 code / OpenRAIL-M weights (free research/personal/startups <$5M) | HTML blocks w/ bboxes+labels, JSON layout (guided decode), tables, KaTeX math | Official: datalab-to/surya-ocr-2-gguf | none found | Yes — official backend; auto-spawns llama-server on CPU/Apple Silicon |
| PaddleOCR-VL-1.6 | PaddlePaddle, 2026-05-27 | ~0.9B (v1: NaViT + ERNIE-4.5-0.3B) | `paddleocr_vl` / ERNIE4.5 | Apache-2.0 | layout/table/formula/chart/seal/spotting; doc-parse | Official: PaddlePaddle/PaddleOCR-VL-1.6-GGUF (+1.5-GGUF) | mlx-community/PaddleOCR-VL-1.6-4bit | Yes (PR #18825) |
| MinerU2.5-Pro-2605 | opendatalab, 2026-05-20 | 1.2B | `qwen2_vl` | Apache-2.0 (older MinerU2.5-2509 is AGPL-3.0) | doc-parse (MinerU pipeline) | Community: mradermacher, jinzhenj, Mungert | none found | Likely (qwen2_vl base arch); unverified |
| MinerU2.5-Flash-0.8B | aijiag, 2026-10 | 0.8B | qwen3.5 + linear-attention | Apache-2.0 | pdf-to-markdown | mradermacher GGUF (days old) | none found | Unverified, very new |
| Unlimited-OCR | baidu, 2026-06-19 | not stated (MoE, DeepSeek-OCR-2 lineage) | custom code | MIT | one-shot multi-page PDF parsing, `<\|det\|>` bbox markers, 32K max length | Community: sahilchachra/Unlimited-OCR-GGUF (imatrix, "llama.cpp" tag) + AWQ | none found | Community GGUF claims llama.cpp; official paths are vLLM/SGLang with custom no-repeat-ngram logit processor |

- GLM-OCR: 0.9B, CogViT + GLM-0.5B decoder, MIT, OmniDocBench V1.5 score 94.62 (#1 overall), 1.7M downloads / 2,151 likes; served via vLLM, SGLang, transformers, Ollama; prompts are task-style ("Text Recognition:", "Table Recognition:", "Formula Recognition:") or strict-JSON information extraction; official SDK adds PP-DocLayoutV3 layout stage (layout model itself Apache-2.0). — [zai-org/GLM-OCR card](https://huggingface.co/zai-org/GLM-OCR), [HF API metadata](https://huggingface.co/api/models?search=ocr)
- Official GLM-OCR GGUF from ggml-org (created 2026-02-17, 112 likes); unsloth/GLM-OCR mirror and mlx-community/GLM-OCR-4bit also exist. — [HF API](https://huggingface.co/api/models?search=ocr)
- llama.cpp `docs/multimodal.md` explicitly lists five supported OCR models with prompt-structure caveats and PR links: PaddleOCR-VL (#18825), GLM-OCR (#19677), DeepSeek-OCR (#17400), dots.ocr (#17575), HunyuanOCR (#21395). — [llama.cpp multimodal.md](https://github.com/ggml-org/llama.cpp/blob/master/docs/multimodal.md)
- Chandra-OCR-2: 85.8% olmOCR-bench (their own run; 85.9 in the olmOCR-bench dataset table), 77.8% on their 43-language bench (+12% over Chandra 1), 90+ languages; outputs markdown/HTML/JSON; vLLM throughput 1.44 pages/s on one H100 (~2 pages/s real-world est.); recommended serving is `chandra_vllm` or HF transformers; weights = modified OpenRAIL-M (free for research, personal use, startups under $2M funding/revenue; cannot be used competitively with Datalab's API). — [datalab-to/chandra-ocr-2 card](https://huggingface.co/datalab-to/chandra-ocr-2)
- Surya-OCR-2: single 0.65B Qwen3.5-style VLM does layout + OCR + table rec (detection is a separate small torch model); 83.3% olmOCR-bench ("best under 3B params"), 87.2% on internal 91-language bench; layout decode is JSON-schema-constrained (`SURYA_GUIDED_LAYOUT`); officially supported backends are vLLM (GPU) **or llama.cpp (CPU / Apple Silicon)**, auto-spawned by the `surya-ocr` package; published Apple Silicon llama.cpp/Metal throughput: 0.108 pages/s ≈ 254 tok/s at ~30 W with `--parallel 8` (~2,360 output tokens/page); weights under modified AI Pubs OpenRAIL-M (free research/personal/startups <$5M). — [datalab-to/surya-ocr-2-gguf card](https://huggingface.co/datalab-to/surya-ocr-2-gguf)
- PaddleOCR-VL lineage: v1 Oct 2025 (arXiv 2510.14528, ERNIE-4.5-0.3B base, Apache-2.0) → v1.5 Jan 2026 (arXiv 2601.21957) → v1.6 May 2026 (arXiv 2606.03264; adds seal/spotting tasks); official PaddlePaddle GGUF repos exist for 1.5 and 1.6; mradermacher + Mungert community GGUFs; mlx-community/PaddleOCR-VL-1.6-4bit (Aug 2026). — [HF API paddleocr-vl search](https://huggingface.co/api/models?search=paddleocr-vl)
- MinerU2.5-Pro line (2604 Apr / 2605 May 2026, arXiv 2604.04771) is Apache-2.0 with `qwen2_vl` arch and transformers library metadata, unlike original MinerU2.5-2509 (AGPL-3.0); community GGUFs exist from mradermacher/jinzhenj/Mungert; opendatalab also shipped MinerU-HTML-v1.1-hunyuan0.5B-compact, MinerU-Diffusion-V1 (2.5B diffusion), and MinerU2.5-Flash-0.8B (qwen3.5 + linear-attention, ~Oct 2026). — [HF API mineru search](https://huggingface.co/api/models?search=mineru)
- DeepSeek-OCR (v1, Oct 2025): still the most-downloaded dedicated parser (2.04M downloads, 3,444 likes, MIT, `deepseek_vl_v2` arch with custom_code). — [HF API](https://huggingface.co/api/models?search=ocr)
- DeepSeek-OCR-2 ("Visual Causal Flow", arXiv 2601.20552): Apache-2.0; card pins transformers==4.46.3 + flash-attn==2.7.3 and CUDA (tested python 3.12.9 + CUDA11.8); dynamic resolution (0-6)×768×768 + 1×1024×1024; prompts `<image>\n<|grounding|>Convert the document to markdown.` or `Free OCR`. — [deepseek-ai/DeepSeek-OCR-2 card](https://huggingface.co/deepseek-ai/DeepSeek-OCR-2)
- Unlimited-OCR (Baidu, arXiv 2606.23050, MIT): positions itself as "push[ing] DeepSeek-OCR one step further"; unique one-shot long-horizon multi-page PDF parsing (pages→images at 300 DPI, multi-image prompts, 32K output budget); requires a custom no-repeat-ngram logit processor (`DeepseekOCRNoRepeatNGramLogitProcessor`) in SGLang or a custom vLLM docker image; acknowledges DeepSeek-OCR/OCR-2/PaddleOCR. Highest like-count (4,613) of any model in the OCR search. — [baidu/Unlimited-OCR card](https://huggingface.co/baidu/Unlimited-OCR)
- dots.ocr v1 (Jul 2025, MIT, 889K downloads, 1,341 likes) remains available under dots-studio; successor dots.mocr (arXiv 2603.13032, MIT, custom_code, 258K downloads) plus a dots.mocr-svg variant were released 2026-03-19; dots.mocr scored 83.9 on olmOCR-bench at 3.0B params. — [HF API dots-studio](https://huggingface.co/api/models?author=dots-studio), [Surya card benchmark table](https://huggingface.co/datalab-to/surya-ocr-2-gguf)

**2025-generation models still current:**

- olmOCR: latest Ai2 release is still **olmOCR-2-7B-1025** (Oct 6 2025, Qwen2.5-VL-7B finetune, Apache-2.0; FP8 variant for vLLM). No olmOCR-3 found in an HF search sorted by creation date (checked 2026-10-13). GGUFs: lmstudio-community, bartowski, mradermacher; MLX: mlx-community 4-bit/8-bit/bf16. Runs on llama.cpp via supported `qwen2_5_vl` arch. olmOCR-bench 82.4 (per Datalab's reproduction of olmocr-repo numbers). — [HF API allenai/olmocr by createdAt](https://huggingface.co/api/models?author=allenai&search=olmocr&sort=createdAt), [HF API olmocr by downloads](https://huggingface.co/api/models?search=olmocr)
- Nanonets-OCR2-3B (Oct 2025, Qwen2.5-VL-3B finetune, 288K downloads): still the newest Nanonets release found; no OCR2 GGUF repo surfaced in my searches (only the older Nanonets-OCR-s has unsloth GGUF). Base `qwen2_5_vl` arch ⇒ should run on llama.cpp, unverified as a packaged GGUF. — [HF API](https://huggingface.co/api/models?search=ocr)
- GOT-OCR2.0 (stepfun-ai, Sep 2024, 0.6B): obsolete for quality — 48.3 on olmOCR-bench; official repo is custom-runtime, but a transformers-native port (`got_ocr2` arch, stepfun-ai/GOT-OCR-2.0-hf) exists. — [Surya card table](https://huggingface.co/datalab-to/surya-ocr-2-gguf), [HF API](https://huggingface.co/api/models?search=ocr)
- Granite-Docling-258M (IBM, 258M, `idefics3` arch, Apache-2.0, 290K downloads, 1,279 likes): still the current version; no GGUF found in searches; the docling-project org now also ships separate RT-DETR layout models (docling-layout-heron, 1.77M downloads) and TableFormerV2 — i.e., IBM's stack is pipeline-style, not a single GGUF-able VLM. — [HF API docling search](https://huggingface.co/api/models?search=docling)
- HunyuanOCR (Tencent, 1B, Nov 2025): llama.cpp support exists (PR #21395 per multimodal.md, with a prompt-structure caveat), but the model did not appear in the top-60 OCR search by downloads, suggesting modest adoption; details not independently verified this session. — [llama.cpp multimodal.md](https://github.com/ggml-org/llama.cpp/blob/master/docs/multimodal.md)
- MonkeyOCR: **not found** in any of my HF searches (top-60 OCR by downloads, no dedicated search performed) — no longer prominent; status unverified. — [HF API](https://huggingface.co/api/models?search=ocr)
- Mistral OCR: appears only as an API baseline in benchmark tables (72.0 on olmOCR-bench); no open-weights release found. — [chandra-ocr-2 card](https://huggingface.co/datalab-to/chandra-ocr-2)
- Marker: still exists as Datalab's conversion pipeline; Marker v1.10.0 scored 76.5 on olmOCR-bench (below the new VLMs, incl. Surya-OCR-2 at 83.3) and now sits on top of the Surya VLM. — [chandra-ocr-2 card](https://huggingface.co/datalab-to/chandra-ocr-2)

**General VLMs used for parsing (Qwen3-VL):**

- Qwen3-VL-2B/4B/8B-Instruct (Oct 2025, Apache-2.0) are heavily used (8B: 8.0M downloads) with **official GGUFs from Qwen** (Qwen/Qwen3-VL-8B-Instruct-GGUF, Qwen3-VL-4B-Instruct-GGUF, created 2025-10-31) plus unsloth GGUFs — these ship with mmproj for llama.cpp. — [HF API qwen3-vl search](https://huggingface.co/api/models?search=qwen3-vl)
- But as parsers they trail badly: Qwen3-VL-8B scores 64.6 on olmOCR-bench vs 83–86 for dedicated small models (tables fail: 45.6). — [chandra-ocr-2 card benchmark](https://huggingface.co/datalab-to/chandra-ocr-2)
- Notable Qwen3-VL-based parsing finetunes: typhoon-ai/typhoon-ocr1.5-2b (269K downloads, Apache-2.0, SCG/SiamAi, Thai+EN) and FireRedTeam/FireRed-OCR (2B, Feb 2026, Apache-2.0). — [HF API](https://huggingface.co/api/models?search=ocr)

### Inferences
- llama.cpp vision support broadly kept pace through 2026: every major dedicated parser family except DeepSeek-OCR-2/dots.mocr/MinerU-Flash has either an official ggml-org/datalab/PaddlePaddle GGUF or a merged multimodal PR.
- The 2026 crop moved to Qwen3/Qwen3.5-style architectures, which is what unlocked official GGUF conversion for Chandra/Surya and MinerU-Flash.
- "Anchored" appears in benchmark tables for olmOCR (8.3B) and GPT-4o/Gemini ("anchored" = prompt-anchored evaluation methodology), suggesting olmOCR's API serving evolved without a new open-weights drop; identity of the "olmOCR (anchored)" entry is unverified.
- The AGPL → Apache shift in MinerU2.5-Pro and the OpenRAIL-M weight licenses on Datalab models show vendors differentiating on license as much as on quality; license now matters when choosing a default parser.

### Gaps
- r/LocalLLaMA could not be fetched (403); no direct community-thread citations. Consensus inferred from HF downloads/likes + benchmark tables.
- Parameter counts not stated on-card for DeepSeek-OCR-2 and Unlimited-OCR (both DeepSeek-OCR-lineage MoE; DeepSeek-OCR v1 was ~3B total with ~570M active per its paper — from prior knowledge, not re-verified).
- dots.mocr param count comes from the Surya card's olmOCR-bench table (3.0B), not the model card (not fetched).
- MonkeyOCR, HunyuanOCR full specs, and any olmOCR post-Oct-2025 weights release: unverified.
- MLX ports: none found for Surya-2, Chandra-2, dots.mocr, MinerU2.5-Pro, DeepSeek-OCR-2, Unlimited-OCR (searched HF; absence of evidence, not proof of absence).

---

## Key Question 2: Which are actually SMALL and practical to serve alongside other models on one Apple Silicon machine?

### Takeaway
For a 128GB M5 Max running llama-server/MLX with other models co-resident, the practical set is GLM-OCR (0.9B), PaddleOCR-VL-1.6 (~0.9B), Surya-OCR-2 (0.65B), Granite-Docling (258M, transformers/MLX-VLM only), and optionally Chandra-OCR-2 (5.3B) when quality matters — all fit trivially in RAM at Q4/Q8 (sub-1B models ≈ 0.5–1GB; Chandra-2 ≈ 3–4GB at Q4). Published Apple Silicon numbers exist only for Surya-OCR-2 (0.108 pages/s ≈ 254 tok/s via llama.cpp Metal at ~30 W); expect roughly similar page throughput for the other sub-1B OCR VLMs since page parsing is output-token-bound (~2,400 tokens/page), i.e., several seconds per dense page — throughput comes from batching concurrency, not raw speed.

### Cited Findings
- Surya-OCR-2 on Apple Silicon via llama.cpp/Metal: 0.108 pages/s, 254 tokens/s, p50 59s, ~30 W, avg 2,360 output tokens/page, measured with `--parallel 8` on an (unspecified) Apple Silicon machine. On RTX 5090/vLLM the same model does 5.35 pages/s. — [Surya card throughput tables](https://huggingface.co/datalab-to/surya-ocr-2-gguf)
- Surya-OCR-2 is explicitly positioned as a llama.cpp-on-Apple-Silicon model: "Surya 2 runs layout, OCR, and table recognition through a single VLM served by vllm (GPU) or llama.cpp (CPU / Apple Silicon)"; backend auto-selects llamacpp on non-NVIDIA; you can point it at your own running OpenAI-compatible server via `SURYA_INFERENCE_URL`. — [Surya card](https://huggingface.co/datalab-to/surya-ocr-2-gguf)
- Chandra-OCR-2 (5.3B): 1.44 pages/s on an H100 at 96 concurrency, est. ~2 pages/s real-world; the model card's own benchmark shows it beating Datalab's hosted API tier only slightly (85.8 vs 86.7). — [chandra-ocr-2 card](https://huggingface.co/datalab-to/chandra-ocr-2)
- GLM-OCR vendor speed claims: 1.86 pages/s (PDF input) and 0.67 images/s on unnamed single-replica hardware; 0.9B params explicitly marketed for "high-concurrency services and edge deployments". — [GLM-OCR card](https://huggingface.co/zai-org/GLM-OCR)
- Memory-fit arithmetic: official GGUF repos for PaddleOCR-VL-1.6 and GLM-OCR are sub-1B models; at Q4_K_M a ~0.9B VLM is roughly 0.6–0.8 GB of weights plus mmproj and KV cache — negligible next to the 128GB unified budget (inference from param counts, not a measured figure).
- Output verbosity is the real throughput driver: Surya reports ~2,400 output tokens per page; llama.cpp docs warn some OCR models "require large context window, for example: -c 8192". — [Surya card](https://huggingface.co/datalab-to/surya-ocr-2-gguf), [llama.cpp multimodal.md](https://github.com/ggml-org/llama.cpp/blob/master/docs/multimodal.md)
- llama.cpp caveat for all of these: "OCR models are trained with specific prompt and input structure" — you must use each model's documented prompt (links to per-model PRs) or accuracy collapses. — [llama.cpp multimodal.md](https://github.com/ggml-org/llama.cpp/blob/master/docs/multimodal.md)
- Custom-runtime models to avoid for this stack: DeepSeek-OCR-2 pins `transformers==4.46.3` + `flash-attn==2.7.3` (CUDA-oriented); Unlimited-OCR needs pinned torch 2.10/transformers 4.57.1 in transformers mode and a custom logit processor even on vLLM/SGLang; original DeepSeek-OCR v1 and dots.ocr v1 have merged llama.cpp PRs (#17400, #17575) and are the usable members of those lineages. — [DeepSeek-OCR-2 card](https://huggingface.co/deepseek-ai/DeepSeek-OCR-2), [Unlimited-OCR card](https://huggingface.co/baidu/Unlimited-OCR), [llama.cpp multimodal.md](https://github.com/ggml-org/llama.cpp/blob/master/docs/multimodal.md)
- llama-swap-style co-serving is realistic: GGUF OCR models are drop-in `llama-server` models with `--mmproj`; MLX users have 4-bit builds for GLM-OCR and PaddleOCR-VL-1.6 via mlx-community. — [ggml-org/GLM-OCR-GGUF](https://huggingface.co/ggml-org/GLM-OCR-GGUF), [mlx-community/PaddleOCR-VL-1.6-4bit](https://huggingface.co/mlx-community/PaddleOCR-VL-1.6-4bit), [mlx-community/GLM-OCR-4bit](https://huggingface.co/mlx-community/GLM-OCR-4bit)

### Inferences
- On M5 Max, expect the sub-1B OCR VLMs to land in the same rough band as Surya-2's published 0.1–0.3 pages/s single-stream Metal figure, scaling up with `--parallel`/batching since these models are small enough that several concurrent decodes fit easily; nobody publishes Apple Silicon numbers for GLM-OCR/PaddleOCR-VL yet, so treat any per-model tok/s as unmeasured until you benchmark.
- A pragmatic single-machine layout: one dedicated 0.65–0.9B parser (GLM-OCR or PaddleOCR-VL-1.6) always resident via llama-swap, Chandra-OCR-2 5.3B loaded on demand for hard documents, general Qwen3-VL-4B/8B only as a fallback for mixed vision+reasoning tasks.

### Gaps
- No published Apple Silicon tok/s found for GLM-OCR, PaddleOCR-VL-1.6, Chandra-OCR-2, olmOCR-2, DeepSeek-OCR (only Datalab publishes Metal numbers).
- Chandra-OCR-2 GGUF quality (does the community quant match vLLM bf16 accuracy?) unverified.
- Whether Datalab's llama.cpp auto-spawn path works with a user-managed llama-server (rather than its own spawned instance) is documented only via `SURYA_INFERENCE_URL`; no third-party confirmation found.

---

## Key Question 3: 2026 consolidation — is there a community-consensus "best small PDF parser"?

### Takeaway
Yes, consolidation happened around (a) the olmOCR-bench leaderboard as the common yardstick and (b) a clear tier of small winners: **GLM-OCR** (highest adoption + #1 OmniDocBench V1.5 + official ggml-org GGUF + MLX) is the de-facto default small parser for llama.cpp/MLX stacks; **Surya-OCR-2** (0.65B) is the consensus "accuracy-per-parameter" pick and the only one with first-class Apple Silicon llama.cpp integration; **Chandra-OCR-2** (5.3B) is the consensus open-weights quality king. DeepSeek-OCR remains the most-downloaded single model of the genre but its lineage (OCR-2, Unlimited-OCR) drifted toward custom GPU runtimes.

### Cited Findings
- The olmOCR-bench leaderboard (maintained in the allenai/olmOCR-bench dataset, reproduced in Datalab's cards) is now the standard comparison; top entries: Infinity-Parser2-Pro 35.1B = 87.6, Chandra-OCR-2 5.3B = 85.9, dots.mocr 3.0B = 83.9, Surya-OCR-2 0.65B = 83.3, LightOnOCR-2-1B = 83.2 (different methodology), Chandra-1 9.0B = 83.1, olmOCR-2 = 82.4, DeepSeek-OCR = 75.4, Mistral OCR API = 72.0, Qwen3-VL-8B = 64.6, GOT-OCR = 48.3. — [Surya card table](https://huggingface.co/datalab-to/surya-ocr-2-gguf), [chandra-ocr-2 card](https://huggingface.co/datalab-to/chandra-ocr-2)
- OmniDocBench V1.5 has a separate leaderboard where GLM-OCR claims #1 at 94.62. — [GLM-OCR card](https://huggingface.co/zai-org/GLM-OCR)
- Adoption signal (HF downloads, 2026-10-13): DeepSeek-OCR 2.04M, GLM-OCR 1.70M, Chandra-OCR-2 1.65M, Surya-OCR-2 1.43M + its GGUF 0.70M, Unlimited-OCR 1.18M, dots.ocr 0.89M, DeepSeek-OCR-2 0.67M, Nanonets-OCR2-3B 0.29M, Granite-Docling 0.29M, PaddleOCR-VL-1.6 0.05M (but GGUF 0.09M). Likes: Unlimited-OCR 4,613; DeepSeek-OCR 3,444; GLM-OCR 2,151; dots.ocr 1,341. — [HF API](https://huggingface.co/api/models?search=ocr)
- The llama.cpp project itself anoints a small set of OCR models with official support notes and ggml-org GGUFs (PaddleOCR-VL, GLM-OCR, DeepSeek-OCR, dots.ocr, HunyuanOCR) — strong signal for what the local-LLM tooling ecosystem treats as first-class. — [llama.cpp multimodal.md](https://github.com/ggml-org/llama.cpp/blob/master/docs/multimodal.md)
- General-purpose VLMs (Qwen3-VL) are no longer considered competitive for parsing despite being the most-downloaded VLMs overall (8M downloads for 8B) — a ~20-point olmOCR-bench gap to dedicated models. — [chandra-ocr-2 card](https://huggingface.co/datalab-to/chandra-ocr-2), [HF API qwen3-vl](https://huggingface.co/api/models?search=qwen3-vl)
- New entrant direction: LightOnOCR-2-1B (1B, 83.2 with a methodology caveat) and MinerU2.5-Flash-0.8B (linear-attention qwen3.5, Oct 2026) show the frontier still moving smaller/faster. — [Surya card table](https://huggingface.co/datalab-to/surya-ocr-2-gguf), [HF API mineru search](https://huggingface.co/api/models?search=mineru)

### Inferences
- For a llama.cpp/MLX home-lab, the consensus pick is effectively: GLM-OCR or PaddleOCR-VL-1.6 as default (MIT/Apache, official GGUF+MLX), Surya-OCR-2 if you accept its OpenRAIL weight terms and want the packaged Apple Silicon experience, Chandra-OCR-2 for maximum quality within its OpenRAIL terms.
- License consolidation is real: the top-quality open models (Chandra/Surya) carry revenue-capped OpenRAIL weight licenses, while the permissively-licensed (MIT/Apache) quality leaders are GLM-OCR, PaddleOCR-VL, dots.mocr, DeepSeek-OCR lineage, and Unlimited-OCR.

### Gaps
- No direct r/LocalLLaMA thread citations (fetch blocked); "community consensus" here is triangulated from HF adoption metrics, benchmark leaderboards, and first-class llama.cpp support — not from forum sentiment.
- LightOnOCR-2-1B and Infinity-Parser2-Pro specs were not independently verified (taken from the Surya card's reproduced table).
