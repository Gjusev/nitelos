# Changelog

All notable changes to nitelos are documented here. The format follows
[Keep a Changelog 1.1.0](https://keepachangelog.com/en/1.1.0/); versioning
follows [Semantic Versioning](https://semver.org/).

## [Unreleased]

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
