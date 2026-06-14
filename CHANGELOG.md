# Changelog

## [0.1.0] — 2026-06-14

### Added

- Initial public release.
- FastAPI bridge exposing Anthropic `/v1/messages` endpoint.
- Endpoints: `GET /`, `HEAD /`, `GET /v1/models`, `POST /v1/messages`, `POST /v1/messages/count_tokens`.
- Converts Anthropic message/tool format to OpenAI chat completions format.
- Streaming support with Anthropic-compatible SSE events.
- Local approximate token counting (no upstream call).
- Dot-probe suppression.
- Model alias support for Claude subagent model names.
- Bearer authentication.
- Windows setup and run scripts.
- Full test suite with pytest.
