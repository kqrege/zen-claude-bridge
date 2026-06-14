# Security Policy

## Reporting a Vulnerability

If you discover a security vulnerability in this project, please report it privately by emailing:

**iacobdamianstefan@gmail.com**

Please do not open a public issue for security vulnerabilities.

We will acknowledge receipt within 48 hours and work on a fix. You will be credited for the discovery unless you prefer to remain anonymous.

## API Key Safety

- **Never commit `.env` files** or any file containing real API keys to version control.
- If you have accidentally exposed an API key (OpenCode Zen key, DeepSeek key, etc.), revoke it immediately through the provider's dashboard.
- The default `CLAUDE_GATEWAY_KEY` (`sk-local-zen`) is a local-only key used between Claude Desktop and this bridge. It does not need to be secret for localhost use, but change it if you expose the bridge to a network.
- If you paste logs online, scan them first for bearer tokens, API keys, and secrets. Use the `redact_secrets` utility in this project or a text editor search to remove sensitive strings.

## Scope

zen-claude-bridge is a local development tool. It is designed to run on `127.0.0.1` and should not be exposed to untrusted networks. If you need remote access, use a VPN or SSH tunnel — do not expose the bridge port directly.

## Dependencies

Keep dependencies updated to avoid known CVEs. Run:

```bash
pip install --upgrade -r requirements.txt
```

Review dependency changes when upgrading.
