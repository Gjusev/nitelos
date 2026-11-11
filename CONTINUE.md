# CONTINUE — picking up Project 1B (nitelos[langfuse] + nitelos-hooks)

Status: implemented on branch `feature/langfuse-and-hooks` (v0.3.0), tests
green offline. See [NOTES.md](NOTES.md) for what is done, what is deferred, and
how each research open question (Q1–Q12) was resolved.

## Environment

- Python 3.12/3.13 via uv (`uv sync --group dev`; `uv run pytest -q`,
  `uv run ruff check src tests`, `uv run mypy`). No pip installs (PEP 668).
- Everything runs offline; the conftest denies network outside opt-in live
  markers (`github_live`, `langfuse_live`).

## Live-run rule (owner mandate — keep this in any continuation)

- Any code that makes live **LLM** calls must use the Z.ai Coding Plan as the
  endpoint: OpenAI-compatible base URL `https://api.z.ai/api/coding/paas/v4`,
  model **`glm-5.3-flash` ONLY** (pinned — do not offer, document, or default
  to any other model anywhere in code, README, this file, or docs), key via
  env var (e.g. `NITELOS_ZAI_KEY`; Langfuse-side credentials stay separate).
- On a billing/endpoint error: **STOP and report**. Never fall back to a
  pay-per-call provider.
- Offline tests stay offline and need no key.
- Current live surface: only the opt-in Langfuse API test
  (`NITELOS_RUN_LANGFUSE_LIVE=1` + `LANGFUSE_HOST`/`LANGFUSE_PUBLIC_KEY`/
  `LANGFUSE_SECRET_KEY`); it makes no LLM calls.

## Next steps (deferred from 1B)

1. Verify the Codex `hooks.json` shape and the `/hooks` trust flow against a
   live Codex release (NOTES Q12/Q7), and the OpenCode V2 plugin against a
   released OpenCode build.
2. Confirm the Observations API v2 server-side `filter` shape; move the
   backfill's client-side name/since filtering server-side (NOTES Q10).
3. Exercise `ensure_score_config` + `record_verdict` once against a real
   Langfuse project (`langfuse_live` marker).
4. Ship the CI gate recipe (research design item 5): experiment script with
   numeric 1/0 item evaluations, success-rate run evaluator, `RegressionError`
   gate; resolve NOTES Q4/Q5 empirically there.
5. SubagentStop wiring for Claude Code/Codex (explicitly out of 1B scope).
