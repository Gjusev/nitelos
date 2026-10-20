# Changelog

All notable changes to nitelos are documented here. The format follows
[Keep a Changelog 1.1.0](https://keepachangelog.com/en/1.1.0/); versioning
follows [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Internal

- v0.2 planning: product and task plan ([docs/planning/17-v0.2-product-and-plan.md](docs/planning/17-v0.2-product-and-plan.md)) with proposed ADR-014/015/016 recorded in [docs/implementation/decisions.md](docs/implementation/decisions.md).
- Central v0.2 boundary tests BND-01..03 ([tests/test_boundaries.py](tests/test_boundaries.py)) and contributor-rule amendments ([docs/implementation/agent-rules.md](docs/implementation/agent-rules.md)).

No public interface changes yet.

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

- Evaluation results, with every denominator, are in [reports/v0.1/SUMMARY.md](reports/v0.1/SUMMARY.md): the deterministic path conformed on 120 of 120 authored synthetic cases; the experimental visual backend over-claims (unsafe acceptance 7 of 18). Final-test labels were audited by two independent AI reviewers plus adjudication; no human annotation audit was performed (ADR-013). No claim is made about real-world performance.
