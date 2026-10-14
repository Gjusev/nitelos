# Rules for implementer and reviewer instances

These rules apply to every Claude Code instance assigned a Nitelos task. The orchestrator owns integration.

1. Work only inside the worktree path given in your assignment. Never edit the main checkout
   `C:\Code Main\nitelos` or another task's worktree. Do not push, publish, or delete branches.
2. Stay inside the files/modules your assignment lists. If you need a change elsewhere — especially
   `pyproject.toml`, `uv.lock`, `.github/`, `tests/conftest.py`, or a public contract defined by an earlier task —
   STOP and report the exact needed change in your final report instead of making it.
3. Normative sources win: docs/planning 09 (scope), 03 (schemas/errors), 05 (evidence/policy), 07 (security),
   06 (evaluation), 04 (backends). If two normative requirements conflict, do not pick one silently: report
   the conflict, alternatives and impact. Routine choices inside the contract are yours.
4. Test first. Write the behavioral tests listed in the assignment, run them, and capture the meaningful
   failure (e.g. ImportError/AttributeError for a missing symbol is acceptable only for the very first run;
   then assertion failures). Then implement the minimum correct code.
5. Forbidden: simulated success, fabricated inference/metrics, xfail/skip to hide failures, TODOs on critical
   paths presented as done, swallowed exceptions, `except BaseException`, network in unit tests, mocks
   presented as model accuracy, changing expectations to fit wrong behavior, broad `type: ignore`
   (every ignore needs a code and reason), logging of raw values, `eval`/`exec`/subprocess in library code.
6. Code style: Python 3.12 syntax, strict mypy clean, Ruff lint+format clean, pure functions where the spec
   says pure, frozen/immutable models, safe `repr` (IDs/types/counts only), no hidden globals or caches,
   public docstrings stating authority, exceptions and limitations. Match the surrounding code; keep it small.
7. Before reporting, run in your worktree:
   `uv sync --frozen --group dev` (once), the task's verification command, the full offline suite
   `uv run pytest -q`, `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy`.
8. Commit your work on your task branch with message prefix `NIT-0XX:` and the trailer
   `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Several commits are fine.
9. Final report format (plain text, concise):
   - Task ID, branch, final commit SHA.
   - Files created/changed.
   - Tests written (IDs → test functions) and the observed initial failure.
   - Exact commands run and their final summary lines (pass/fail counts).
   - Acceptance criteria checklist with evidence per item.
   - Deviations, interpretations of ambiguous spec text, needed out-of-scope changes, open risks.
   Report facts only; if something could not be run, say so.
