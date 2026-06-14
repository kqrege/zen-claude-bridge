# Troubleshooting

Common issues encountered while setting up or running zen-claude-bridge, with solutions derived from actual debugging sessions.

---

## Error: `Invalid API key`

**When:** Claude Desktop or `curl` calls the bridge and gets 401.

**Causes:**
- The `Authorization` header is missing or malformed.
- The bearer token does not match `CLAUDE_GATEWAY_KEY` in `.env`.
- The `.env` file was not created or has the wrong key.

**Fix:**
1. Verify `.env` exists and contains `CLAUDE_GATEWAY_KEY=sk-local-zen`.
2. Check the request header is exactly `Authorization: Bearer sk-local-zen` (not `Bearer:`, not `X-API-Key`).
3. Restart the bridge after changing `.env`.

---

## Error: `No payment method`

**When:** Calling `deepseek-cursor-proxy` and OpenCode Zen returns a payment error.

**Cause:** The model name `deepseek-v4-flash` (without `-free`) is a paid model that requires billing setup.

**Fix:** Use `deepseek-v4-flash-free` instead. Check your `.env`:

```env
DEEPSEEK_MODEL=deepseek-v4-flash-free
```

Also verify that the `deepseek-cursor-proxy` configuration passes the correct model name.

---

## Error: `/v1/responses` 404

**When:** LiteLLM or some other proxy routes requests to OpenAI Responses API endpoints that do not exist on `deepseek-cursor-proxy`.

**Cause:** LiteLLM exposes `/v1/responses` and some client requests land there. The upstream only supports `/v1/chat/completions`.

**Fix:** Ensure you are using zen-claude-bridge (this project), not LiteLLM. This bridge does not expose `/v1/responses` at all. If you are using this bridge and still seeing `/v1/responses`, check your Claude Gateway configuration to ensure it points to `http://127.0.0.1:4000` (the bridge) and not a LiteLLM instance.

---

## Error: `/v1/responses/input_tokens` 404

**When:** Same scenario as above — LiteLLM routing to an unsupported endpoint.

**Cause:** Identical to `/v1/responses` — LiteLLM exposes this endpoint, but the upstream does not support it.

**Fix:** Same as above. Ensure you are routing through zen-claude-bridge.

---

## Raw `<details><summary>Thinking</summary>` in Output

**When:** Claude Desktop shows raw HTML tags like `<details><summary>Thinking</summary>...` in responses.

**Cause:** `deepseek-cursor-proxy` includes the model's internal reasoning in the response by default. Without the `--no-display-reasoning` flag, the proxy emits thinking blocks as raw HTML comment-like text.

**Fix:** Always run `deepseek-cursor-proxy` with the `--no-display-reasoning` flag:

```bash
uv run deepseek-cursor-proxy --no-ngrok --port 9000 --no-display-reasoning
```

If using the batch script, it already includes this flag.

---

## Leading Dot in Response

**When:** Every response starts with `"."` followed by the actual content (e.g., `.Hello, how can I help?`).

**Cause:** Claude sometimes sends a one-token probe containing only `"."` before a real request. This is a health check or capability probe. If the bridge does not suppress it, the probe message is processed by the upstream model, which generates a response to just `"."`.

**Fix:** The bridge includes dot-probe detection in `zen_claude_bridge/conversions.py`. If you see a leading dot, verify:
1. You are running the latest version of the bridge.
2. The `conversions.is_dot_probe()` function is being called (it runs in `app.py` for every `/v1/messages` request).

---

## Subagent: `model "claude-haiku-4-5-20251001" not found`

**When:** Claude Code spawns a subagent and the request fails with a model-not-found error.

**Cause:** Claude Code requests specific model versions for subagents. If the requested model name is not in the bridge's alias list or Claude Gateway's allowlist, the request fails.

**Fix:**
1. Add the missing model name to `CLAUDE_MODEL_ALIASES` in `src/zen_claude_bridge/config.py`.
2. Add the missing model name to the Claude Gateway `models.allowlist` configuration.

Current aliases include:
- `claude-sonnet-4-6`
- `claude-haiku-4-5-20251001`
- `claude-haiku-4-5`
- `claude-haiku-4-5-latest`
- `claude-3-5-haiku-latest`
- `claude-3-5-sonnet-latest`
- `claude-opus-4-1`

If Claude requests a new model name, add it to both lists.

---

## Uvicorn: `Could not import module "C"`

**When:** Running `uvicorn zen_claude_bridge.app:app` on Windows.

**Cause:** A Windows-specific path issue where uvicorn misinterprets the drive letter in the path (e.g. `C:\Users\...`).

**Fix:** Use `python -m uvicorn` instead of bare `uvicorn`:

```bash
python -m uvicorn zen_claude_bridge.app:app --host 127.0.0.1 --port 4000
```

The `run-bridge.bat` script already uses `python -m uvicorn`.

---

## Port 4000 Already in Use

**When:** Starting the bridge and getting an `OSError: [Errno 10048]` or similar.

**Cause:** Another process is already listening on port 4000.

**Fix:**
1. Find the process: `netstat -ano | findstr :4000`
2. Kill it: `taskkill /PID <pid> /F`
3. Or change the bridge port in `.env`:
   ```env
   BRIDGE_PORT=4001
   ```
4. Update Claude Gateway URL to match.

---

## Port 9000 Not Running

**When:** The bridge starts but generation requests fail or time out.

**Cause:** `deepseek-cursor-proxy` is not running on port 9000.

**Fix:**
1. Start the proxy: `scripts\run-deepseek-proxy.bat`
2. Verify it's running: check the terminal window or run:
   ```bash
   curl -s http://127.0.0.1:9000/v1/chat/completions -d "{}"
   ```
3. If using a different port, update `DEEPSEEK_UPSTREAM_URL` in `.env`.

---

## Empty Response or Timeout

**When:** The bridge responds but the content is empty or the request times out.

**Possible causes:**
- OpenCode Zen API key is missing, invalid, or expired.
- `REQUEST_TIMEOUT_SECONDS` is too low for long generations.
- Network issues reaching the OpenCode Zen API.
- Rate limiting on the OpenCode Zen API.

**Fix:**
1. Check the bridge terminal for error logs (they show upstream response codes).
2. Verify `OPENCODE_ZEN_API_KEY` in `.env`.
3. Increase timeout in `.env`: `REQUEST_TIMEOUT_SECONDS=1200`
4. Check if the proxy terminal shows any errors.

---

## Scripts Not Working (Linux/macOS)

**When:** Running `.bat` scripts on non-Windows systems.

**Cause:** Batch files are Windows-specific.

**Fix:** Run the Python commands directly:

```bash
# Setup
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Run bridge
python -m uvicorn zen_claude_bridge.app:app --host 127.0.0.1 --port 4000

# Run proxy
cd /path/to/deepseek-cursor-proxy
uv run deepseek-cursor-proxy --no-ngrok --port 9000 --no-display-reasoning
```
