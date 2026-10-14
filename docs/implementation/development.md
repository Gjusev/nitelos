# Development instructions

Requirements: [uv](https://docs.astral.sh/uv/) and Python 3.12 or 3.13 (uv can provision either).
The default development interpreter is pinned in `.python-version` (3.12).

```text
uv sync --frozen --group dev          # core + dev tools, no optional extras
uv run pytest -q                      # offline suite; markers local_model/paid_api excluded by default
uv run ruff check .
uv run ruff format --check .
uv run mypy                           # strict, src/nitelos
uv build                              # wheel + sdist into dist/
```

Ordinary tests deny network access at the socket boundary (`tests/conftest.py`).
Dependency, lockfile, public-contract and CI changes are centralized: implementers request them
from the orchestrator instead of editing `pyproject.toml`, `uv.lock` or `.github/` directly.

To test on Python 3.13 without disturbing the default environment:

```text
UV_PROJECT_ENVIRONMENT=.venv-313 uv sync --frozen --group dev --python 3.13
UV_PROJECT_ENVIRONMENT=.venv-313 uv run --frozen --python 3.13 pytest -q
```
