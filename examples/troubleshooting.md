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

---

## `[deepseek-cursor-proxy] Refreshed reasoning_content history.`

**When:** The assistant response contains `[deepseek-cursor-proxy] Refreshed reasoning_content history.` as a visible line.

**What it is:** This is a notice from `deepseek-cursor-proxy`. It means the proxy had to recover or refresh the DeepSeek `reasoning_content` history, likely because prior tool-call reasoning content could not be restored from its cache.

**Effect:** Each time the proxy refreshes reasoning history, it may lose track of earlier tool-call context. If it happens frequently, the model may behave as though it forgot recent conversation context or tool results.

**Not automatically a context-limit error:** This notice is not the same as hitting a 200k context window. It is a cache/recovery event inside the proxy layer.

**Normal users:** The notice is hidden by default. You don't need to do anything.

**Debug users:** To see the notice for debugging, set:

```env
SHOW_DEEPSEEK_RECOVERY_NOTICE=true
```

Then restart the bridge. The notice will be visible in responses.

**To reduce occurrences:**

This is not the same as hitting a 200k context limit — the proxy's reasoning cache is missing or stale.

- **Enable Bridge Memory Compaction** — the bridge can track recovery events and activate reasoning-safe mode to minimize cache misses. See [Bridge Memory Compaction](../README.md#bridge-memory-compaction).
- Reduce the number of multi-turn tool-call sequences. Each tool round-trip adds reasoning content that the proxy must cache.
- If using Claude Code subagents, consider shorter subagent prompts.
- If the notice appears on every request, there may be a deeper issue with the proxy's reasoning cache. Try updating `deepseek-cursor-proxy`:

```powershell
scripts\update-deepseek-proxy.bat
```

---

## DeepSeek Proxy Debug: Reject Mode

`deepseek-cursor-proxy` has a debug mode that rejects responses where reasoning content is missing and produces verbose traces.

**Enable it:**

```powershell
set DEEPSEEK_PROXY_DEBUG_REJECT=1
scripts\run-deepseek-proxy.bat
```

This starts the proxy with:

```
--missing-reasoning-strategy reject --verbose --trace-dir .\trace-dumps
```

**Warning:** Verbose traces can contain your prompts, code, or API secrets. Do not share them publicly. Traces are saved to `trace-dumps/` under the project root.

**To restore normal mode:** Unset the env var or set it to anything other than `1`:

```powershell
set DEEPSEEK_PROXY_DEBUG_REJECT=
scripts\run-deepseek-proxy.bat
```

---

## Repeated Reasoning Recovery / Model Forgetting Context

**When:** You see repeated `DeepSeek reasoning_content recovery occurred` warnings in the logs. After these warnings begin, the model starts forgetting prior context, tool results, or user instructions.

**What it is:** Each time `deepseek-cursor-proxy` recovers reasoning content, it may lose track of older tool-call context. This is a proxy cache recovery event, not necessarily a context-limit error. If compaction changes the message prefix, the proxy cache can miss and trigger another recovery, creating a loop.

**Solutions:**

1. **Enable Bridge Memory Compaction** — set `BRIDGE_CONTEXT_COMPACTION=true` in `.env`. The bridge's reasoning-safe mode activates automatically after repeated recovery events and reduces proxy cache mismatches.

2. **Lower the trigger threshold** — if Claude still compacts internally before the bridge does, set a lower trigger:
   ```env
   BRIDGE_COMPACTION_TRIGGER_TOKENS=100000
   BRIDGE_COMPACTION_KEEP_RECENT_MESSAGES=12
   ```

3. **Increase summary size** — if the model still forgets details:
   ```env
   BRIDGE_COMPACTION_MAX_SUMMARY_CHARS=30000
   ```

4. **Check for downstream changes** — if you updated `deepseek-cursor-proxy` or changed its arguments, recovery behavior may change.

5. **Do not clear `reasoning_content.sqlite3`** — this database stores the proxy's reasoning cache. Clearing it forces all sessions to enter recovery mode.

---

## Bridge Memory: Summary Contains Sensitive Info

**When:** Memory summary files in `.bridge-memory/` contain sensitive information.

**Fix:** Disable compaction:
```env
BRIDGE_CONTEXT_COMPACTION=false
```
Then delete the `.bridge-memory/` directory:
```powershell
Remove-Item .bridge-memory -Recurse -Force
```

---

## Bridge Memory: Compaction Happens Too Often

**When:** Compaction logs appear on every request.

**Fix:** Raise the trigger token threshold:
```env
BRIDGE_COMPACTION_TRIGGER_TOKENS=250000
```

---

## Bridge Memory: Model Still Forgot Something

**When:** After compaction, the model does not remember a specific detail.

**Fix:** The extractive summary preserves file paths, commands, errors, and decisions, but may miss nuanced details. Try:

1. Increase `BRIDGE_COMPACTION_MAX_SUMMARY_CHARS=30000` — keeps more text per message.
2. Increase `BRIDGE_COMPACTION_KEEP_RECENT_MESSAGES=30` — keeps more raw messages.
3. Lower `BRIDGE_COMPACTION_TRIGGER_TOKENS=120000` — compacts earlier so more raw messages fit.
