# OpenAI API Explainer

This document explains the main areas of the OpenAI API from the perspective of this repo, which exposes a local OpenAI-compatible endpoint at:

```text
http://127.0.0.1:8001/v1
```

For Dockerized Open WebUI, use:

```text
http://host.docker.internal:8001/v1
```

Official references:

- https://platform.openai.com/docs/api-reference/responses
- https://platform.openai.com/docs/api-reference/chat
- https://platform.openai.com/docs/api-reference/embeddings
- https://platform.openai.com/docs/api-reference/authentication

## Mental model

The OpenAI API is not one single shape. It is a family of compatible endpoint styles:

- `Responses API`
  This is the modern general-purpose API for model output.
- `Chat Completions API`
  The older but still widely used chat interface built around `messages`.
- `Completions API`
  The older prompt-in, text-out style API used by legacy clients.
- `Embeddings API`
  Returns vectors instead of text.
- `Realtime / streaming patterns`
  Ways to receive partial output before the request fully completes.

In practice, many local servers and tools only implement a subset, most commonly:

- `POST /v1/chat/completions`
- `GET /v1/models`
- sometimes streaming over server-sent events

That matters here because a local OpenAI-compatible wrapper may behave like the OpenAI API without implementing every modern endpoint.

## Authentication

OpenAI-style APIs usually expect:

```http
Authorization: Bearer <API_KEY>
```

Hosted OpenAI requires a real key.

Local OpenAI-compatible servers often accept:

- any placeholder key
- no key at all
- a custom local key if configured

That is why Open WebUI in this repo is configured with:

```text
OPENAI_API_KEY=dummy
```

The key is only there to satisfy clients that require the header.

## Models

Clients normally discover available models through:

```text
GET /v1/models
```

That endpoint returns model IDs the client can use in subsequent requests.

For a local wrapper, the model list may be:

- a single currently loaded model
- a synthetic alias
- a compatibility layer over one local GGUF

If a client cannot see your model, `GET /v1/models` is the first place to check.

## Responses API

The `Responses API` is the newer general interface. Conceptually, it is:

- one request format for text, structured output, tools, and multimodal inputs
- more flexible than the older chat/completions split

Typical shape:

```json
{
  "model": "gpt-4.1",
  "input": "Write a haiku about KV cache reuse."
}
```

Why it matters:

- this is the direction of the hosted OpenAI platform
- newer SDKs increasingly center this API
- some OpenAI features arrive here before older compatibility endpoints

Why it may not matter locally:

- many local OpenAI-compatible servers do not implement `POST /v1/responses`
- client compatibility is still often better with `chat/completions`

Rule of thumb:

- use `Responses` when you control both client and backend and know the backend supports it
- use `Chat Completions` when you need maximum compatibility with local wrappers and ecosystem tools

## Chat Completions API

This is still the most important compatibility surface in local model stacks.

Typical shape:

```json
{
  "model": "local-model",
  "messages": [
    {"role": "system", "content": "You are a precise assistant."},
    {"role": "user", "content": "Explain streaming briefly."}
  ]
}
```

Typical response shape:

```json
{
  "id": "chatcmpl-...",
  "object": "chat.completion",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "Streaming returns partial tokens as they are generated."
      },
      "finish_reason": "stop"
    }
  ]
}
```

Why this endpoint matters here:

- Open WebUI commonly uses OpenAI-compatible chat semantics
- many local wrappers and proxies target `POST /v1/chat/completions`
- it is often the safest integration point for local inference servers

## Legacy Completions API

This is the older prompt-based interface:

```json
{
  "model": "legacy-model",
  "prompt": "Write one sentence about context windows."
}
```

This API is useful to understand because:

- some old SDKs and scripts still use it
- some gateways translate it internally to chat-style requests

But for new work, it is usually the least important option in a modern local stack.

Use it only if:

- an older client hard-requires it
- your proxy or compatibility layer already exposes it

## Streaming

Streaming means the server sends partial output before the final response is complete.

This is critical for:

- better perceived latency
- chat UX responsiveness
- long generations
- agent UIs that want live updates

In OpenAI-compatible APIs, streaming is usually enabled with:

```json
{
  "stream": true
}
```

For `chat/completions`, the server usually returns server-sent events where each chunk contains a partial delta. Conceptually:

```text
data: {"choices":[{"delta":{"content":"Strea"}}]}
data: {"choices":[{"delta":{"content":"ming"}}]}
data: [DONE]
```

Important debugging points:

- If the client hangs until the end, check whether streaming is actually enabled.
- If the client errors immediately, check whether the server supports SSE streaming.
- If chunks arrive but look malformed, check whether the client expects chat deltas versus full text snapshots.
- Reverse proxies can break streaming by buffering responses.

For local stacks, streaming failures are often caused by:

- a wrapper that supports normal responses but not streamed ones
- a client expecting OpenAI delta events while the backend emits a different chunk format
- proxy buffering between the client and the model server

## Tools and function calling

OpenAI-style APIs can let the model request tool calls instead of only returning text.

At a high level:

- the client sends tool definitions
- the model chooses whether to call one
- the response contains a structured tool call
- the application executes the tool and sends the result back

This is the basis for agent behavior.

In local compatibility layers, tool support varies a lot:

- some fully support OpenAI-style tool calls
- some expose partial support
- some ignore tool definitions entirely

If agent behavior is flaky, verify:

- the endpoint actually supports tools
- the tool-call schema matches what the client expects
- the local model is instruction-tuned enough to use tools reliably

## Structured output

A related concept is structured or schema-constrained output.

This is useful when you want:

- JSON objects
- strict machine-readable fields
- predictable extraction output

Common failure modes:

- the model returns prose around the JSON
- the client expects strict schema support but the backend only supports plain text
- streaming is enabled for a workflow that assumes a fully valid final JSON object

For local servers, plain prompting plus post-validation is often more portable than assuming full hosted-API structured-output support.

## Embeddings API

Embeddings turn text into vectors for:

- search
- retrieval
- clustering
- semantic matching

Typical request:

```json
{
  "model": "text-embedding-model",
  "input": "llama.cpp KV cache"
}
```

Typical response:

- one or more vectors
- token usage metadata

This is separate from text generation. A server can support chat/completions without supporting embeddings.

For local stacks, embeddings may come from:

- the same service as chat generation
- a different local process
- a hosted provider

That distinction matters for Open WebUI and RAG systems, because the chat backend and the embedding backend are often different services.

## Error handling

When debugging an OpenAI-compatible integration, check these in order:

1. `GET /v1/models` works.
2. A non-streaming `POST /v1/chat/completions` works.
3. A streaming chat request works.
4. Tool calling works, if needed.
5. Embeddings work, if needed.

Common failure classes:

- `401` or `403`
  Bad key, missing key, or a client that insists on auth headers.
- `404`
  Wrong endpoint path, such as `/v1/responses` against a server that only supports `chat/completions`.
- `400`
  Request schema mismatch, unsupported fields, or invalid model ID.
- `500`
  Backend crash, wrapper bug, or model-server failure.

## Compatibility advice for this repo

For this repo's local server, default assumptions should be:

- prefer `POST /v1/chat/completions`
- expect `GET /v1/models`
- treat `Responses API` support as optional unless verified
- use `OPENAI_API_KEY=dummy` when a client insists on a key
- use host-side `http://127.0.0.1:8001/v1`
- use Docker-side `http://host.docker.internal:8001/v1`

If you are integrating a new client, the safest initial smoke test is:

1. list models
2. send one non-streaming chat completion
3. test streaming
4. only then try tools, JSON mode, or embeddings

## Example smoke tests

List models:

```bash
curl -s http://127.0.0.1:8001/v1/models
```

Basic chat completion:

```bash
curl -s http://127.0.0.1:8001/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -H 'Authorization: Bearer dummy' \
  -d '{
    "model": "local-model",
    "messages": [
      {"role": "user", "content": "Say hello in one sentence."}
    ]
  }'
```

Streaming chat completion:

```bash
curl -N http://127.0.0.1:8001/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -H 'Authorization: Bearer dummy' \
  -d '{
    "model": "local-model",
    "stream": true,
    "messages": [
      {"role": "user", "content": "Count from one to five."}
    ]
  }'
```

## Practical takeaway

If you only remember one thing, it should be this:

- `Responses` is the newer general OpenAI API
- `Chat Completions` is still the most important compatibility target
- streaming is essential for UX and often the first thing proxies break
- local stacks rarely implement every hosted OpenAI feature
- always verify the exact endpoint surface your local wrapper actually supports
