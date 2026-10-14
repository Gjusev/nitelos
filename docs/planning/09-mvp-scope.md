# Exact v0.1 scope and release gates

v0.1 is a local-first Python verification SDK plus an evaluation utility. It must function without paid APIs, browsers, model weights or MK-SH-V on the deterministic path. The optional local visual path requires separately provisioned SmolVLM weights and the tested local extra.

## Committed requirements

| ID | Deliverable | Acceptance / owner task |
|---|---|---|
| MVP-01 | Strict schema-v1 request/result and two-dimensional outcome semantics | Only five legal status/decision pairs; round-trip and invalid-input tests; NIT-002 |
| MVP-02 | Artifact integrity and reference handling | All limits/hash/format/ref boundary cases pass; NIT-003 |
| MVP-03 | Deterministic fixed assertion operators | Exact JSON pointer/scalar semantics and no execution/network; NIT-004 |
| MVP-04 | Trust-aware pure policy | All conjunction/contradiction/freshness/subject/binding tables pass; NIT-005 |
| MVP-05 | SDK sync/async lifecycle | Default offline flow, busy/close/cancel behavior, safe errors; NIT-006 |
| MVP-06 | Custom backend protocol and validation | Malformed output cannot become success; NIT-007 |
| MVP-07 | One real local VLM adapter | Pinned offline model smoke run and full error reporting; NIT-008 |
| MVP-08 | Simple optional action trace ingestion | Schema-v1 only, no replay/tool execution; NIT-009 |
| MVP-09 | Authored fixture benchmark, 15 families | 120 cases with disjoint grouped dev/test and provenance; NIT-010 |
| MVP-10 | Error-aware offline evaluation and statistics | Hand-calculated metrics, immutable run record, complete scheduled denominators; NIT-011/012 |
| MVP-11 | Measured benchmark report | Actual model run, per-family results/limitations, no invented values; NIT-013 |
| MVP-12 | Demo, public docs, CI, packaging and licensing | Offline demo works from wheel, gates below, dependency/asset ledger complete; NIT-014/015 |

The local backend ships as **experimental**. The SDK/policy contract is the stable value proposition. No calibrated probabilities, generic fusion or universal reliability promise is included.

## Explicit exclusions

No hosted API adapter, general CLI, REST service, UI/dashboard, persistent artifact database, automatic redaction, data collection service, browser driver, actual Playwright adapter, native provider batch, ensemble, automated remediation, multi-agent coordination, training, fine-tuning, inference server, quantization conversion, distributed evaluation, evidence graph, complex policy language, calibration fitting/threshold enforcement, temporal logic, native System One/MK-SH-V adapter, or downloaded third-party datasets/weights in the package. A documentation recipe is not a maintained integration adapter.

## Critical path and cut policy

NIT-001 → 002 → 003 → 004 → 005 → 006 → 007 → 008 → 013 → 015 is the model-execution critical path. Fixture/trace and metrics branches join before NIT-013. See [full graph](10-implementation-roadmap.md). Do not cut trust binding, error distinctions, input limits, independent evidence typing or complete evaluation accounting to meet a date. If local inference fails, escalate backend viability; never replace it with mocked results. Optional integrations can wait indefinitely.

## Objective release gates

| Gate | Measurable condition |
|---|---|
| G1 Contract | 100% of designated conformance cases pass; schema snapshots and legal result matrix stable |
| G2 Trust/security | All SEC/POL negative cases pass, no false success from forged trust or invalid refs, no default network/raw logging |
| G3 Executable local path | Actual pinned CPU inference on 12-case smoke set; at least one valid decisive label; recorded failures/unknowns; reviewed compatibility manifest |
| G4 Reproducible evaluation | 120-case synthetic manifest; frozen 60-case final split; complete reports for deterministic configuration and local visual configuration, with evidence differences labeled; valid run fingerprints and all scheduled counts |
| G5 Quality | Core CI on Python 3.12/3.13 × Linux/Windows; lint/format/mypy pass; offline tests and sdist/wheel validation pass |
| G6 Rights and supply chain | Exact runtime/optional/transitive license inventory and notices reviewed; only authored fixtures redistributed; no unresolved high/critical reachable vulnerability |
| G7 Adoption documentation | Fresh-wheel offline incomplete-form demo succeeds, quickstart/error/scope/adapter/evaluation/privacy docs present; all public examples match contract |
| G8 Honest reporting | Per-family results, errors/abstentions/coverage, actual hardware/versions; no unsupported accuracy/calibration or real-world generalization claim |

G4 permits deterministic cases using assertions and visual cases using explicit visual criteria, but they must be separate views; these cannot be marketed as matched-model head-to-head scores. A matched comparison uses the identical visual request with two visual backends; v0.1 only ships one, so no fabricated matched competitive leaderboard is required.

Release is not declared in this planning session. G3, G4 and G6 depend on evidence that only implementation/release preparation can produce. No owner-specific deadline or hardware performance claim has been assumed.
