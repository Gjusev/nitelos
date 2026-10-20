# Contributing

Thanks for considering a contribution to Nitelos.

## Ground rules

- **Honesty over polish.** Never fabricate results, metrics or model outputs in
  code, tests, docs or examples. A failing or skipped check is reported as
  such. See [SECURITY.md](SECURITY.md) for vulnerability reporting (not
  issues).
- **Synthetic fixtures only.** Never contribute real screenshots, credentials,
  secrets or personal data. Minimal synthetic reproductions are the norm.
- **Contract discipline.** The wire schemas are normative
  (`docs/planning/03-domain-model-and-api.md`). Field changes need an ADR and
  a version decision, not a quiet edit.

## Development setup

```text
git clone <your fork>
cd nitelos
uv sync --frozen --group dev
uv run pytest -q
uv run ruff check .
uv run ruff format --check .
uv run mypy
```

Tests are offline: the suite denies network access at the socket boundary, and
real local-model runs are separately gated (`NITELOS_RUN_LOCAL`).

## Workflow

1. Open an issue first for anything beyond a small fix.
2. Branch, write failing behavioral tests, then the smallest correct change.
3. Keep diffs scoped: no unrelated refactors or silent scope expansion.
4. All checks green (suite, ruff, format, strict mypy) before opening a PR.
5. Add a DCO sign-off to each commit (`git commit -s`, which appends a
   `Signed-off-by:` line). This is a text attestation that you may submit the
   work, not a cryptographic signature: GPG or SSH commit signing is welcome
   but optional. There is no CLA.

## What we value in review

Every public result labels its scope and basis; errors are coded and safe;
abstention is preserved rather than guessed; documentation stays true when
facts change (e.g., backend status wording that survives a gate failure).
