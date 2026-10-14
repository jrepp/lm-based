# Benchmark Evidence: Most Capable Open-Weight LLM for a 128GB Mac (October 2026)

Research date: 2026-10-10. Sources fetched live during this session: swebench.com, aider.chat/docs/leaderboards,
HF model cards (Qwen/Qwen3-Coder-Next, zai-org/GLM-5), Bing-indexed vendor pages (z.ai, bigmodel.cn, qwen.ai).
Numbers below are attributed to the specific page they came from; anything not directly sourced is in Gaps or is
explicitly labeled Inference.

## Key Question 1: Benchmark standings as of late 2026 (SWE-bench family, LiveCodeBench, Aider, Terminal-Bench, tau2, BFCL, GPQA, MMLU-Pro, ARC-AGI-2, HLE, AIME)

### Takeaway

On agentic/verified coding benchmarks, the late-2025/2026 open-weight leaders are GLM-5 (744B MoE, too big for
128GB) and Qwen3-Coder-Next (80B-A3B, fits easily). GLM-5's own card reports the strongest open-weights numbers
across SWE-bench Verified (77.8), SWE-bench Multilingual (73.3), and Terminal-Bench 2.0 (56.2/60.7 verified),
while Qwen3-Coder-Next posts 70.6 SWE-bench Verified, 44.3 SWE-bench Pro, and 36.2 Terminal-Bench 2.0 at 3B
active params.

### Cited Findings

- GLM-5 (Feb 2026, MIT license, arXiv 2602.15763) self-reported comparison table vs GLM-4.7, DeepSeek-V3.2,
  Kimi K2.5, Claude Opus 4.5, Gemini 3 Pro, GPT-5.2 (xhigh) — [zai-org/GLM-5 model card](https://huggingface.co/zai-org/GLM-5):
  - SWE-bench Verified: GLM-5 77.8 / GLM-4.7 73.8 / DeepSeek-V3.2 73.1 / Kimi K2.5 76.8 / Opus 4.5 80.9 /
    Gemini 3 Pro 76.2 / GPT-5.2 80.0 (OpenHands scaffold, 200K ctx, temp 0.7)
  - SWE-bench Multilingual: GLM-5 73.3 (best in table, above Opus 4.5's 77.5? no — Opus 77.5; GLM-5 best open,
    Gemini 3 Pro 65.0, GPT-5.2 72.0)
  - Terminal-Bench 2.0 (Terminus 2): GLM-5 56.2 (60.7 on zai's "verified" fix of ambiguous instructions) /
    GLM-4.7 41.0 / DeepSeek-V3.2 39.3 / Kimi K2.5 50.8 / Opus 4.5 59.3 / Gemini 3 Pro 54.2 / GPT-5.2 54.0
  - Terminal-Bench 2.0 (Claude Code harness): GLM-5 56.2/61.1, DeepSeek-V3.2 46.4, Opus 4.5 57.9
  - HLE (text-only): GLM-5 30.5 / GLM-4.7 24.8 / DeepSeek-V3.2 25.1 / K2.5 31.5 / Opus 4.5 28.4 /
    Gemini 3 Pro 37.2 / GPT-5.2 35.4; HLE w/ tools: GLM-5 50.4, K2.5 51.8
  - GPQA-Diamond: GLM-5 86.0 / K2.5 87.6 / DeepSeek-V3.2 82.4 / GLM-4.7 85.7 (frontier ref: Gemini 3 Pro 91.9)
  - AIME 2026 I: GLM-5 92.7 / DeepSeek-V3.2 92.7 / K2.5 92.5 / Opus 4.5 93.3; HMMT Nov 2025: GLM-5 96.9
  - Agentic/tool: τ²-Bench GLM-5 89.7 (Opus 4.5 91.6, Gemini 3 Pro 90.7, GPT-5.2 85.5, K2.5 80.2);
    MCP-Atlas 67.8; Tool-Decathlon 38.0; BrowseComp 62.0 (well above Opus 4.5 37.0); Vending-Bench-2 $4,432
    (independent run by Andon Labs)
  - HF-linked eval results for GLM-5: MMLU-Pro 86, GPQA-Diamond 86, MathArena AIME 2026 95.83,
    HMMT Feb 2026 86.36, SWE-bench Multilingual 73.3, Mercor Apex-Agents 17.2 —
    [zai-org/GLM-5 model card](https://huggingface.co/zai-org/GLM-5)
- Qwen3-Coder-Next (Apache-2.0, 80B total / 3B active, 256K native context, non-thinking-only) HF
  leaderboard-verified evals — [Qwen/Qwen3-Coder-Next model card](https://huggingface.co/Qwen/Qwen3-Coder-Next):
  - SWE-bench Pro: 44.3
  - SWE-bench Verified: 70.6
  - Terminal-Bench 2.0: 36.2
  - Vendor claim: "performance comparable to models with 10–20x more active parameters"; trained for
    long-horizon reasoning, complex tool use, and recovery from execution failures; works with Claude Code,
    Qwen Code, Cline, Kilo, Trae scaffolds — [same model card](https://huggingface.co/Qwen/Qwen3-Coder-Next)
- Aider polyglot leaderboard (fetched 2026-10-10) — [aider.chat](https://aider.chat/docs/leaderboards/):
  - Overall top: gpt-5 (high) 88.0%, gpt-5 (medium) 86.7%, o3-pro (high) 84.9%, gemini-2.5-pro-preview 83.1%
  - Best open-weights entries: DeepSeek-V3.2-Exp (Reasoner) 74.2% ($1.30/run, recorded 2025-10-03);
    DeepSeek-V3.2-Exp (Chat) also listed; Kimi K2 (July 2025) 59.1%; gpt-oss-120b (high) 41.8% ($0.74/run);
    Qwen3 235B A22B (diff, no think), DeepSeek R1 (0528), Qwen3 32B, Llama 4 Maverick, Qwen2.5-Coder-32B
    also present
  - The Aider board has NO entries for GLM-4.6/4.7/5, Qwen3-Coder/3-Coder-Next, or Kimi K2-Thinking/K2.5 —
    Aider's own runs lag the 2026 model cycle.
- swebench.com (fetched 2026-10-10) now offers a "Bash Only / mini-SWE-agent" uniform-harness Verified view
  (500 instances) alongside legacy per-submission numbers, plus SWE-bench Multimodal (480) and Multilingual
  (300) boards; site news shows May 2026 ProgramBench and Nov 2025 CodeClash releases —
  [swebench.com](https://www.swebench.com/). Leaderboard numbers are rendered client-side and could not be
  scraped in this session.
- GLM-5.x API-line successors exist: z.ai markets GLM-5.3 / GLM-5.3-Flash / GLM-5.2 / GLM-5-Turbo; bigmodel.cn
  docs describe GLM-5.2 as a 1M-context "long-task era" flagship and GLM-5.3 as sharing GLM-5.2's base model
  with gains coming from post-training (software engineering + agent focus) —
  [z.ai subscribe page](https://z.ai/subscribe), [bigmodel.cn GLM-5.2 docs](https://docs.bigmodel.cn/cn/guide/models/text),
  [bigmodel.cn GLM-5.3 docs](https://docs.bigmodel.cn/cn/guide/models/text) (via Bing).
- 2026-era benchmarks appearing in frontier tables: AIME 2026, HMMT Nov 2025 / Feb 2026, Terminal-Bench 2.0,
  Mercor Apex-Agents, CyberGym, Vending-Bench-2, MCP-Atlas, Tool-Decathlon —
  [GLM-5 model card](https://huggingface.co/zai-org/GLM-5).

### Inferences

- GLM-5's Terminal-Bench 2.0 numbers (56.2) exceed every frontier reference in its own table except Opus 4.5's
  59.3, and its τ²-Bench (89.7) is within ~2 points of Opus 4.5 — i.e., the open-weights frontier in early 2026
  is roughly at Claude-Opus-4.5 level on agentic tasks. Self-reported numbers with tailored prompts/judges, so
  treat cross-model comparisons as directional (the card's own footnotes document per-benchmark judge models
  and harness tweaks).
- SWE-bench Pro 44.3 for Qwen3-Coder-Next is remarkable if confirmed independently (SWE-bench Pro public-set
  scores for most frontier agents have historically been in the ~20s–30s); it is sourced from Qwen's tech
  report (arXiv 2603.00729) and marked as an HF-leaderboard-verified eval, but not yet independently
  re-run by the SWE-bench team to this researcher's knowledge.

### Gaps

- LiveCodeBench, BigCodeBench, BFCL v3, ARC-AGI-2, and Artificial Analysis open-vs-open standings for 2026
  models: not retrieved (leaderboards are JS-rendered; no static page captured). No sourced numbers this session.
- LMArena / community arena rankings for GLM-5 / K2.5 / DeepSeek successors: not retrieved.
- Whether GLM-5.2/GLM-5.3 weights are open: unverified. The open-weights artifact confirmed this session is
  GLM-5 (MIT); GLM-5.2/5.3 are documented as API models on bigmodel.cn.
- No contamination caveats were found stated in the fetched sources, beyond GLM-5's footnotes describing
  verified Terminal-Bench fixes for ambiguous instructions.

## Key Question 2: Head-to-head of named candidates (Qwen3-Coder family, Qwen3.5/3.6, GLM-4.6/5, DeepSeek-V3.x, Kimi K2/K2.5, MiniMax-M1/M2, gpt-oss-120b, Llama 4, Gemma 3/4, Mistral)

### Takeaway

Confirmed-by-primary-source standings in the fetched data: GLM-5 leads open agentic benchmarks; Kimi K2.5 is the
runner-up open model in GLM-5's comparison table (76.8 SWE-bench Verified, 50.8 TB2, 31.5 HLE); DeepSeek-V3.2
lags both on agentic coding (73.1 / 39.3) but ties GLM-5 on AIME 2026; Qwen3-Coder-Next dominates the
fits-in-128GB class (70.6 SWE-V at 80B-A3B). No sourced data was found this session for Qwen3.5/3.6,
MiniMax-M2, Gemma 4, or Mistral Large.

### Cited Findings

- GLM-5: 744B total / 40B active MoE, pretrained on 28.5T tokens (vs GLM-4.5's 355B/32B on 23T), integrates
  DeepSeek Sparse Attention (DSA); positioned for "complex systems engineering and long-horizon agentic tasks";
  claims "best-in-class performance among all open-source models in the world on reasoning, coding, and agentic
  tasks" — [zai-org/GLM-5 model card](https://huggingface.co/zai-org/GLM-5). Third-party Chinese-language page
  describes GLM-5 as 745B params, 44B active, 200K context ([glm-5.org](https://glm-5.org/zh), via Bing —
  minor discrepancy with the card's 744B/40B; trust the card).
- Kimi K2.5: exists as a 2026 open flagship (referenced and scored in GLM-5's table: 76.8 SWE-bench Verified,
  31.5 HLE, 87.6 GPQA-D, 92.5 AIME 2026-I, 50.8 TB2, 60.6 BrowseComp, 80.2 τ²) —
  [GLM-5 model card](https://huggingface.co/zai-org/GLM-5). Parameter count / MTP status not directly verified.
- DeepSeek-V3.2 (aider lists "-Exp (Reasoner)" and "-Exp (Chat)" variants): 74.2% Aider polyglot (Reasoner),
  best open score on Aider's board — [aider.chat](https://aider.chat/docs/leaderboards/); in GLM-5's table it
  scores 73.1 SWE-V / 39.3 TB2 / 85.3 τ² / 25.1 HLE / 92.7 AIME 2026-I — [GLM-5 card](https://huggingface.co/zai-org/GLM-5).
- gpt-oss-120b: 41.8% Aider polyglot at high reasoning ($0.74/run) — [aider.chat](https://aider.chat/docs/leaderboards/).
- Llama 4 Maverick: present on Aider's polyglot board (entry exists; below the leaders; exact % not extracted
  this session) — [aider.chat](https://aider.chat/docs/leaderboards/).
- Qwen3-Coder family: Qwen3-Coder-Next is the current coding-flagship artifact (80B-A3B, Apache-2.0,
  qwen3_next hybrid DeltaNet+Gated-Attention architecture, 512 experts/10 active, non-thinking only,
  594K downloads last month, 115 community GGUF quantizations on HF) —
  [Qwen/Qwen3-Coder-Next](https://huggingface.co/Qwen/Qwen3-Coder-Next).
- "Qwen3.8-Max" and "Qwen3.8-Flash" appear on qianwenai.com as multimodal API models with 1M-class context —
  [qianwenai.com](https://www.qianwenai.com/models) (via Bing; this domain is NOT the official qwen.ai and may
  be an SEO mirror — treat as unconfirmed). No evidence of open-weights Qwen3.5/3.6 releases was found.

### Inferences

- For a 128GB Mac, the relevant frontier is "what fits": Qwen3-Coder-Next (80B) fits at high quant with large
  context; gpt-oss-120b (MXFP4 ~60GB class) fits; GLM-5 (744B), DeepSeek-V3.2 (~685B class), Kimi K2.5 (1T
  class) do not fit at usable quants.
- Kimi K2.5 and DeepSeek-V3.2 are credible "capability ceiling" references from the same vendor-reported table,
  useful for judging how much a 128GB-runnable model gives up vs the open frontier (~4–7 points SWE-V, ~15–20
  points TB2 vs GLM-5).

### Gaps

- No primary data found this session for: Qwen3.5 / Qwen3.6 open releases; MiniMax-M1/M2 current standings;
  Gemma 3/4; Mistral Large; GLM-4.6/4.7 standalone cards (GLM-4.7 numbers exist only inside GLM-5's table);
  Kimi K2-Thinking benchmarks; official K2.5 model card.
- Exact Aider % for Llama 4 Maverick, Qwen3 235B, and DeepSeek-V3.2-Exp (Chat) were visible in the board but
  not extracted (only names + selected scores pulled from the saved page).

## Key Question 3: Models too big for 128GB — smaller/distilled variants and low-quant options

### Takeaway

The 2026 open flagships (GLM-5 744B, DeepSeek-V3.x ~685B, Kimi K2/K2.5 ~1T) cannot fit 128GB at any usable
quant (~2-bit of a 744B model is already ~190GB before KV cache). The practical "fits" tier is 80–120B MoE:
Qwen3-Coder-Next (80B-A3B) and gpt-oss-120b. No 2026-released sub-128GB flagship distilled from the big MoEs
(e.g., a "GLM-5-Air" or DeepSeek/Kimi distill) was confirmed this session.

### Cited Findings

- GLM-5 card documents local serving via vLLM 0.19+, SGLang 0.5.10+, KTransformers 0.5.3+, Transformers,
  xLLM — all multi-GPU/server-class deployment paths (examples use `--tp-size 8`); 19 community quantizations
  exist on HF — [zai-org/GLM-5](https://huggingface.co/zai-org/GLM-5). Nothing in the card describes a
  single-128GB-Mac deployment.
- Qwen3-Coder-Next is explicitly marketed for "coding agents and local development," 80B total / 3B active,
  with official support notes for llama.cpp, Ollama, LM Studio, MLX-LM, and KTransformers —
  [Qwen/Qwen3-Coder-Next](https://huggingface.co/Qwen/Qwen3-Coder-Next).
- gpt-oss-120b runs at $0.74/225-case Aider run — the cheapest per-run entry on the board — consistent with
  cheap local serving; it is a ~120B MoE class model (aider lists it as
  `openrouter/openai/gpt-oss-120b --reasoning-effort high`) — [aider.chat](https://aider.chat/docs/leaderboards/).

### Inferences

- Memory math (inference, not sourced): 128GB unified memory with macOS's default ~75% GPU wire limit leaves
  ~96GB for weights+KV. Q4_K_M of an 80B model is ~45–50GB (fits with huge context); MXFP4 of 120B ~60–63GB
  (fits); Q4 of 235B+ MoEs (~125GB+) does not; nothing below ~2.5-bit average fits a 744B model in 96GB.
- The 3B-active architecture of Qwen3-Coder-Next additionally means fast decode on Metal even at high quant —
  a meaningful local-latency advantage over denser 100B-class models.

### Gaps

- No verified 2026 data on distilled variants of DeepSeek-V3.2 / Kimi K2.5 / GLM-5, nor on whether GLM-5 has an
  "Air"-class sibling (GLM-4.5-Air was the 2025 analog; unverified this session).
- GGUF file sizes / recommended quants per model on 128GB: not retrieved from quant repos this session.

## Key Question 4: Community perception — "best local model for coding on a 128GB Mac" (2026), at what quant

### Takeaway

Could not directly retrieve r/LocalLLaMA threads this session (search engines and Reddit were not reachable via
fetch). The strongest proxy signal found: Qwen3-Coder-Next's adoption metrics — 594K downloads last month and
115 llama.cpp/LM Studio/Ollama quantizations within months of release — make it the most actively served
80B-class coding model on HF, and its card explicitly targets local CLI/IDE agent harnesses (Claude Code, Cline,
Kilo, Trae, Qwen Code).

### Cited Findings

- Qwen3-Coder-Next: 594,051 downloads last month, 1.68K likes, 115 quantizations tagged for llama.cpp/LM
  Studio/Jan/Ollama, 39 finetunes — [Qwen/Qwen3-Coder-Next](https://huggingface.co/Qwen/Qwen3-Coder-Next).
- GLM-5: 585,542 downloads last month, 2.12K likes, 19 llama.cpp-app-tagged quantizations, arXiv paper with 223
  citations listed on HF — [zai-org/GLM-5](https://huggingface.co/zai-org/GLM-5).
- Recommended sampling for Qwen3-Coder-Next: temperature=1.0, top_p=0.95, top_k=40 —
  [model card](https://huggingface.co/Qwen/Qwen3-Coder-Next).
- r/LocalLLaMA remains the active community hub (agentsindex.ai mirror dated Aug 2026; aggregator sites exist) —
  [agentsindex.ai](https://agentsindex.ai/r-localllama) (via Bing), but no thread content was retrievable.

### Inferences

- Combining benchmark fit + adoption + official local-harness support, Qwen3-Coder-Next is the evidence-backed
  default for "most capable model that actually runs well on a 128GB Mac for agentic coding" as of Oct 2026;
  at Q4_K_M (~48GB) it leaves ~45GB+ of headroom for 256K-class KV cache. gpt-oss-120b is the alternative when
  OpenAI-harness compatibility matters, but its Aider score (41.8% vs DeepSeek-V3.2's 74.2%) suggests it trails
  the 2026 open frontier badly on repo-level coding.
- Preferred quant: unverified by community sources this session; the inference above (Q4_K_M as quality/size
  sweet spot for 80B on 128GB) is standard practice, not a cited finding.

### Gaps

- The specific community consensus ("which quant do 128GB Mac users run", "does X beat Y in practice") could not
  be sourced: DuckDuckGo served a CAPTCHA, Bing's site:reddit.com query returned only navigational links, and
  Reddit itself was not fetched. Recommend a follow-up with direct old.reddit.com thread URLs.
- MLX vs GGUF performance on M5 Max for Qwen3-Next architecture (hybrid DeltaNet support in MLX/llama.cpp
  maturity): not researched.

## Key Question 5: Speculative decoding / MTP checkpoints — throughput impact and capability differences vs non-MTP quants

### Takeaway

GLM-5 ships an official MTP module and vendors document MTP/EAGLE speculative decoding as the recommended
serving config (3 speculative tokens); this boosts effective throughput but is orthogonal to quantization
capability — the drafted tokens still come from the same base model, so a non-MTP GGUF should be
capability-identical.

### Cited Findings

- GLM-5 vLLM recipe: `--speculative-config.method mtp --speculative-config.num_speculative_tokens 3`;
  SGLang recipe: `--speculative-algorithm EAGLE --speculative-num-steps 3 --speculative-eagle-topk 1
  --speculative-num-draft-tokens 4` — [zai-org/GLM-5 model card](https://huggingface.co/zai-org/GLM-5).
  This confirms MTP checkpoints exist for GLM-5 and are the vendor-recommended deployment mode.
- GLM-5's architecture note: it integrates DeepSeek Sparse Attention "largely reducing deployment cost while
  preserving long-context capacity" — [same card](https://huggingface.co/zai-org/GLM-5).

### Inferences

- MTP layers are auxiliary draft heads; llama.cpp GGUF conversions routinely drop them (they affect speed, not
  output distribution). Therefore an MTP-trained GLM-5 and a non-MTP GGUF conversion should score identically
  on benchmarks at the same quant of the trunk weights; any reported benchmark deltas between "MTP vs non-MTP
  quants" would indicate conversion bugs, not capability differences. (Inference from standard MTP design;
  not independently sourced for these specific models.)
- On Apple Silicon, llama.cpp's MTP support is limited vs vLLM/SGLang; the throughput win is mostly a
  datacenter-stack story as of the fetched docs.

### Gaps

- No measured tok/s numbers for GLM-5 or Qwen3-Coder-Next with/without MTP on Mac hardware were found.
- Whether Kimi K2.5 / DeepSeek-V3.2 MTP checkpoints affect their GGUF conversions: unverified.
- llama.cpp-side MTP/speculative support status for qwen3_next (DeltaNet) and glm_moe_dsa architectures in
  October 2026: not researched (would require the llama.cpp repo changelog).
