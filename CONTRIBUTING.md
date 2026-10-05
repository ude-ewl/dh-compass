# Contributing

Contributions are provided under the project's MIT license. Submit only material
you own or have permission to contribute, and retain third-party copyright and
license notices. Do not commit provider data, credentials, caches or run outputs.
Record the source and units when changing model assumptions.

```bash
uv sync --extra web
uv run pytest
uv run ruff check .
uv run python scripts/release_audit.py
```

Keep solver work mocked in ordinary tests. Configuration paths are resolved by
PathConfig; avoid current-directory assumptions and import-time computation.
For frontend changes run `npm ci`, `npm run lint`, `npm run typecheck`,
`npm run test`, `npm run test:e2e`, `npm run build` and `npm run licenses:check`
inside `frontend/`. Preserve English/German placeholders, units and active state.

See [the release checklist](docs/release-checklist.md) before publishing artifacts.
