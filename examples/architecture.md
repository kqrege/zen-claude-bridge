# Architecture

## Overview

zen-claude-bridge solves a specific problem: **Claude Desktop and Claude Code Gateway speak Anthropic's API format, but OpenCode Zen / DeepSeek speak OpenAI's chat completions format.** A translation layer is required.

This document explains the full request flow, the component roles, and the design decisions.

---

## Request Flow

```
┌──────────────────────┐
│   Claude Desktop     │
│   Claude Code        │
│   Claude Code Gateway│
└──────────┬───────────┘
           │
           │  HTTP POST /v1/messages
           │  Authorization: Bearer sk-local-zen
           │  Body (Anthropic format):
           │  {
           │    "model": "claude-sonnet-4-6",
           │    "messages": [{"role": "user", "content": "Hello"}],
           │    "stream": true,
           │    "tools": [...]
           │  }
           ▼
┌─────────────────────────────────────┐
│         zen-claude-bridge           │  Port 4000
│                                     │
│  1. Verify bearer token             │
│  2. Resolve model alias             │
│  3. Suppress dot probe if detected  │
│  4. [Optional] Bridge Memory        │
│     Compaction (summarize old msgs) │
│  5. Convert Anthropic messages      │
│     → OpenAI messages               │
│  6. Convert Anthropic tools         │
│     → OpenAI tools                  │
│  7. Call upstream /v1/chat/completions│
│  8. Track DeepSeek reasoning        │
│     recovery (streaming + non-str)  │
│  9. Convert OpenAI response         │
│     → Anthropic response            │
└──────────┬──────────────────────────┘
           │
           │  HTTP POST /v1/chat/completions
           │  Authorization: Bearer <opencode_key>
           │  Body (OpenAI format):
           │  {
           │    "model": "deepseek-v4-flash-free",
           │    "messages": [{"role": "user", "content": "Hello"}],
           │    "stream": true
           │  }
           ▼
┌─────────────────────────────────────┐
│      deepseek-cursor-proxy          │  Port 9000
│                                     │
│  Translates local requests to       │
│  OpenCode Zen API.                  │
│  --no-display-reasoning prevents    │
│  raw thinking blocks in output.     │
└──────────┬──────────────────────────┘
           │
           │  HTTPS /v1/chat/completions
           ▼
┌─────────────────────────────────────┐
│         OpenCode Zen API            │
│                                     │
│  deepseek-v4-flash-free model       │
│  Free, no payment method needed     │
└─────────────────────────────────────┘
```

---

## Why Not LiteLLM?

LiteLLM was evaluated first. It is an excellent project that supports many providers, but it was not the right fit here for these reasons:

### Problem: `/v1/responses` Routing

LiteLLM exposes multiple OpenAI-compatible endpoints, including:

- `/v1/chat/completions`
- `/v1/responses`
- `/v1/responses/input_tokens`

When Claude Code or Claude Gateway sends certain subagent requests, LiteLLM sometimes routes them to `/v1/responses` or `/v1/responses/input_tokens`. The `deepseek-cursor-proxy` backend only implements `/v1/chat/completions`, so these requests return 404 errors.

This happened nondeterministically — some requests would work, others would fail, depending on how LiteLLM interpreted the upstream capabilities.

### Solution: Custom Bridge

By writing a focused FastAPI bridge, we:

1. **Control exactly which endpoints exist** — only `/v1/messages`, `/v1/models`, `/v1/messages/count_tokens`, and health endpoints.
2. **No ambiguous routing** — every incoming request maps to one upstream call.
3. **No `/v1/responses`** — these endpoints simply do not exist, so they cannot be called.
4. **Full control over message conversion** — we handle edge cases like dot probes, model aliases, and tool call translation explicitly.

---

### Role of deepseek-cursor-proxy

`deepseek-cursor-proxy` is used as the upstream OpenAI-compatible proxy on port `9000`. It handles DeepSeek V4 thinking/tool-call compatibility, especially the `reasoning_content` behavior required by DeepSeek thinking-mode tool calls.

`zen-claude-bridge` sits in front of it and translates Claude/Anthropic Gateway requests into OpenAI-compatible chat completion requests.

## Why deepseek-cursor-proxy?

OpenCode Zen's API is a standard OpenAI-compatible chat completions endpoint. However, Claude Desktop sends messages in Anthropic format. Rather than calling OpenCode Zen directly, we need:

1. A running bridge (this repo) that translates formats.
2. A proxy that handles the actual HTTP call to OpenCode Zen and manages the API key.

`deepseek-cursor-proxy` serves as that proxy layer. It's battle-tested, handles the OpenCode Zen authentication, and provides the streaming SSE format that our bridge consumes.

The `--no-display-reasoning` flag is critical because without it, `deepseek-cursor-proxy` includes the model's internal reasoning as raw HTML comments (`<details><summary>Thinking</summary>...`) in the response. Since Claude Desktop renders the content as-is, this appears as literal text in the chat.

---

## Tool Call Translation

One of the bridge's key features is translating tool calls between Anthropic and OpenAI formats.

### Anthropic → OpenAI (request)

| Anthropic | OpenAI |
|-----------|--------|
| `tools[].input_schema` | `tools[].function.parameters` |
| `tools[].name` | `tools[].function.name` |
| `tool_use` content block | `tool_calls` in assistant message |
| `tool_result` content block | `tool` role message |

### OpenAI → Anthropic (response)

| OpenAI | Anthropic |
|--------|-----------|
| `tool_calls[].function.name` | `tool_use.name` |
| `tool_calls[].id` | `tool_use.id` |
| `tool_calls[].function.arguments` | `tool_use.input` |
| `finish_reason: tool_calls` | `stop_reason: tool_use` |

---

## Streaming

When Claude sends `"stream": true`, the bridge:

1. Sends a streaming request to `deepseek-cursor-proxy`.
2. Consumes OpenAI SSE chunks (`data: {...}` format).
3. Translates each chunk into Anthropic SSE events:
   - `message_start`
   - `content_block_start`
   - `content_block_delta`
   - `content_block_stop`
   - `message_delta`
   - `message_stop`

When `"stream": false` or absent, the bridge waits for the full upstream response and returns a single Anthropic JSON response.

---

## Local Token Counting

The `/v1/messages/count_tokens` endpoint does **not** call the upstream API. It returns an approximate count using a simple heuristic:

```
input_tokens ≈ total_text_length // 4
```

This is sufficient for Claude Desktop's UI display. If exact token counts are needed, consider implementing a tokenizer or calling the upstream's token counting endpoint if available.

When **Bridge Memory Compaction** is enabled, ``/v1/messages/count_tokens`` returns the estimated token count *after* compaction. This helps prevent Claude/Gateway from forcing its own destructive compaction before the bridge can compact the payload.

---

## Limitations

| Area | Limitation |
|------|------------|
| **Image input** | Image content blocks are replaced with a text placeholder — the upstream does not support vision. |
| **Token counts** | Approximate local estimation only. |
| **Concurrent requests** | One upstream call per request (no connection pooling sharing across requests — each request creates its own httpx client). |
| **Model fidelity** | All Claude model names are aliased to the same underlying model. Behavior differences between sonnet/haiku/opus are not preserved. |
| **Non-Windows** | Scripts are `.bat` files. Linux/macOS users should run the Python module directly. |
