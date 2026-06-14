# Zen Claude Bridge

**Run OpenCode Zen / DeepSeek V4 Flash Free through Claude Desktop and Claude Code Gateway.**

This project provides a local FastAPI bridge that translates Anthropic's Claude API format (`/v1/messages`) into OpenAI-compatible chat completions, routing requests through `deepseek-cursor-proxy` to the **OpenCode Zen** API.

No LiteLLM. No OpenAI API key. No billing surprises. Just a clean local bridge.

---

## Architecture

```
Claude Desktop / Claude Code Gateway
        │
        │  Anthropic /v1/messages
        │  Bearer: sk-local-zen
        ▼
┌─────────────────────────────┐
│  zen-claude-bridge          │  ← local FastAPI app (port 4000)
│  - /v1/messages             │
│  - /v1/models               │
│  - /v1/messages/count_tokens│
│  - dot-probe suppression    │
│  - model aliasing           │
│  - tool call conversion     │
└──────────┬──────────────────┘
           │
           │  OpenAI /v1/chat/completions
           │  stream=true
           ▼
┌─────────────────────────────┐
│  deepseek-cursor-proxy      │  ← local proxy (port 9000)
│  --no-display-reasoning     │
└──────────┬──────────────────┘
           │
           │  OpenCode Zen API
           │  /v1/chat/completions
           ▼
┌─────────────────────────────┐
│  OpenCode Zen               │
│  deepseek-v4-flash-free     │
└─────────────────────────────┘
```

---

## Why This Exists

### What Didn't Work

**LiteLLM** was the first attempt. It supports both Anthropic and OpenAI formats, which seemed perfect. However, LiteLLM incorrectly routed some requests to OpenAI's Responses API:

- `/v1/responses` — LiteLLM tried to proxy these, but the upstream only supports chat completions.
- `/v1/responses/input_tokens` — Same problem, same 404.

The `deepseek-cursor-proxy` backend only implements `/v1/chat/completions`. LiteLLM's routing for Anthropic `/v1/messages` and Claude Code subagent requests would sometimes leak to these unsupported endpoints.

**The fix:** A custom FastAPI bridge that cleanly maps every Anthropic endpoint to OpenAI chat completions — no ambiguous routing.

### What Does Work

| Component | Purpose |
|-----------|---------|
| `zen-claude-bridge` (this repo) | Anthropic → OpenAI translation, model aliasing, dot-probe suppression, streaming |
| `deepseek-cursor-proxy` | Routes OpenAI chat completions to OpenCode Zen API |
| OpenCode Zen | Provides `deepseek-v4-flash-free` model at no cost |

### Key Design Decisions

- **No LiteLLM** — The custom bridge gives full control over routing and prevents `/v1/responses` leaks.
- **`--no-display-reasoning`** — Without this flag, `deepseek-cursor-proxy` emits raw `<details><summary>Thinking</summary>` blocks into the response, which Claude Desktop renders as literal HTML text.
- **Model aliases** — Claude Code subagents request specific model names (`claude-sonnet-4-6`, `claude-haiku-4-5-20251001`, etc.). The bridge accepts all of them and routes everything to `deepseek-v4-flash-free`.
- **Dot-probe suppression** — Claude sometimes sends a single-token `"."` probe. The bridge detects and suppresses it so responses don't start with a stray dot.
- **Local token counting** — `/v1/messages/count_tokens` returns an approximate count without calling the upstream API.

---

## Requirements

| Item | Notes |
|------|-------|
| **OS** | Windows recommended (scripts are `.bat`). Linux/macOS can use the Python module directly. |
| **Python** | 3.10+ or 3.11+ |
| **`uv`** | Required by `deepseek-cursor-proxy`. Install from [astral.sh/uv](https://docs.astral.sh/uv/) |
| **OpenCode Zen API key** | Required for upstream access. Get it from the OpenCode dashboard. |
| **Claude Desktop / Claude Code Gateway** | Your Anthropic account with gateway feature enabled. |
| **[`yxlao/deepseek-cursor-proxy`](https://github.com/yxlao/deepseek-cursor-proxy)** | Required upstream proxy. Handles DeepSeek reasoning/tool-call compatibility on port 9000. |

---

## Installation

### 1. Clone the repository

```bash
git clone https://github.com/kqrege/zen-claude-bridge.git
cd zen-claude-bridge
```

### 2. Run setup

```batch
scripts\setup-windows.bat
```

This creates a Python virtual environment, installs dependencies, and copies `.env.example` to `.env`.

### 3. Configure your API key

Edit `.env`:

```env
CLAUDE_GATEWAY_KEY=sk-local-zen
OPENCODE_ZEN_API_KEY=your_actual_opencode_key_here
DEEPSEEK_MODEL=deepseek-v4-flash-free
DEEPSEEK_UPSTREAM_URL=http://127.0.0.1:9000/v1/chat/completions
BRIDGE_HOST=127.0.0.1
BRIDGE_PORT=4000
REQUEST_TIMEOUT_SECONDS=600
```

### 4. Install `deepseek-cursor-proxy`

```bash
git clone https://github.com/mylxsw/deepseek-cursor-proxy.git
cd deepseek-cursor-proxy
uv sync
```

### 5. Start the proxy (Window 1)

```batch
scripts\run-deepseek-proxy.bat
```

Or directly:

```bash
cd path\to\deepseek-cursor-proxy
uv run deepseek-cursor-proxy --no-ngrok --port 9000 --no-display-reasoning
```

### 6. Start the bridge (Window 2)

```batch
scripts\run-bridge.bat
```

Or:

```bash
cd zen-claude-bridge
python -m uvicorn zen_claude_bridge.app:app --host 127.0.0.1 --port 4000
```

### 7. Start all at once

```batch
scripts\run-all.bat
```

---

## Claude Gateway Configuration

Configure Claude Desktop or Claude Code Gateway with these settings:

| Setting | Value |
|---------|-------|
| **URL** | `http://127.0.0.1:4000` |
| **API key** | `sk-local-zen` |
| **Auth type** | Bearer |
| **Model allowlist** | See below |

### Model aliases (add all to allowlist)

```
claude-sonnet-4-6
claude-haiku-4-5-20251001
claude-haiku-4-5
claude-haiku-4-5-latest
claude-3-5-haiku-latest
claude-3-5-sonnet-latest
claude-opus-4-1
deepseek-v4-flash-free
deepseek-v4-flash
```

All of these route to `deepseek-v4-flash-free` — you only need them in the allowlist for Claude to accept subagent requests.

### Testing the connection

Send this test prompt:

```
Reply exactly: OK_PROXY_WORKS
```

If you get back `OK_PROXY_WORKS`, everything is connected.

---

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` / `HEAD` | `/` | Health check |
| `GET` | `/v1/models` | List available model aliases |
| `POST` | `/v1/messages` | Generate a response (streaming or non-streaming) |
| `POST` | `/v1/messages/count_tokens` | Approximate local token count |

All `POST` endpoints also work with `?beta=true`.

---

## Troubleshooting

| Symptom | Likely Cause |
|---------|-------------|
| `Could not import module "C"` | Uvicorn path issue on Windows — use `python -m uvicorn` |
| `/v1/responses` 404 | Something is still routing to LiteLLM or Responses API — this bridge does not expose those endpoints |
| `No payment method` on DeepSeek | You're using `deepseek-v4-flash` (paid) instead of `deepseek-v4-flash-free` (free) |
| Raw `<details><summary>Thinking</summary>` in output | `deepseek-cursor-proxy` is running without `--no-display-reasoning` |
| Response starts with `"."` | Dot-probe suppression is broken |
| Subagent requests failing with "model not found" | Claude model alias is missing from the allowlist or the bridge's alias list |

See [examples/troubleshooting.md](examples/troubleshooting.md) for detailed solutions.

---

## Development

```bash
# Install dev dependencies
pip install -e ".[test]"

# Run tests
pytest

# Run with auto-reload
python -m uvicorn zen_claude_bridge.app:app --host 127.0.0.1 --port 4000 --reload
```

---

## Security

- **Never commit `.env` files** — the `.gitignore` excludes them, but double-check.
- **Rotate leaked keys immediately.** If you've pasted logs containing your OpenCode Zen key, revoke it through the OpenCode dashboard.
- The bridge runs on `127.0.0.1` by design. Do not expose it to untrusted networks.
- See [SECURITY.md](SECURITY.md) for the full security policy and vulnerability reporting.

---

## Project Structure

```
zen-claude-bridge/
├── src/zen_claude_bridge/
│   ├── __init__.py
│   ├── app.py             # FastAPI app with all endpoints
│   ├── config.py          # Environment variable configuration
│   ├── conversions.py     # Anthropic ↔ OpenAI message/tool conversion
│   ├── security.py        # Bearer auth, secret redaction
│   ├── streaming.py       # Anthropic-compatible SSE streaming
│   └── token_count.py     # Local approximate token counting
├── tests/
│   ├── test_conversions.py
│   ├── test_token_count.py
│   ├── test_dot_probe.py
│   └── test_models.py
├── scripts/
│   ├── setup-windows.bat
│   ├── run-bridge.bat
│   ├── run-deepseek-proxy.bat
│   ├── run-all.bat
│   └── test-bridge.bat
├── examples/
│   ├── architecture.md
│   ├── claude-gateway-settings.md
│   └── troubleshooting.md
├── .env.example
├── .gitignore
├── requirements.txt
├── pyproject.toml
├── LICENSE
├── NOTICE
├── SECURITY.md
├── CONTRIBUTING.md
├── CODE_OF_CONDUCT.md
└── CHANGELOG.md
```

---

## License

Apache-2.0. See [LICENSE](LICENSE) and [NOTICE](NOTICE).

## Disclaimer

This project is an independent compatibility bridge. It is not affiliated with Anthropic, Claude, DeepSeek, Cursor, or OpenCode. All product names and trademarks are the property of their respective owners.

## Credits / Acknowledgements

This project is designed to work with [`yxlao/deepseek-cursor-proxy`](https://github.com/yxlao/deepseek-cursor-proxy), which handles DeepSeek V4 thinking/tool-call compatibility by preserving and reinjecting `reasoning_content`.

`zen-claude-bridge` provides the Claude/Anthropic-compatible Gateway layer in front of that proxy. It does not replace `deepseek-cursor-proxy`; it depends on it for the DeepSeek reasoning/tool-call compatibility path used in this setup.

This project is independent and is not affiliated with Anthropic, Claude, DeepSeek, Cursor, OpenCode, or the `deepseek-cursor-proxy` maintainers.
