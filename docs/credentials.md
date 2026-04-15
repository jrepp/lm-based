# Credentials and routing

This repo supports two ways to reach cloud LLM providers: **direct** API calls
using a provider key you supply, or **proxied** calls routed through the local
x402 payment proxy (default port 8402) that handles authentication and USDC
micropayments automatically.

## Two-tier model

```
Your code / open-webui
        │
        ▼
   ClawRouter  (reads clawrouter.json)
        │
   ┌────┴─────────────────┐
   │                      │
   ▼                      ▼
Direct API           x402 proxy :8402
(key in env)         (no key needed)
   │                      │
provider endpoint    provider endpoint
```

**Direct routing** — when `OPENAI_API_KEY` (etc.) is set in your environment,
ClawRouter sends that provider's traffic straight to the native API endpoint
using your key.  You pay the provider directly.

**Proxy routing** — when the key is absent, the request goes to the local x402
proxy.  The proxy holds its own credentials and settles via USDC micropayments.
No provider key is needed from you for this path.

The routing decision is made at config-generation time (`./clawrouter_config.py`)
and written into `clawrouter.json`.  Re-generate whenever you add or remove keys.

## Setting credentials

Copy `.env.example` to `.env` and fill in the keys you have:

```bash
cp .env.example .env
$EDITOR .env
```

`.env` is gitignored.  Never commit real keys.

After editing `.env`, regenerate the routing config:

```bash
./clawrouter_config.py
```

## Checking what's configured

```bash
# Show credential status for all providers (reads live env)
./clawrouter_config.py --providers

# Full stack check: sidecars, endpoints, credential audit
./clawrouter_config.py --doctor
```

Example `--providers` output:

```
Cloud provider credentials  (set keys in .env — see docs/credentials.md)

  Provider                  Env var             Status    Routing
  ----------------------------------------------------------------------------------
  · GLM-5                   GLM_API_KEY         [not set] x402 proxy
  ✓ ChatGPT / GPT-4o        OPENAI_API_KEY      [set]     direct → https://api.openai.com/v1
  · MiniMax M2.7            MINIMAX_API_KEY      [not set] x402 proxy
  · DeepSeek Chat           DEEPSEEK_API_KEY    [not set] x402 proxy
  · Claude Sonnet 4.6       ANTHROPIC_API_KEY   [not set] x402 proxy
  · Grok 4.1 Fast           XAI_API_KEY         [not set] x402 proxy
  · Gemini 2.5 Pro          GEMINI_API_KEY      [not set] x402 proxy

  1 direct  ·  6 via x402 proxy
```

## Provider env var reference

| Provider              | Key env var        | Base URL env var    | Default direct endpoint |
|-----------------------|--------------------|---------------------|-------------------------|
| GLM-5                 | `GLM_API_KEY`      | `GLM_API_BASE`      | _(proxy only)_          |
| ChatGPT / GPT-4o      | `OPENAI_API_KEY`   | `OPENAI_API_BASE`   | `https://api.openai.com/v1` |
| MiniMax M2.7          | `MINIMAX_API_KEY`  | `MINIMAX_API_BASE`  | _(proxy only)_          |
| DeepSeek Chat         | `DEEPSEEK_API_KEY` | `DEEPSEEK_API_BASE` | `https://api.deepseek.com/v1` |
| Claude Sonnet 4.6     | `ANTHROPIC_API_KEY`| `ANTHROPIC_API_BASE`| `https://api.anthropic.com/v1` |
| Grok 4.1 Fast         | `XAI_API_KEY`      | `XAI_API_BASE`      | `https://api.x.ai/v1` |
| Gemini 2.5 Pro        | `GEMINI_API_KEY`   | `GEMINI_API_BASE`   | `https://generativelanguage.googleapis.com/v1beta/openai` |

## Base URL overrides

Each provider also has a `*_API_BASE` var.  Use it to:

- Point a provider at a compatible third-party endpoint (e.g. Azure OpenAI)
- Route through a local aggregator or caching proxy
- Override the direct endpoint for testing

When both the key and a base override are set, the override wins over the
default `direct_base`.

## clawrouter.json security

`clawrouter.json` stores `api_key_env` (the env var *name*), never the
resolved secret.  The file is gitignored but can safely be shared or committed
if needed — it contains no credentials.

ClawRouter resolves the actual key from the environment at runtime.
