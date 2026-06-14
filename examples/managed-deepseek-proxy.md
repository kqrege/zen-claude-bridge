# Managed `deepseek-cursor-proxy`

## Why This Exists

`zen-claude-bridge` depends on [`deepseek-cursor-proxy`](https://github.com/yxlao/deepseek-cursor-proxy) to translate OpenAI-compatible chat completions into OpenCode Zen API calls, preserving DeepSeek V4 `reasoning_content` for tool-call workflows.

Previously, users had to manually:

1. Clone the `deepseek-cursor-proxy` repository.
2. Install its dependencies (`uv sync`).
3. Remember where they put it.
4. Run it from the correct directory.

This was error-prone and confusing, especially for beginners.

## How It Works Now

Starting with v0.2.0, `zen-claude-bridge` manages `deepseek-cursor-proxy` **automatically**.

### Auto-Managed Location

The proxy is cloned into a hidden folder at the root of this repository:

```text
.external/
  deepseek-cursor-proxy/
    .git/
    pyproject.toml
    src/
    ...
```

This folder is:

- **Ignored by git** — it will not appear in commits or PRs.
- **Auto-cloned** by `scripts\setup-windows.bat`.
- **Auto-detected** by `scripts\run-deepseek-proxy.bat`.
- **Safe to delete** — re-run `setup-windows.bat` to re-clone.

### What You Need to Do

**Nothing.** The setup script handles everything.

```powershell
scripts\setup-windows.bat   # Clones deepseek-cursor-proxy automatically
scripts\run-all.bat          # Starts proxy + bridge
```

That's it. No manual cloning, no path configuration, no `uv sync` by hand.

## Updating

To update to the latest version of `deepseek-cursor-proxy`:

```powershell
scripts\update-deepseek-proxy.bat
```

This runs `git pull --ff-only` inside the managed copy. It will not destroy local changes or reset your repository.

## Reinstalling

If the managed copy gets corrupted or you want a fresh clone:

```powershell
rmdir /s .external\deepseek-cursor-proxy
scripts\setup-windows.bat
```

Or just delete the entire `.external` folder:

```powershell
rmdir /s .external
scripts\setup-windows.bat
```

## Alternative: Manual Installation

You can still use a manually installed `deepseek-cursor-proxy` if you prefer. Just set the `DEEPSEEK_CURSOR_PROXY_DIR` environment variable before running the scripts:

```powershell
set DEEPSEEK_CURSOR_PROXY_DIR=C:\path\to\your\deepseek-cursor-proxy
scripts\run-deepseek-proxy.bat
```

When `DEEPSEEK_CURSOR_PROXY_DIR` is set, the script will use your custom path instead of the managed copy.

## Architecture

```
Claude Desktop / Claude Code Gateway
        │
        ▼
zen-claude-bridge (port 4000)    ← This repo
        │
        ▼
.external/deepseek-cursor-proxy/ (port 9000)   ← Auto-managed
        │
        ▼
OpenCode Zen API (deepseek-v4-flash-free)
```

## Attribution

[`deepseek-cursor-proxy`](https://github.com/yxlao/deepseek-cursor-proxy) is an independent MIT-licensed project by **yxlao**. It handles DeepSeek V4 `reasoning_content` compatibility.

`zen-claude-bridge` provides the Claude/Anthropic-compatible Gateway layer in front of it. No affiliation or endorsement is implied.

- **Project**: https://github.com/yxlao/deepseek-cursor-proxy
- **License**: MIT
- **Role in this stack**: Routes OpenAI chat completions to OpenCode Zen API, preserving DeepSeek thinking blocks for tool calls.

## License Notice

The managed copy of `deepseek-cursor-proxy` retains its own MIT license and copyright notices. Its source code is not modified or re-licensed by `zen-claude-bridge`. See `.external/deepseek-cursor-proxy/LICENSE` for details.
