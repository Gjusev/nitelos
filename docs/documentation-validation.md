# Documentation validation (2026-10-20)

What was checked after the [documentation audit](documentation-audit.md), on Windows 11,
CPython 3.12.2, `uv run`, commit `64299ce` plus the uncommitted doc changes.
Status per line: **checked** (ran, passed), **failed**, or **not run**.

| Check | Command | Result | Status |
|---|---|---|---|
| README quickstart block | executed with `python -c` from the fenced block | exit 0, prints `success` | checked |
| `docs/quickstart.md` script | executed from the fenced block | exit 0, output identical to the literal output in the page | checked |
| "Change one value" claim | `examples/quickstart.py` with `"validation_error": True` | exit 0, `decision: failure`, `CRITERION_REFUTED` (`videos/nitelos-launch/evidence/quickstart_flipped.stdout.txt`) | checked |
| README "The problem" output | `uv run python examples/demo_incomplete_form.py` | byte-identical to `evidence/demo_incomplete_form.stdout.txt` | checked |
| Example outputs used in docs and films | `examples/quickstart.py`, `examples/demo_external_pending.py` | byte-identical to the captured `evidence/*.stdout.txt` | checked |
| Core-only checkout command | `uv sync --frozen --no-dev --dry-run` | plan removes the dev group (pytest-cov, ruff, scipy, ...) and keeps the core | checked |
| Relative links and anchors | `uv run python videos/nitelos-launch/tools/check_links.py` | 111 targets in 26 files (including these two reports), 0 broken | checked |
| External links | same script lists them | 5 listed (uv docs, PyPI page, 3 shields.io badges), not fetched | not run |
| Documentation tests | `uv run pytest -q -k "doc or DOC"` | 15 passed | checked |
| Full test suite | `uv run pytest -q` | 604 passed, 2 skipped (symlink refused by the platform), 1 deselected | checked |
| Lint and format | `uv run ruff check .` / `uv run ruff format --check .` | all checks passed, 182 files formatted | checked |
| Python fragments in `custom-adapters.md`, `lifecycle.md`, `traces.md`, `recipes/caller-collection.md`, `implementation/nit-008-adapter-design.md` | n/a (fragments, not scripts) | read for consistency with the API names only | not run |
| README rendering on GitHub (dark/light `<picture>`) | n/a (private repo; not viewed in the GitHub UI) | SVGs validated as XML and rendered in Chromium | not run on GitHub |

Nothing failed in this pass.
