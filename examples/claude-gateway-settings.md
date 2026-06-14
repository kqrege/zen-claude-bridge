# Claude Gateway Configuration

This guide explains how to configure Claude Desktop and Claude Code Gateway to use zen-claude-bridge.

---

## Prerequisites

1. `deepseek-cursor-proxy` is running on port 9000.
2. `zen-claude-bridge` is running on port 4000.
3. Your `.env` has `OPENCODE_ZEN_API_KEY` set correctly.

---

## Claude Desktop Settings

Open Claude Desktop settings (gear icon → Account Settings or through the settings file).

### Settings File Location

- **Windows:** `%APPDATA%\Claude\claude_desktop_config.json`
- **macOS:** `~/Library/Application Support/Claude/claude_desktop_config.json`

### Example Configuration

```json
{
  "gateway": {
    "url": "http://127.0.0.1:4000",
    "apiKey": "sk-local-zen",
    "authType": "bearer"
  },
  "models": {
    "allowlist": [
      "claude-sonnet-4-6",
      "claude-haiku-4-5-20251001",
      "claude-haiku-4-5",
      "claude-haiku-4-5-latest",
      "claude-3-5-haiku-latest",
      "claude-3-5-sonnet-latest",
      "claude-opus-4-1"
    ]
  }
}
```

### Field Descriptions

| Field | Value | Notes |
|-------|-------|-------|
| `gateway.url` | `http://127.0.0.1:4000` | The bridge must be running on this port |
| `gateway.apiKey` | `sk-local-zen` | Must match `CLAUDE_GATEWAY_KEY` in `.env` |
| `gateway.authType` | `bearer` | Case-insensitive |
| `models.allowlist` | (see above) | All these model names must be present for subagents to work |

---

## Model Allowlist Notes

Claude Code spawns subagents that request specific model versions. If a model is not in the allowlist, the subagent request will fail.

The bridge accepts all these model names and routes them to `deepseek-v4-flash-free`. You do **not** need separate upstream models for each one — the allowlist is purely for Claude to accept the request.

If you encounter errors like `model "claude-haiku-4-5-20251001" not found`, add the missing model name to the allowlist.

---

## Verification

### Step 1: Test the bridge directly

```bash
curl -s http://127.0.0.1:4000/ -H "Authorization: Bearer sk-local-zen"
# Expected: {"status":"ok","service":"zen-claude-bridge","version":"0.1.0"}
```

### Step 2: List models

```bash
curl -s http://127.0.0.1:4000/v1/models -H "Authorization: Bearer sk-local-zen"
# Expected: {"object":"list","data":[{"id":"claude-sonnet-4-6",...}, ...]}
```

### Step 3: Test generation

```bash
curl -s -X POST http://127.0.0.1:4000/v1/messages \
  -H "Authorization: Bearer sk-local-zen" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "claude-sonnet-4-6",
    "messages": [{"role": "user", "content": "Reply exactly: GATEWAY_OK"}],
    "max_tokens": 50
  }'
```

### Step 4: Configure Claude Desktop

After configuring the settings file, restart Claude Desktop. Send a test message — if the configuration is correct, Claude will route through the bridge.

---

## Troubleshooting Gateway Settings

**Problem: "Invalid API key"**
- Verify `gateway.apiKey` matches `CLAUDE_GATEWAY_KEY` in `.env`.
- Check for extra whitespace or quotes in the config file.

**Problem: "Model not found"**
- The model name is not in the `models.allowlist`.
- Check Claude Desktop logs for the exact model name being requested.

**Problem: "Connection refused"**
- The bridge is not running. Start it with `scripts\run-bridge.bat`.

**Problem: "Empty response" or timeouts**
- `deepseek-cursor-proxy` may not be running on port 9000.
- The OpenCode Zen API key may be invalid or expired.
- Check the proxy window for error messages.
