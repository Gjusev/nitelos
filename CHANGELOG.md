# Changelog

All notable changes to nitelos are documented here. The format follows
[Keep a Changelog 1.1.0](https://keepachangelog.com/en/1.1.0/); versioning
follows [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.3.0] - 2026-11-11

### Added

- Langfuse reporting extra (`nitelos[langfuse]`, Project 1B): `record_verdict`
  writes the categorical `nitelos_outcome` score (`success`/`failure`/`abstained`,
  enforced by an idempotently-created score config) per verification result —
  idempotent via the verification id as score id, observation-level scores pass
  both trace and observation ids, evidence references go in the comment (and in
  metadata only when the client supports it), never raw page content. Backfill
  CLI (`nitelos langfuse backfill --criterion FILE --since DATE [--dry-run]
  [--force]`) reads `nitelos.verify` spans via Observations API v2 (cursor
  pagination, client-side name/since filtering), re-verifies each trace where
  evidence is available (abstains where it is not), and prints counts per
  verdict; skips traces already carrying the score unless `--force`. The SDK
  and network imports stay lazy; offline tests run against fake clients and
  canned pages, with one opt-in live test behind `NITELOS_RUN_LANGFUSE_LIVE=1`.
- Hook adapters extra (`nitelos[hooks]`, Project 1B):
  `nitelos.integrations.hooks` — a Codex Stop-hook adapter (block = the reason
  becomes the auto-created continuation prompt; abstention logs and never
  blocks; `stop_hook_active` respected via the shared fingerprint loop guard;
  installer prints the mandatory `/hooks` trust step), an OpenCode
  observe-and-report adapter (no completion blocking exists; generated V2
  plugin reports at `session.idle`, optional `tool.execute.before` tool-call
  guard behind `NITELOS_OPENCODE_TOOL_GUARD`), a thin Claude Code delegate over
  the NIT-023 plugin (now also loading `.nitelos/criteria.yaml` when PyYAML is
  present), and `nitelos hooks install --harness claude-code|codex|opencode
  [--target FILE] [--force]` which never overwrites an existing config without
  `--force`. Golden stdin fixtures per harness in `tests/fixtures/hooks/`.
- `nitelos` console entry point (the CLI previously ran only via
  `python -m nitelos.cli`); `nitelos collect` behavior is unchanged.
- Runnable offline demo `examples/claude_code_stop_hook/`: an agent claiming
  "All tests pass." while the junit report shows a failure — the Stop hook
  blocks with the failing test named (`bash run_demo.sh`).

### Changed

- Version bumped 0.2.0rc1 → 0.3.0 (minor). Dependency/license inventory gained
  sections for the new `hooks` (PyYAML) and `langfuse` (SDK v5 line) extras.

### Research basis

- Design and open-question resolutions follow
  [docs/planning/20-hooks-and-langfuse-research.md](docs/planning/20-hooks-and-langfuse-research.md);
  the resolved questions (Q1–Q9) and their conservative answers are recorded in
  [NOTES.md](NOTES.md).

## [0.2.0rc1] - 2026-10-21

### Added

- Collector framework (`nitelos.collect`): read-only, bounded collectors whose errors become structured results so the verifier abstains instead of failing (NIT-017, ADR-014/015), with the `git`, `junit`, `github` and `http` collectors (NIT-018..021) and the shared hardened GET transport (NIT-020).
- Claude Code plugin (NIT-023): a Stop hook that verifies agent claims against collected evidence, turn-start records, a loop guard, `/nitelos:init` and `/nitelos:check` commands, and a marketplace-ready plugin manifest.
- Inspect AI scorer (NIT-024): verification as an Inspect `Score` (C/I/A) with `nitelos_accuracy` excluding abstention from the denominator.
- DeepEval metric (NIT-026): `NitelosOutcomeMetric` with a deterministic 1/0 score and distinct abstention and execution-error reasons.
- MCP server (NIT-027): `verify_outcome`, `collect` (host-pinned configs only) and `describe_criteria` over stdio.
- LangGraph node (NIT-025): `verify_outcome_node` writing a safe verification summary into graph state, with routing helpers and an interrupt pattern.
- Playwright page-state helper (NIT-022): read-only page capture (never drives the browser) producing one observation and one screenshot evidence item.
- OpenTelemetry export improvements (NIT-028): per-verification spans with allowlisted GenAI attributes and a traced-verify helper.
- Console entry points: `nitelos` (debug `collect` subcommand) and `nitelos-hook`.
- Pre-action gate (`nitelos.gate`, NIT-033): the act/ask decision math ported from gate-calibrated per ADR-017 (temperature scaling and logistic calibrators, conformal risk-controlled threshold, three policies); signals arrive as host-supplied numbers, the tier map is host configuration, irreversible actions always ask. Experimental research port: the source's negative result and assumptions ship in the docs.

### Changed

- README and documentation overhaul after the v0.1.0 tag: PyPI version and supported-Python badges, a README restructured around the user workflow, docs index (docs/README.md), expanded quickstart, brand assets and launch-film sources under videos/nitelos-launch, and the hosted explainer film linked from the README.

### Internal

- Repository hygiene (NIT-016): issue templates with verdict-reporting paths, repository description and topic plan, and repo-hygiene tests.

### Migration notes

v0.1 code keeps working on the v0.2 line. The public request and result
contract (`parse_request`, `Verifier.verify`, evidence and trace models) is
unchanged between `integration/v0.1` and `integration/v0.2`; the v0.2 work
adds modules (collectors, integrations, entry points) without altering the
existing surface. Verified by diffing the public API between the two
integration branches.

### Internal

- v0.2 planning: product and task plan ([docs/planning/17-v0.2-product-and-plan.md](docs/planning/17-v0.2-product-and-plan.md)) with proposed ADR-014/015/016 recorded in [docs/implementation/decisions.md](docs/implementation/decisions.md).
- Central v0.2 boundary tests BND-01..03 ([tests/test_boundaries.py](tests/test_boundaries.py)) and contributor-rule amendments ([docs/implementation/agent-rules.md](docs/implementation/agent-rules.md)).


## [0.1.0] - 2026-10-16

### Added

- Schema-1 request and result contract: strict parsing (`parse_request`, `parse_policy`, `parse_trace`), frozen models, five legal `execution_status`/`decision` pairs, safe validation errors with field paths.
- Deterministic assertion evaluation: RFC 6901 JSON pointers with the three fixed operators `equals`, `in`, `exists` over normalized observations and action views.
- Evidence integrity: SHA-256 digests over exact bytes and canonical JSON payloads, byte/depth/pixel ceilings, bounded single-frame PNG/JPEG decoding, artifact store.
- Host-built `TrustBinding`s for external criteria and the strict `VerificationPolicy` (model inference off by default).
- `Verifier` with synchronous `verify`, async `averify`, one-call-at-a-time lifecycle (`BUSY`/`CLOSED`), safe diagnostics and no network use.
- Schema-1 trace ingestion (`parse_trace`, `Trace.to_request`) with a bounded action-context window.
- Custom visual backend protocol: instance injection, capability preflight, validated findings (no self-asserted grounding, no calibrated scores).
- Experimental local visual backend: SmolVLM2-2.2B-Instruct pinned checkpoint, CPU/Linux, `local` extra, strict three-label parser, full error mapping. The originally pinned 500M checkpoint failed the executability gate (0/44 decisive labels) and that record is kept.
- Synthetic 120-case benchmark (15 scenario families, sealed freeze), sequential evaluation runner with run reports, and the RUN-01/02 report validator.
- Documentation (12 pages plus a caller collection recipe), offline examples, and CI for Linux/Windows on Python 3.12/3.13.

### Notes

- Evaluation results, with every denominator, are in [reports/v0.1/SUMMARY.md](reports/v0.1/SUMMARY.md): the deterministic path conformed on 120 of 120 authored synthetic cases; the experimental visual backend over-claims (decisive accuracy 26 of 38 in each split; unsafe acceptance 7 of 18 in each split). Final-test labels were audited by two independent AI reviewers plus adjudication; no human annotation audit was performed (ADR-013). No claim is made about real-world performance.

[Unreleased]: https://github.com/Gjusev/nitelos/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/Gjusev/nitelos/releases/tag/v0.1.0
