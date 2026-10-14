# Evidence and verification policy

This document is normative together with [domain contracts](03-domain-model-and-api.md). The policy is a small typed configuration and pure function, not a DSL. Every decision is conditional on explicit criteria, supplied evidence, collector assumptions and an observation cutoff.

## Provenance without false authenticity claims

Use a structured list and references, not a general evidence graph. Evidence ID identifies a capture event; artifact digest identifies bytes. Identical image bytes may occur in different events with different timestamps or subjects. Deduplicate decoded bytes internally by digest but preserve all event records. A digest detects later byte changes, not a forged original, mislabeled source, stale capture or manipulated screenshot.

The artifact store owns immutable bytes for a single invocation. Compute image hashes before decoding; compute observation/action hashes over canonical payload, with source/subject/time bound separately in the request fingerprint. Trust bindings include exact artifact digest plus context fields. Keep normalized preprocessing metadata in diagnostics; don't rewrite original evidence digests to hashes of resized tensors. Model-specific preprocessing is included in model fingerprint and evaluation comparability checks.

All references must resolve. Validate box bounds and pointer syntax; that validates a citation's address, not its semantic truth. Deterministic matching can establish what a supplied JSON value says. The local VLM can only supply an inference about pixels; it cannot create a new observation, source, identity binding or evidence ID. Model rationale is untrusted diagnostic text and excluded from policy logic. No model-generated region is treated as independently grounded.

## Policy configuration

`VerificationPolicy` v1 fields: `id` (default `strict`), `version` (literal `1`), `allow_model_inference` (default false). Other semantics are fixed in v0.1: all criteria required, contradiction becomes unknown, external binding required, temporal/subject checks enforced, unknown is not failure, and no confidence thresholds. Canonical policy hash includes every effective value. Caller cannot override trust via request metadata. Unknown config keys produce `INVALID_POLICY`.

The explicit visual opt-in authorizes a limited model-inferred decision on visual criteria. It does not upgrade grounding or establish external truth. Recommended high-impact tasks use external assertions; v0.1 does not infer a risk classification from objective prose. A human must choose criteria appropriate to consequences. No high-risk visual-only reliability claim is permitted.

## Eligibility and criterion algorithm

For each criterion, in this order:

1. Structural errors (unknown reference, broken artifact, malformed pointer, unsupported kind, invalid image/hash) fail input validation for the request. Do not reinterpret these as uncertainty.
2. Gather only explicitly cited evidence. An empty list gives UNKNOWN/MISSING_EVIDENCE. Extra evidence remains recorded but does not implicitly alter criteria.
3. Check type/channel: visual accepts screenshots; observed_state accepts `dom`, `accessibility`, `tool` observations; behavioral accepts actions or `tool` observations; external accepts only `external_api`/`database` observations. A referenced incompatible kind/channel is `input_error/UNSUPPORTED_CAPABILITY`, not a silent skip.
4. Check exact subject, exact request checkpoint, age `0 <= as_of-captured_at <= max_age_seconds`, and phase final. Nonmatching or pending items are ineligible with respective reason codes. There is no “newest wins” rule. A caller chooses final evidence IDs explicitly. All ineligible items are excluded; if none remain, unknown with all applicable codes. A future-dated item is an input error, not ineligible.
5. For external items also require host binding matching evidence ID, digest, source ID, subject, checkpoint. No matching binding => ineligible/UNTRUSTED_EXTERNAL. A stale bound item is still ineligible. Mere success text, an HTTP 200, or an agent-provided trust flag never satisfies this step.
6. Assertion: evaluate each remaining value at the pointer. Equal/member/present => supported; present unequal/not-member => refuted; missing/non-scalar where scalar required => unknown. If there is at least one supported and one refuted observation, criterion unknown/CONTRADICTORY_EVIDENCE. Otherwise any refuted => refuted; otherwise any supported => supported; otherwise unknown/MISSING_VALUE. Unknown observations alone do not negate decisive, eligible observations. Return all examined references and a per-reference evaluation diagnostic; do not hide contradictory evidence.
7. Visual: if policy disallows model inference, unknown/MODEL_INFERENCE_DISALLOWED with no model call. If permitted, send all eligible cited images to the selected backend; validate its finding. UNKNOWN => MODEL_UNCERTAIN. Supported/refuted are accepted only as `basis=model_inferred`, with `VISUAL_GROUNDING_UNVERIFIED`. The VLM is asked to detect contradictions across its images, but the framework cannot guarantee semantic contradiction detection. This residual limitation must be visible. Mixed screenshot states are not deterministically fused.

All declared visual criteria are capability-checked regardless of policy gating. Model input token preflight occurs for the criteria that would actually invoke the model. No hard assertion says screenshots corroborate external data: visual and external criteria remain separate requirements.

Reason ordering is deterministic: process cited evidence in `evidence_ids` order, checking subject, checkpoint, freshness, phase and external binding in that order; collect all applicable ineligibility reasons and deduplicate preserving first occurrence. Append comparison/model reasons next. Result-level reasons start with the aggregate code and then include criterion reasons in criterion order, deduplicated. For supported/refuted results, ineligible extra cited observations may remain in reasons/diagnostics without changing the decisive state. Input validation returns the first error by request field order as specified in document 03, then criterion order, then evidence order; tests must not depend on third-party exception ordering.

## Aggregation truth table

| Criterion results across all required criteria | Overall decision |
|---|---|
| All supported | success |
| At least one refuted, others any state | failure |
| No refuted, at least one unknown | abstained |
| Any execution input/backend error | decision null; execution status carries error |

This is conjunction, not majority vote or probability fusion. A contradictory criterion becomes unknown; a different independently refuted required criterion still proves the conjunction false. Success does not imply every supplied artifact was informative; it means every explicit criterion was supported by admissible evidence.

## Required examples and edge cases

| Situation | Criteria and result |
|---|---|
| Tool reports upload succeeded; no external snapshot | External stored-file criterion => abstained |
| Page says payment successful; trusted ledger says pending | External criterion excludes pending ledger => abstained, even with visual support |
| Ledger final status failed; screenshot says successful | External criterion refuted => failure; visual criterion may separately support appearance |
| Wrong customer on confirmation page | Subject mismatch => unknown; explicit trusted `customer_id` unequal assertion => failure |
| Two trusted final observations disagree at same checkpoint | Criterion unknown/CONTRADICTORY_EVIDENCE; never accept based on source count |
| Old failure then new success in a trajectory | Cite the final checkpoint for outcome. History is not automatically contradictory final evidence |
| Final field `validation_error=true`, agent summary “done” | No-error assertion refuted; summary cannot override it |
| Evidence phase pending with status false | Unknown, not failure: state may still settle |
| Missing screenshot item omitted completely | Missing cited evidence list yields unknown; dangling nonempty ref is input error |
| Supplied screenshot file bytes truncated | INVALID_IMAGE, not model abstention |
| Visual backend emits unknown evidence ID | INVALID_EVIDENCE_REFERENCE backend error |
| All tool calls completed, behavior-only criterion succeeds | Scope explicitly behavioral; documentation must not call this external outcome proof |

Multi-step tasks are represented by explicit final predicates, e.g. saved artifact exists AND correct record ID AND required final status. In v0.1 there is no temporal logic or proof that every intermediate action occurred. A criterion with historical procedural requirements is unsupported unless formulated as an explicit behavioral observation at the checkpoint. No multi-model disagreement mechanism ships; future independent findings must retain model identity and cannot be averaged without justification.

## Missing evidence versus real-world failure

Truth can be false while evidence cannot establish it. A hidden backend failure with only a plausible screenshot should abstain under an external criterion. An oracle label does not give the verifier permission to guess. A loading screenshot may support a criterion explicitly about loading, but cannot establish completion if the required final evidence is pending. State collectors must mark finality correctly; Nitelos cannot discover false metadata from a digest.

## Calibration plan, deliberately not a v0.1 guarantee

Reserve explicit score types and collect error-aware metrics. Shipped backends expose no numerical confidence, and v0.1 has no threshold setting or calibration fitting. This avoids giving arbitrary generated confidence scientific status.

Future calibration uses stable logits/probabilities, disjoint fitting and threshold-selection data, frozen model/prompt/preprocessing/evidence view, and a registry binding all fingerprints. Temperature scaling is appropriate for finite-option logits; it is not a method for turning a free-text confidence assertion into ground truth. Threshold selection should optimize specified coverage subject to observed risk constraints, with an independent audit set. Shift invalidates any unconditional interpretation. Detailed formulas and uncertainty requirements are in [evaluation methodology](06-evaluation-methodology.md).

Policy tests use literal hand-calculated tables, including all three-valued conjunction combinations and contradiction precedence. Policy version changes require new tests, benchmark manifests and an ADR; changing a policy on the test set is a new experiment, not a corrected old result.
