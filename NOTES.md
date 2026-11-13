# Project 1B implementation notes — nitelos[langfuse] + nitelos-hooks (v0.3.0)

Branch `feature/langfuse-and-hooks`. Follows the recommended design in
[docs/planning/20-hooks-and-langfuse-research.md](docs/planning/20-hooks-and-langfuse-research.md).
All tests are offline: no live Langfuse, no Claude Code, no LLM, no network
(conftest denies sockets outside opt-in live markers).

## Done

- **`nitelos[langfuse]`** (`src/nitelos/integrations/langfuse.py`):
  - `record_verdict(result, trace_id, observation_id=None, *, client=None,
    name="nitelos_outcome", config_id=None)` — categorical score
    `success`/`failure`/`abstained`; `score_id` = the nitelos verification id
    (the API documents score `id` as an idempotency key); observation-level
    scores send BOTH `trace_id` and `observation_id`.
  - `ensure_score_config` — creates the config (`success=1/failure=0/abstained=-1`)
    when absent, tolerates raced creates, **never PATCHes**.
  - `evidence_comment` / `metadata_payload` — deterministic, bounded evidence
    references; values capped at 198 chars with an explicit `...[truncated]`
    marker; no raw evidence or page content (same privacy rule as the OTel
    export).
  - Backfill: `nitelos langfuse backfill --criterion FILE --since DATE
    [--dry-run] [--force]` — `GET /api/public/v2/observations` (fields groups,
    cursor pagination: only a missing `meta.cursor` ends iteration), rows
    grouped by `traceId`, one bounded evidence bundle per trace, re-verified
    through the real `Verifier` (host trust bindings, criteria from the
    criterion file), scores written per trace, counts printed per verdict,
    traces already carrying the score skipped unless `--force`. HTTP lives in
    `nitelos/collect/langfuse_api.py` — the only place network imports are
    allowed (boundary test BND-03).
- **`nitelos[hooks]`** (`src/nitelos/integrations/hooks/`): Codex Stop adapter,
  OpenCode observe-only adapter (generated V2 plugin + `observe` command),
  thin Claude Code delegate over the NIT-023 plugin, and
  `nitelos hooks install --harness … [--target FILE] [--force]` (prints the
  snippet by default; never overwrites an existing target without `--force`).
  Golden stdin fixtures per harness in `tests/fixtures/hooks/`.
- `nitelos.claude_code.load_criteria` — criteria now load from
  `.nitelos/criteria.json` (unchanged behavior) **or** `.nitelos/criteria.yaml`
  (lazy PyYAML import; JSON wins when both exist).
- `nitelos` console entry point added (previously only `nitelos-hook` and
  `python -m nitelos.cli` existed despite the v0.2 changelog claiming a
  `nitelos` script).
- Docs: README sections for both integrations; runnable offline demo
  `examples/claude_code_stop_hook/` (agent claims "tests pass", junit shows a
  failure, hook blocks with the failing test named — `bash run_demo.sh`,
  asserted by `test_hooks14`); CHANGELOG `0.3.0`; version bumped
  0.2.0rc1 → 0.3.0; dependency-license inventory extended for PyYAML and the
  langfuse SDK closure.

## Verification

- `uv run pytest -q` (offline): 825 passed, 22 skipped, 1 deselected
  (skips = extras not provisioned / opt-in live markers; the langfuse live
  test is skipped by default).
- `uv run ruff check src tests` and `ruff format --check`: clean.
- `uv run mypy` (strict): clean.

## Research open questions — resolved conservatively

- **Q1 (score `comment` size limit)** — none documented. Resolved by keeping
  the comment short and deterministic anyway (`_COMMENT_CAP = 480` with honest
  truncation); no reliance on undocumented limits.
- **Q2 (`create_score()` metadata)** — the documented SDK signature has no
  `metadata` parameter. Conservative resolution: evidence refs live in the
  comment; `record_verdict` inspects the client's signature at call time and
  sends the bounded `metadata_payload` **only** when the client accepts
  `metadata` (the API-level field). Documented in the module docstring and
  covered by LF-04.
- **Q3 (score-config mutability)** — conflicting docs (immutable vs PATCH
  endpoint). Resolved: `ensure_score_config` treats configs as immutable — it
  reads, creates only when absent, tolerates a raced create by re-reading, and
  never PATCHes; a drifted shared config is surfaced, not silently rewritten.
- **Q4 (categorical values in experiment item evaluators)** — out of scope for
  1B (the CI gate recipe is design item 5, deferred; see below). Unresolved
  empirically; does not block.
- **Q5 (experiment-action + SDK v5)** — deferred with the CI gate recipe; the
  extra accepts `langfuse>=4.6,<6` so either line installs.
- **Q6 (OpenCode plugin API generation)** — shipped the V2 plugin source (the
  documented current API) with the module path overridable via env
  (`NITELOS_OPENCODE_MODULE`); completion blocking remains impossible, so the
  adapter is observe-only by construction.
- **Q7 (Codex hook trust distribution)** — the installer's snippet prints the
  mandatory `/hooks` per-hash trust-review step and the continuation-prompt
  semantics. The exact `hooks.json` shape is best-effort against the documented
  file format and was not exercised against a live Codex; verify the shape on
  the then-current release before shipping guidance (also re-check the 600 s
  default timeout on `Stop`).
- **Q8 (OTel ingestion-version header)** — documentation item as the research
  predicted: the backfill docs note the up-to-15-minute freshness lag for
  exporters that do not send `x-langfuse-ingestion-version: 4`; nitelos never
  installs exporters.
- **Q9 (SDK v4 floor)** — the extra accepts `langfuse>=4.6,<6`
  (`create_score` unchanged v4→v5 per the research); the inventory notes the
  server floor (v5 SDK needs server ≥ 4.59.0).

## New open questions / deferred

- **Q10 (server-side `filter` shape for Observations API v2)** — the exact
  URL-encoded filter-column format was not verifiable offline; the backfill
  fetches pages and filters `name`/`since` **client-side**. If server-side
  filtering is confirmed later, push the predicate into the request to cut
  page volume.
- **Q11 (backfill criteria subjects)** — the backfill rewrites every criterion's
  `subject`/`evidence_ids` to the single per-trace evidence bundle; criteria
  files designed for the interactive hooks (specific collector evidence ids)
  need pointers that resolve against
  `/observations/<index>/metadata/...` to decide anything in backfill.
- **Q12 (Codex `hooks.json` shape)** — see Q7; needs one live Codex session to
  confirm before docs call it authoritative.
- **Deferred (research design item 5)**: the Langfuse experiment CI/CD gate
  recipe (numeric 1/0 item evaluations, success-rate run evaluator,
  `RegressionError`), SubagentStop wiring, and live-verified score-config
  bootstrap against a real project.

## Live-run rule (owner mandate)

Any future live LLM call must use the Z.ai Coding Plan endpoint — base URL
`https://api.z.ai/api/coding/paas/v4`, model **`glm-5.3-flash` only** (do not
offer or default to any other model), key via env var (e.g. `NITELOS_ZAI_KEY`;
Langfuse credentials stay separate). On a billing or endpoint error the code
must **stop and report** — never fall back to a pay-per-call provider. Offline
tests stay offline and need no key. The only live code shipped in 1B is the
opt-in Langfuse API test (no LLM involved).
