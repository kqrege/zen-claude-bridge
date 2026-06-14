# Contributing

Contributions are welcome. By contributing you agree that your work will be licensed under the same Apache-2.0 license as this project.

## Guidelines

1. **Fork the repository** and create a feature branch.
2. **Make your changes** — keep them focused. One pull request per feature or fix.
3. **Include tests** for new functionality. Run `pytest` and ensure all tests pass.
4. **No secrets** — do not commit API keys, tokens, or credentials of any kind.
5. **Preserve attribution** — keep the existing copyright and license notices intact. If you add substantial new files, include the Apache-2.0 header.
6. **Open a pull request** — describe what you changed and why.

## Code Style

- Python code should follow PEP 8.
- Use type hints for public functions.
- Keep functions small and focused.
- Prefer readability over cleverness.

## Testing

```bash
pytest
```

Aim to keep coverage at or above 80% for the `src/zen_claude_bridge/` package.

## Reporting Issues

Open a GitHub issue for bugs, feature requests, or questions. For security issues, see [SECURITY.md](SECURITY.md).

## License

By contributing, you agree that your contributions will be licensed under the Apache-2.0 license included in this repository.
