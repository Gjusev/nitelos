# GLM 5.3 implementation handoff

You are implementing **Nitelos**, an Apache-2.0-targeted Python SDK that checks whether explicit agent success criteria are supported by supplied evidence. The tagline is **Verify the outcome, not the attempt.** This repository's planning documents are the complete baseline; no previous conversation is needed. This document instructs a separately authorized implementation phase. The planning author has not created an application, tests, dependency lock or benchmark results.

## Read before the first edit

Read [planning index](README.md), [executive summary](00-executive-summary.md), [exact MVP scope](09-mvp-scope.md), [contract](03-domain-model-and-api.md), [policy algorithm](05-evidence-and-policies.md), [architecture](02-system-architecture.md), [security](07-security-and-privacy.md), [roadmap](10-implementation-roadmap.md) and [test matrix](12-testing-and-ci.md). Consult [backends](04-verification-backends.md) before model work and [evaluation](06-evaluation-methodology.md) before any benchmark code. Research and ADRs explain the rationale, not an invitation to change fixed contracts silently.

**Start with NIT-001.** First write a packaging/import test that fails because the package does not exist. Establish the minimal src-layout package, core dependencies, lock and CI. Do not scaffold every planned module with fake successful methods. NIT-002 then defines the schemas, followed by architectural review AR-1. Deterministic verification is the first complete feature, before any VLM integration.

## Fixed architectural constraints

- The verifier receives immutable data; it never acts on the agent's behalf. No browser/network/database collector in v0.1.
- Explicit criteria are mandatory. Objective prose cannot silently generate conditions or change the policy.
- Execution status and decision are independent. `input_error`/`backend_error` always have null decision. Abstention is a successful execution with insufficient evidence.
- Evidence scope is explicit. Visual, behavioral, observed and external scopes cannot promote themselves into another scope.
- External confirmation requires runtime host trust bound to exact evidence ID/digest/source/subject/checkpoint. Imported JSON cannot authorize its own external claims.
- Deterministic assertions are three fixed JSON-pointer operators. No eval, callbacks from JSON, SQL or policy DSL.
- Every criterion is required; any admissible refutation fails the conjunction, all supported succeeds, otherwise abstain. Same-criterion contradiction => unknown.
- The model is advisory within a visual criterion. Strict policy defaults to disallowing model inference; opt-in remains model-inferred with unverified semantic grounding.
- One optional local model: pinned SmolVLM-500M. Its adapter generates only a strict three-label answer; no numerical confidence or fabricated evidence.
- Core is model-agnostic. No MK-SH-V code, checkpoints, datasets or experiment changes. Future adapters must use the existing protocol.
- Python SDK is the product; the evaluation module command is a bounded research utility. No general CLI/server/dashboard.

## Public API inventory

Expose these names from stable documented imports (prefer top-level for common types; optional backends under `nitelos.backends.smolvlm`): `VerificationRequest`, `AssertionCriterion`, `VisualCriterion`, `Evidence`, `EvidenceRef`, `ArtifactStore`, `VerificationPolicy`, `TrustBinding`, `VerificationResult`, `CriterionResult`, `Verifier`, `parse_request`, `RequestValidationError`, `ConfigurationError`. Evidence factories construct the discriminated variants with hashes/dimensions; they do not accept a `trusted` flag. Do not import the optional backend at top level.

Backend contract names: `Backend`, `BackendDescriptor`, `BackendCapabilities`, `BackendFinding`, `Score`. Custom backend injection is `Verifier(backend=instance)`, no global registry. Evaluation: `load_evaluation_manifest`, `evaluate`, `compare_reports`. No undocumented boolean `is_success` helper.

Factory signatures are specified conceptually in document 03. Preserve field names and defaults. Choose keyword-only optional configuration, typed overloads where needed, and explicit artifact stores. `Verifier.verify(request_or_mapping, *, artifacts=None)` and async `averify` are the supported invocation methods. No automatic model or backend choice from strings in evidence. `artifacts=None` acts as an empty store, so image-free assertions work simply.

## Trace schema-v1, exact minimum

`Trace` wire object fields: `schema_version` literal `1`; `evidence` ordered list of the same Evidence variants from document 03; `metadata` bounded JSON object default empty. No other fields, embedded artifact bytes, source trust, model config, policy, executable actions or oracle labels. `parse_trace(mapping_or_json_text)` validates duplicate keys/IDs, limits and schema; safe `RequestValidationError` on failure. `Trace.to_request(*, objective, criteria, request_id, checkpoint_id, as_of)` returns a VerificationRequest using the trace evidence and metadata. References/timestamps requiring request context are checked at to_request/verification. `action.tool_result_id` must refer to an observation of channel tool with a greater sequence number; pending action may omit it. Trace order is capture order; timestamps may tie, but must be nondecreasing. Request evidence uses the same nondecreasing timestamp rule. An initial screenshot is a screenshot with an earlier checkpoint ID; there is no special before/after wrapper.

Structured action arguments are accepted for audit but never transmitted to the shipped visual model. Model context selection is the documented last-eight action name/status view; record omitted IDs. This is not full trajectory comprehension. User-facing docs must state the two-image-per-criterion limit and bounded context.

## Error handling discipline

Map each error to document 03's taxonomy. A correct tool status is not task success. A missing value is unknown; a malformed artifact is input error; a malformed label is backend error; a valid UNKNOWN is abstention. Never return a default success on exception. Log only safe event IDs/codes, never values. Retain exception causality internally for controlled development diagnostics, but do not serialize original messages. Do not catch cancellation or process-control exceptions as normal failures.

One active verification per instance. Async facade uses a bounded worker and does not imply hard process isolation. Close is idempotent and waits for work to actually finish. Verify after close returns CLOSED. A local backend may cooperatively time out but cannot forcibly stop a stuck native kernel. Do not implement a fake hard-timeout guarantee using `asyncio.wait_for` alone.

## Test-first loop for every task

1. Confirm task inputs/dependencies and reviews complete. Record the task ID and expected files.
2. Write its specified failing behavioral tests. Capture the meaningful failure, not only a missing test dependency.
3. Implement the smallest vertical slice satisfying that behavior. Avoid broad scaffolding, unneeded classes and unrelated refactors.
4. Run the ticket command and dependency regressions. Fix failures before proceeding.
5. Run formatting, lint and strict type checks. Inspect for network access, logging leaks and contract drift.
6. Update the task log with changed files, commands/results, unresolved blockers and deviations. Do not fabricate checks you could not run.
7. At AR-1 through AR-5, submit the concrete artifacts for review. Approval is required for contract changes and these explicit checkpoints, not for every small coding choice.

If a task blocks on model provision/hardware, licensing or reviewer availability, report the precise missing input and continue only independent ready tasks. Do not declare a skipped integration test a passed release gate. Do not train a substitute model or use a paid API fallback.

## Coding standards

Python 3.12-compatible syntax; strict mypy on public/core code; bounded uses of Any only at external JSON/library boundaries, immediately validated. Public docstrings state authority, exceptions and limitations. Pure functions for policy/metrics; no hidden singleton, cache, network or global mutable configuration. Use tuples/immutable internal structures for prepared data; safe repr. Use pathlib only at caller-authorized evaluation/file boundaries. Context managers own resources. Optional dependencies are lazy and extras documented. No credentials in examples, environment files or fixtures.

For optional model APIs lacking usable stubs, isolate a small typed wrapper; avoid broad mypy ignores. Every ignore needs a code and reason. Never use tests that assert only that a mock returns what it was configured to return; test request construction, boundaries, normalization and policy impact. Tests must distinguish hallucinated semantic judgment from fabricated evidence reference.

## Demonstration definition

An original local registration fixture has a required email field empty and visible validation error. A stored synthetic agent summary says registration succeeded. The caller supplies `validation_error=true` in a normalized DOM observation. The no-error assertion expects false, so Nitelos returns ok/failure with the observation pointer. A second case supplies only an upload tool success for an external stored-file criterion; Nitelos returns ok/abstained. An optional visual example may judge the screenshot but clearly reports model inference. No demo claims that the library independently captured the DOM or verified a real account.

## Completion and prohibited expansion

All NIT tasks and G1–G8 evidence must be complete before a release recommendation. Package name availability and rights must be rechecked. Publishing requires maintainer authorization separately; do not commit/push/publish merely because this document describes release preparation. Stop after the agreed implementation phase. Future roadmap is not an automatic task queue.
