# Benchmarks & Leaderboards for PDF/Document-Parsing Models (state as of October 2026)

All sources fetched 2026-10-13 unless noted. "Self-reported" means the model's authors produced the numbers; otherwise a third party ran the eval.

## What are the current benchmarks, what do they measure, and what are the criticisms?

### Takeaway
Two end-to-end page-parsing benchmarks dominate model selection in late 2026: **OmniDocBench** (opendatalab, CVPR 2025; latest v1.7, leaderboard on v1.6_full) for comprehensive per-component scoring (text edit distance, table TEDS, formula CDM, reading order), and **olmOCR-Bench** (Ai2) for pass/fail "unit-test" style checks on real-world PDF→text quality. OCRBench/OCRBench v2 and legacy VQA sets (DocVQA, ChartQA, TextVQA) measure VLM text/QA ability, not page→markdown parsing, and are no longer the deciding factor for parser selection.

### Cited Findings

**OmniDocBench (opendatalab, CVPR 2025)**
- 1,651 PDF pages, 10 document types, 5 layout types, 5 language types; annotations for 28 block-level + 4 span-level element categories, including text, LaTeX for formulas, LaTeX+HTML for tables, and reading order. — [OmniDocBench GitHub](https://github.com/opendatalab/OmniDocBench)
- End-to-end metric: **Overall = ((1 − text edit distance)×100 + table TEDS + formula CDM) / 3**, plus reading-order edit distance and layout detection (COCO mAP). TEDS is used for table structure; **CDM** (Character Detection Match, from UniMERNet) is the formula metric — this is the community's formula eval, not "KernelBench" (KernelBench is an unrelated NVIDIA GPU-kernel benchmark). — [OmniDocBench GitHub](https://github.com/opendatalab/OmniDocBench)
- Version history: v1.0 (Dec 2024) → v1.5 (Sep 2025: +374 pages, balanced CN/EN, 200 DPI for newspapers/notes, CDM integrated, Overall redefined as the 3-way average, CN/EN grouping removed) → v1.6 (Apr 2026: **MGAM matching** — "Multi-Granularity Adaptive Matching" that searches optimal segmentation granularity on the prediction side only; +296 hard pages: nested tables, dense formulas, unconventional layouts; CDM ported from Node.js/KaTeX to Python) → v1.7 (Apr 30, 2026). As of Oct 2026 the main leaderboard is **v1.6_full**; there is **no OmniDocBench 2.0** — the "CV" association is its CVPR 2025 paper. — [OmniDocBench GitHub updates](https://github.com/opendatalab/OmniDocBench)
- Latest leaderboard update 2026/09/11 added TeleOCR, OvisOCR2, Unlimited-OCR. An EvalScope integration (running OmniDocBench against OpenAI-compatible endpoints) was added 2026/07/27, making it easy to eval locally served models. — [OmniDocBench GitHub updates](https://github.com/opendatalab/OmniDocBench)
- Criticisms/limits: heavily CN/EN bilingual (5 language types, en/simplified_chinese/en_ch_mixed page attributes); many entries are contributed as inference scripts by model authors (semi-self-reported); scores are sensitive to matching algorithm version (the v1.5→v1.6 MGAM change re-baselined scores). Evaluation requires a heavy runtime (TeX Live 2025, ImageMagick 7, Ghostscript) — the repo ships a Docker image for reproducibility. — [OmniDocBench GitHub](https://github.com/opendatalab/OmniDocBench)

**olmOCR-Bench (Allen Institute for AI)**
- ~7,000 test cases over ~1,400 PDF pages across 8 categories: ArXiv math, Old scans math, Tables, Old scans, Headers & footers, Multi column, Long tiny text, Base. Operates on single-page PDFs; output is plain text/markdown. — [olmOCR GitHub](https://github.com/allenai/olmocr)
- Design: **machine-checkable pass/fail "facts" (unit tests)** — text presence/absence, natural reading order, table cell relationships (Markdown or HTML tables; rowspan/ colspan checks require HTML, so markdown-only output can't max the Tables category), and math verified by rendering with KaTeX and checking relative symbol order. Deliberately **avoids edit distance**: "soft metrics … may assign lower scores for parses that differ from the reference but may in fact still be correct." Unicode/hyphen/quote normalization applied. — [olmOCR-Bench README](https://github.com/allenai/olmocr/blob/main/olmocr/bench/README.md)
- Provenance is explicit: in its results table, entries marked `*` are "reported by model authors" (self-reported); unmarked rows are reproduced in-house by Ai2. — [olmOCR-Bench README](https://github.com/allenai/olmocr/blob/main/olmocr/bench/README.md)
- Criticisms/limits: English-only by construction (arXiv, Internet Archive, Library of Congress, internal English web crawl); not position-sensitive (except headers/footers), so it does not score layout fidelity or full structural reconstruction; headers/footers tests assume the olmOCR convention that they *should* be dropped, which penalizes parsers that preserve them; and the star system means the leaderboard mixes self-reported and reproduced numbers. — [olmOCR-Bench README](https://github.com/allenai/olmocr/blob/main/olmocr/bench/README.md)
- Datalab describes it as "the widely accepted olmocr benchmark." — [Chandra GitHub](https://github.com/datalab-to/chandra)

**OCRBench / OCRBench v2 / MDPBench (HustVL / Yuliang Liu et al.)**
- OCRBench (v1): 1,000 QA pairs across Text Recognition, Scene-Text VQA, Document VQA, KIE, Handwritten Math Expression — a general multimodal OCR capability test, published in Science China Information Sciences 2024. — [MultimodalOCR GitHub](https://github.com/Yuliang-Liu/MultimodalOCR)
- OCRBench v2 (NeurIPS 2025 D&B): 10,000 human-verified QA pairs, 31 scenarios, bilingual (EN/ZH), focused on visual text localization + reasoning, with a high proportion of hard samples. Leaderboard updated quarterly; last update **2026.03** per the repo news. — [MultimodalOCR GitHub](https://github.com/Yuliang-Liu/MultimodalOCR)
- **MDPBench** (NeurIPS 2026 D&B, released Apr 2026): first multilingual real-world document-parsing benchmark — 3,400 document images, 17 languages (EN, ZH, AR, DE, ES, FR, HI, ID, IT, JA, KO, PT, RU, TH, VI, zh-TW), digital + photographed documents, public **and private** splits to prevent leakage. Key finding: on photographed documents open-source models drop ~17.8% on average and ~14.0% on non-Latin scripts, while closed models (Gemini 3 Pro cited) are far more robust. Leaderboard is a HF Space. — [MultimodalOCR GitHub](https://github.com/Yuliang-Liu/MultimodalOCR)
- Note: OCRBench v1/v2 are **VLM text-reasoning benchmarks** (QA accuracy), not end-to-end page→markdown parsers; specialized small parsers rarely appear on them.

**Legacy VQA (DocVQA / SP-DocVQA / ChartQA / TextVQA)**
- Still used in general VLM model cards as document-QA signal, but none of the 2026 parsing leaderboards use them as the headline metric; they measure field-level QA accuracy, not full-page reconstruction, reading order, or table/formula fidelity. No 2026 source examined treats them as decisive for parser selection. (Absence from OmniDocBench/olmOCR-Bench/MDPBench methodology is itself the evidence.)

**2026 entrants**
- **ParseBench** (parsebench.ai): "the first benchmark that evaluates what AI agents actually need from document parsing" — 2,000 human-verified pages, 169K deterministic test rules, 5 capability dimensions. — [ParseBench](https://www.parsebench.ai/)
- **MPDocBench-Parse** (arXiv 2605.22100, May 2026): multi-page document-level end-to-end eval; 433 manually annotated documents, 3,246 pages, 15 document types, EN+ZH. — [arXiv](https://arxiv.org/abs/2605.22100)
- **Datalab multilingual OCR benchmark** (43-language and 90-language tables shipped in the Chandra repo): tests tables, math, ordering, layout, text accuracy; motivated by "there isn't a good public multilingual OCR benchmark, so we made our own." — [Chandra GitHub](https://github.com/datalab-to/chandra)
- **Nanonets benchmark portal** aggregates OmniDocBench, olmOCR-Bench and IDP-style extraction benchmarks. — [benchmarking.nanonets.com](https://benchmarking.nanonets.com/benchmarks)
- Community: **Local-Doc-Parsing-Bench** (MkengineTA GitHub) benchmarks *locally served* doc-parsing setups. — [GitHub](https://github.com/MkengineTA/Local-Doc-Parsing-Bench)
- "Mimectron" does not exist; the closest match is **NVIDIA Nemotron Parse 2.0** (model card updated 2026-09-11), a document-image → structured text/layout/reading-order model — a *model*, not a benchmark. — [NVIDIA build.nvidia.com](https://build.nvidia.com/nvidia/nemotron-parse-2.0/modelcard)

### Inferences
- OmniDocBench's v1.6 change set (hard pages, MGAM matching) shows the benchmark maintainers actively responding to prior criticisms (formula-as-unicode matching bias, matching artifacts) — a good sign for its continued authority, but it means scores from different versions (v1.0/v1.5/v1.6) are not comparable.
- olmOCR-Bench's pass/fail design maps most directly to "will this parser produce usable markdown/text for LLM ingestion," which is why vendors (Datalab, docsumo) quote it even when it embarrasses their own models (e.g., Nanonets-OCR2's 32.1 on headers/footers, Qwen3-VL-8B's 64.6 overall — both from Datalab's own runs).

### Gaps
- Exact OCRBench v2 standings for small models were not retrieved (leaderboard at [99franklin.github.io/ocrbench_v2](https://99franklin.github.io/ocrbench_v2/), JS/GH-pages content not fetched; last quarterly update 2026.03).
- Granite-Docling's current (Oct 2026) standing was not found on the leaderboards fetched; it does not appear in the OmniDocBench v1.6_full table.
- No r/LocalLLaMA thread content was directly quotable from search results; community sentiment below is proxied through 2026 vendor/aggregator write-ups (docsumo, Roboflow, towardsdeeplearning) and clearly attributed.

## Current standings (Oct 2026): small open models vs frontier VLMs

### Takeaway
Small specialized parsing VLMs (≤4B) now **beat frontier general VLMs** on OmniDocBench: TeleOCR (1.2B) 96.91, OvisOCR2 (0.8B) 96.47, PaddleOCR-VL-1.6 (0.9B) 96.34 vs Gemini 3 Pro 92.91, Qwen3-VL-235B 89.78, GPT-5.2 86.59. On olmOCR-Bench the top small open models are Chandra 2 (4B) at 85.8 (Datalab-run) / 85.9 (self-reported), dots.ocr 1.5 at 83.9 (self-reported), and olmOCR-2-7B at 82.4 (Ai2-run) — with olmOCR-2 still the best in the headers/footers category. There is **no evidence of an olmOCR 3** as of Oct 2026; olmOCR-2-7B-1025 (v0.4.0, Oct 2025) is the latest.

### Cited Findings

**OmniDocBench v1.6_full leaderboard (repo table, updated through 2026/09/11; Overall ↑ / TextEdit ↓ / Formula CDM ↑ / Table TEDS ↑):**
- TeleOCR (1.2B, specialized): **96.91** / 0.0267 / 96.59 / 96.82 (also best Table TEDS-S 98.18) — top of the full table. — [OmniDocBench GitHub](https://github.com/opendatalab/OmniDocBench)
- OvisOCR2 (0.8B): 96.47 / **0.0265 best text** / 97.49 / 94.58; best reading order (0.1120). — same source
- PaddleOCR-VL-1.6 (0.9B): 96.34 / 0.0326 / **97.53 best formula CDM** / 94.76. PaddleOCR-VL-1.5: 94.93; original PaddleOCR-VL: 94.18. — same source
- MinerU2.5-Pro (1.2B): 95.75; MinerU2.5: 93.04. GLM-OCR (0.9B): 95.22. — same source
- Other small models: Unlimited-OCR (3B) 94.00; Qianfan-OCR (4B) 93.90; Youtu-Parsing (2.5B) 93.74; Logics-Parsing-v2 (4B) 93.33; ABot-OCR (2B) 93.30; FireRed-OCR (2B) 93.26; dots.ocr (3B) 90.77; OpenDoc-0.1B 90.67; DeepSeek-OCR 2 (3B) 90.25; HunyuanOCR (1B) 89.95; Dolphin-v2 (3B) 89.50; OCRVerse (4B) 88.60; MonkeyOCR-pro-3B 88.57; Dolphin-1.5 (0.3B) 86.52; olmOCR (7B) 85.74; Nanonets-OCR-s (3B) 83.61; POINTS-Reader (3B) 83.37. — same source
- Frontier reference: Gemini 3 Pro 92.91, Gemini 3 Flash 92.62, Qwen3-VL-235B 89.78, GPT-5.2 86.59, Kimi K2.5 (1T) 84.53, InternVL3.5-241B 83.76; pipeline tools MinerU-Pipeline 86.47 and Marker 78.44 trail. Every one of these is below the top ~15 small specialized models. — same source
- Caveat: these are computed by opendatalab from model authors' inference scripts, and the table's ranking is dominated by Chinese-lab models on a CN/EN benchmark. Third-party reproductions exist, e.g. an independent v1.6 re-run on an RTX 3090 Ti with VRAM/throughput notes (Instavar research page, 2026). — [Instavar](https://instavar.com/research/ocr/open-document-ocr-models)

**olmOCR-Bench (Overall ±, 8 categories):**
- From the olmOCR repo table: Chandra OCR 0.1.0* 83.1±0.9; Infinity-Parser 7B* 82.5; **olmOCR v0.4.0 (7B, in-house) 82.4±1.1**; PaddleOCR-VL* 80.0±1.0; Marker 1.10.1 76.1±1.1; DeepSeek-OCR 75.7±1.0; MinerU 2.5.4* 75.2±1.1; Mistral OCR API 72.0±1.1; Nanonets-OCR2-3B 69.5±1.1 (headers/footers 32.1 is its catastrophic category). `*` = self-reported. — [olmOCR GitHub](https://github.com/allenai/olmocr)
- From Datalab's own runs (Chandra README): **Datalab API 86.7±0.8**; **Chandra 2 (4B) 85.8±0.8** (Tables 92.1 — best in that table; Long tiny text 93.7); dots.ocr 1.5 83.9 (sourced from dots.ocr repo); Chandra 1 83.1; olmOCR 2 82.4 (best Headers & footers 96.1 tied with DeepSeek-OCR's 96.1); dots.ocr (v1) 79.1±1.0; Marker 76.5; DeepSeek-OCR 75.4; GPT-4o (anchored) 69.9; **Qwen3-VL-8B 64.6±1.1**; Gemini Flash 2 (anchored) 63.8. — [Chandra GitHub](https://github.com/datalab-to/chandra)
- Category takeaways from that table: best Old-scans-math = Datalab API 90.2 / Chandra 2 89.1; best multi-column = dots.ocr 1.5 (85.3); best headers/footers = olmOCR 2 (96.1). — same source
- Multilingual (Datalab's own 43-language benchmark, avg): Datalab API 80.4% > Chandra 2 77.8% > Chandra 1 69.4% > Gemini 2.5 Flash 67.6% > GPT-5 Mini 60.5%; 90-language subset: Chandra 2 72.7% vs Gemini 2.5 Flash 60.8%. Self-benchmarked, but the only broad multilingual table published. — [Chandra GitHub](https://github.com/datalab-to/chandra)
- olmOCR 2 claims: v0.4.0 (Oct 21, 2025) "boosts olmOCR-bench score by ~4 points using synthetic data and RL(VR) training"; paper: "olmOCR 2: Unit Test Rewards for Document OCR" (arXiv 2510.19817). No olmOCR 3 appears in the repo news, releases, or third-party tables as of Oct 2026. — [olmOCR GitHub](https://github.com/allenai/olmocr)

**Per-model notes**
- Chandra 2: released March 2026, 4B params (down from Chandra 1's ~8B-class footprint), built on Qwen 3.5 per credits; weights are **modified OpenRAIL-M** — free for research/personal/startups under $2M funding/revenue, but "cannot be used competitively with our API" and commercial self-hosting requires a license. vLLM-based serving; ~1.44 pages/s on one H100 on the (hard) olmOCR-bench mix, ~2 pages/s real-world estimated. — [Chandra GitHub](https://github.com/datalab-to/chandra); "85.9% olmOCR-bench SOTA, 77.8% on internal 43-language benchmark" claimed in the v0.2.0 release notes. — [Chandra releases](https://github.com/datalab-to/chandra/releases)
- dots.ocr 1.5: 83.9 olmOCR-Bench self-reported (up from 79.1 for dots.ocr v1). — [Chandra GitHub benchmark table, sourced per-row](https://github.com/datalab-to/chandra)
- PaddleOCR-VL family (0.9B): 80.0 olmOCR-Bench (self-reported, starred in Ai2's table) and 94.18→96.34 across its three OmniDocBench versions. — [olmOCR GitHub](https://github.com/allenai/olmocr); [OmniDocBench GitHub](https://github.com/opendatalab/OmniDocBench)
- MinerU 4.0 (current MinerU release): the VLM backend runs on **llama.cpp (Vulkan) by default**, or vLLM/LMDeploy; small models run ONNX/Torch — directly relevant to local serving. MinerU2.5 tech report arXiv 2509.22186; MinerU2.5-Pro arXiv 2604.04771. — [MinerU GitHub](https://github.com/opendatalab/MinerU)
- MDPBench finding (cross-model, Oct 2026 relevant): open-source parsers collapse on photographed pages (−17.8%) and non-Latin scripts (−14.0%) relative to closed models like Gemini 3 Pro — clean-digital-benchmark scores overstate real-world robustness. — [MultimodalOCR GitHub](https://github.com/Yuliang-Liu/MultimodalOCR)
- Vendor summaries corroborate the small-model dominance narrative: Roboflow (Aug 2026): "PaddleOCR-VL, GLM-OCR, and MinerU beat 235B VLMs on OmniDocBench at 0.9B params"; docsumo (Sep 30, 2026) ranks 2026 models by OmniDocBench + olmOCR-Bench. — [Roboflow blog](https://roboflow.com/blog/best-open-source-ocr-models); [Docsumo blog](https://www.docsumo.com/blog/best-ocr-models)
- One aggregator (ofox.ai, Apr 2026) quotes different OmniDocBench numbers (GLM-OCR 94.62, PaddleOCR-VL 94.50, Gemini 3.1 Pro 90.33, GPT-5.4 ≈85.8) — consistent with an older (v1.5) eval or different filter than the repo's v1.6_full; treat aggregator numbers as version-sensitive. — [ofox.ai](https://ofox.ai/blog/best-ai-model-for-ocr-2026/)

### Inferences
- On paper, the OmniDocBench v1.6 top tier (TeleOCR 1.2B, OvisOCR2 0.8B, PaddleOCR-VL-1.6 0.9B, MinerU2.5-Pro 1.2B, GLM-OCR 0.9B) are all ≤1.2B — an order of magnitude smaller than what the user needs to fit, trivially servable on a 128GB M5 Max. On olmOCR-Bench, the English "real-world PDF" leader among *open weights* is Chandra 2 (4B) but with a restrictive OpenRAIL-M license; the safest-license high performers are PaddleOCR-VL-1.6 (0.9B) and MinerU2.5(-Pro) (1.2B).
- Benchmark disagreement is informative: olmOCR-2 scores only 85.74 on OmniDocBench v1.6 but leads headers/footers on its own bench; Nanonets-OCR2 looks average on OmniDocBench (83.61 for OCR-s) and poor on olmOCR-Bench (69.5); dots.ocr is mid on OmniDocBench v1.6 (90.77) but strong on olmOCR-Bench (83.9 for 1.5). Cross-checking both is necessary, not optional.

### Gaps
- dots.ocr 1.5's size/release date and its own repo's full category numbers were not independently verified (second-hand via the Chandra table).
- TeleOCR, OvisOCR2, GLM-OCR, MinerU2.5-Pro papers/model cards were not individually fetched; their OmniDocBench rows are opendatalab-computed but their GGUF/MLX availability for llama.cpp/MLX serving is unverified (MinerU's llama.cpp support is confirmed via its README).
- OCRBench v2 current top-10 was not retrieved (see previous gap section).
- Granite-Docling and Nemotron Parse 2.0 standings on these tables were not found; neither appears in the OmniDocBench v1.6_full or olmOCR-Bench tables fetched.

## Is there a live leaderboard, and is it updated?

### Takeaway
Yes — the live hubs are the **OmniDocBench GitHub leaderboard** (actively updated; last model additions 2026/09/11, versioned dataset on HF/OpenDataLab), the **olmOCR-Bench table** in the Ai2 repo (updated per model release; results distinguish self-reported vs reproduced), the **OCRBench v2 GitHub-pages leaderboard** (quarterly; last 2026.03), and the **MDPBench HF Space leaderboard** (2026). No single HF Space named "Document Parsing Leaderboard" could be confirmed; aggregators (CodeSOTA, Nanonets portal) mirror OmniDocBench as the canonical task metric.

### Cited Findings
- OmniDocBench: leaderboard lives in the repo README ("v1.6_full"); updates logged 2026/03/31 (large model batch), 2026/04/30 (v1.7 + Qianfan-OCR), 2026/07/27 (EvalScope integration), 2026/09/11 (TeleOCR, OvisOCR2, Unlimited-OCR). Dataset on HF: opendatalab/OmniDocBench; official site opendatalab.com/omnidocbench. — [OmniDocBench GitHub](https://github.com/opendatalab/OmniDocBench)
- olmOCR-Bench: results table maintained in [allenai/olmocr](https://github.com/allenai/olmocr) README and [olmocr/bench README](https://github.com/allenai/olmocr/blob/main/olmocr/bench/README.md); dataset at HF `allenai/olmOCR-bench`; last update coincided with olmOCR v0.4.0 (Oct 2025), with third parties (Datalab) publishing newer rows for their own models. — same sources
- OCRBench v2 leaderboard: [99franklin.github.io/ocrbench_v2](https://99franklin.github.io/ocrbench_v2/), "updated quarterly," latest update 2026.03 per repo news. — [MultimodalOCR GitHub](https://github.com/Yuliang-Liu/MultimodalOCR)
- MDPBench leaderboard: HF Space `Delores-Lin/MDPBench-leaderboard`. — [MultimodalOCR GitHub](https://github.com/Yuliang-Liu/MultimodalOCR)
- CodeSOTA lists Document Parsing with "149 benchmark results across 3 datasets. Canonical: OmniDocBench." — [CodeSOTA](https://www.codesota.com/tasks/document-parsing)
- DuckDuckGo searches for an HF Space literally named "document parsing leaderboard" returned no results (checked 2026-10-13) — the name in circulation may be informal. (Absence of evidence noted.)

### Inferences
- The OmniDocBench GitHub README *is* the de facto live document-parsing leaderboard in Oct 2026; everything else either mirrors it, complements it (olmOCR-Bench for English real-world checks), or special-purpose tests it (MDPBench multilingual).

### Gaps
- Whether opendatalab.com/omnidocbench renders its own live HTML leaderboard (JS app) was not verified.
- olmOCR-Bench's table update cadence in 2026 (beyond the Oct 2025 v0.4.0 entry) is unclear; the newest rows there come from third-party repos.

## Practical selection guidance: which benchmark best predicts real-world PDF→markdown quality?

### Takeaway
Community and vendor practice in 2026 treats **olmOCR-Bench as the best single predictor of real-world English PDF→markdown quality** (pass/fail unit tests on messy real PDFs; Datalab calls it "the widely accepted" benchmark and even runs it on rivals), with **OmniDocBench v1.6 as the complementary structural benchmark** for tables (TEDS), formulas (CDM), reading order, and CN/EN coverage. For a local-serving decision on M5 Max, triangulate both, weight the categories you actually have, and note MDPBench's warning that all of these clean-scan benchmarks overstate robustness on photos/non-Latin scripts.

### Cited Findings
- olmOCR-Bench's design rationale targets exactly the failure modes that ruin downstream markdown: dropped content, wrong reading order across columns/articles, table cell relationships, mangled math, missed tiny dense text — checked as binary facts "similar to a unit test," explicitly rejecting edit distance because a "correct" parse can differ from the reference. — [olmOCR-Bench README](https://github.com/allenai/olmocr/blob/main/olmocr/bench/README.md)
- Datalab benchmarked its own and rival models on olmOCR-Bench ("widely accepted") rather than only on its internal suite, and separately published a multilingual suite because no good public one existed — an implicit endorsement that olmOCR-Bench is the reference but is English-only. — [Chandra GitHub](https://github.com/datalab-to/chandra)
- omniDocBench contributes what olmOCR-Bench can't: TEDS/CDM component scores, reading-order edit distance, and per-attribute breakdowns (watermark, fuzzy scan, rotation, table borders/merges) — use it when your documents are table/formula-heavy or Chinese. — [OmniDocBench GitHub](https://github.com/opendatalab/OmniDocBench)
- 2026 third-party write-ups use exactly this pair: docsumo's "Best OCR Models (2026)" compares on OmniDocBench + olmOCR-Bench scores with size/license/hardware notes (Sep 30, 2026); Roboflow's Aug 2026 ranking leads with OmniDocBench at 0.9B-scale wins; Instavar re-ran OmniDocBench v1.6 locally on an RTX 3090 Ti adding VRAM/throughput context. — [Docsumo](https://www.docsumo.com/blog/best-ocr-models); [Roboflow](https://roboflow.com/blog/best-open-source-ocr-models); [Instavar](https://instavar.com/research/ocr/open-document-ocr-models)
- MDPBench shows the blind spot: open-source parsers lose ~14–18% on photographed/non-Latin pages versus their clean-scan scores; it publishes public+private splits specifically to counter contamination. — [MultimodalOCR GitHub](https://github.com/Yuliang-Liu/MultimodalOCR)
- Licensing is a selection factor independent of scores: Chandra 2's OpenRAIL-M restricts competitive/commercial self-hosting; olmOCR (OLMo/Apache), PaddleOCR-VL (Apache-2.0 per Roboflow's license comparison), MinerU pipeline, and dots.ocr are permissive per their repos. — [Chandra GitHub](https://github.com/datalab-to/chandra); [Roboflow](https://roboflow.com/blog/best-open-source-ocr-models)
- Serving-path datapoint: MinerU 4.0's VLM tier is designed to run under llama.cpp (Vulkan default) — evidence the top OmniDocBench-tier VLMs are consumable in the user's llama.cpp/mmproj or MLX workflow, though GGUF availability for each model must be checked per-model. — [MinerU GitHub](https://github.com/opendatalab/MinerU)

### Inferences
- For the user's task (page image → markdown with layout/tables/formulas/reading order on Apple Silicon): shortlist = **MinerU2.5(-Pro) 1.2B, PaddleOCR-VL-1.6 0.9B, GLM-OCR 0.9B, TeleOCR 1.2B, OvisOCR2 0.8B** (OmniDocBench tier + tiny footprints) and **Chandra 2 4B** if the OpenRAIL-M license is acceptable and English-dominant real-world PDFs are the workload; **dots.ocr 1.5 (3B)** as a middle ground on olmOCR-Bench. Avoid picking on legacy VQA or OCRBench alone.
- Because OmniDocBench v1.6's top ranks are filled by CN-lab models on a CN/EN benchmark, an English-only user should discount ~1–2 points of ordering and lean more on olmOCR-Bench category scores.
- Contamination risk is lowest where benchmarks publish held-out private splits (MDPBench) or are regenerated (OmniDocBench v1.6's new hard pages); oldest public sets (DocVQA, ChartQA, TextVQA) should be assumed contaminated for frontier models and are irrelevant to parser selection anyway.

### Gaps
- No directly quotable r/LocalLLaMA 2026 thread was retrieved endorsing a single "most trusted" benchmark; the olmOCR-Bench-as-proxy claim rests on primary-source design rationale plus Datalab/vendor adoption, not on quoted community threads.
- Chandra 2 GGUF/mmproj or MLX availability was not verified; Chandra's docs show HF/vLLM paths only.
- ParseBench and MPDocBench-Parse model standings were not retrieved (sites/papers not fetched), so their influence on selection in Oct 2026 can't be assessed beyond their existence.
