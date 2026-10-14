# Domain model and public API

**Normative contract v1**, package target 0.1.0. All examples are non-executable API specifications. This document and [policy semantics](05-evidence-and-policies.md) govern implementation. Types use Python terminology without supplying application code.

## Serialization and validation rules

Public models use Pydantic v2, strict validation, unknown fields forbidden, no coercion of strings to booleans/numbers, no NaN/infinity. JSON numbers distinguish bool from numeric values. Integers and floats compare numerically for assertion equality; `1` equals `1.0`, but neither equals `true`. Reject duplicate JSON object keys at ingestion. Timestamps are UTC RFC3339 strings with `Z`, parsed to timezone-aware UTC datetimes by the boundary parser; direct constructors accept aware datetimes only. ID strings match `[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}`. SHA-256 digests are lowercase 64-character hex strings. No implicit UUID conversion is required for caller IDs. Library-generated IDs use UUID4 strings.

All objects are frozen after validation; deep-copy mutable input containers into immutable internal values. Public serialization returns ordinary JSON objects/arrays. Ordering of criteria, evidence and findings is preserved. Canonical fingerprints use UTF-8 JSON with sorted keys, compact separators, no non-finite numbers, UTC timestamps, and original array order; document this as Nitelos canonical JSON v1, not a claim of RFC 8785 compliance. Hashes of image artifacts are over exact supplied bytes. Never hash a Python repr.

## Request

| Field | Type / default | Contract |
|---|---|---|
| `schema_version` | literal `"1"` | Required in wire JSON; constructor default `"1"` |
| `request_id` | ID | Required; caller's correlation identifier |
| `objective` | nonblank string | 1–4,096 characters; descriptive context, not a generated rubric |
| `checkpoint_id` | ID | Required; all decisive final observations belong here |
| `as_of` | UTC timestamp | Required; explicit observation cutoff, never substituted by wall clock |
| `criteria` | ordered Criterion list | 1–16, unique IDs, all required |
| `evidence` | ordered Evidence list | 0–128, unique IDs and unique sequence numbers |
| `metadata` | JSON object, `{}` | At most 8 KiB; not sent to models, not interpreted as authority |

No backend credentials, trust bindings or policy object are embedded in an untrusted request. They are configured on the verifier by its trusted caller. No objective-only auto-criterion generation in v0.1.

## Criteria: a discriminated union

Common fields: `id`, `description` (1–1,024 characters), `kind`, `scope`, `evidence_ids` (0–16 unique IDs), `subject` (nonempty map of string identity keys to string values, at most 16 pairs), `max_age_seconds` (integer 0–86,400, default 300). Subject is required, including for interface tasks, e.g. `{"form":"registration-1"}`. Different criteria may concern different subjects. A criterion describes a required final condition as of the request checkpoint. Dependencies and optional criteria are not in v0.1.

| Kind | Scope allowed | Additional fields |
|---|---|---|
| `assertion` | `observed_state`, `behavioral`, `external` | `pointer`: RFC 6901 JSON Pointer; `operator`: `equals`, `in`, `exists`; `expected`: JSON scalar for equals, 1–64 JSON scalars for in, absent for exists |
| `visual` | `visual` only | No expression or generated assertion; description states a single visually assessable criterion |

`subject` comparison is exact map equality, not substring matching. `exists` tests existence of the selected key/value even when the value is null. Absence of the path is UNKNOWN, including for exists: incomplete snapshots do not prove absence. To verify nonexistence, supply an explicit complete collector observation such as `{"record_exists":false}` and compare to false. No `not`, regex, numeric range, expression, arbitrary code, or JSONPath language. Split compound assertions into multiple criteria.

Empty `evidence_ids` is valid and results in missing-evidence abstention. A nonempty reference to an undeclared ID is `input_error/UNKNOWN_REFERENCE`; absence and corruption are distinct.

## Evidence

Every evidence item has:

| Field | Contract |
|---|---|
| `id`, `kind` | Unique ID and discriminant |
| `sequence` | Nonnegative integer; evidence list strictly ascending, gaps allowed; captured_at timestamps nondecreasing in this order (ties allowed) |
| `captured_at` | UTC timestamp, no later than `request.as_of` |
| `checkpoint_id` | ID; initial/history evidence may differ from final checkpoint |
| `source_id` | Collector identity label, not a proof of identity |
| `subject` | Exact identity map, same limits as criterion |
| `phase` | `final` or `pending`; required, no inferred default |
| `sha256` | Digest of artifact bytes or canonical payload; computed by SDK helpers, checked at verification |

Payload variants:

| Kind | Payload | Admissible use |
|---|---|---|
| `screenshot` | `artifact_id`, `media_type` (`image/png` or `image/jpeg`), `width`, `height` | Visual criterion; phase/checkpoint constraints still apply |
| `observation` | `channel`: `dom`, `accessibility`, `tool`, `external_api`, `database`, `human`; `data`: JSON object | Assertions; channel does not confer trust |
| `action` | `name` <=128 chars; `arguments`: JSON object; `reported_status`: `completed`, `failed`, `unknown`; `tool_result_id`: optional evidence ID | Behavioral criterion only, or untrusted visual context |

Action assertions view a JSON object containing name/arguments/reported_status/tool_result_id. A screenshot region is an `EvidenceRef` selecting a box, not a separate image copy. Raw HTML, accessibility trees, human prose and full tool logs are unsupported inputs; callers normalize relevant observations into JSON. Marking a DOM observation as external does not make it external confirmation. Human annotations are untrusted observations unless a future authenticated annotation integration is designed; v0.1 does not use them as external authority.

If present, `action.tool_result_id` must reference an observation with channel `tool` and a greater sequence number. Invalid target/type/order is `input_error/UNKNOWN_REFERENCE` with a safe field path. An action may have no tool result. The complete minimal Trace schema and conversion API are in document 11; all Evidence constraints here also apply to traces.

`EvidenceRef`: `evidence_id`, optional `pointer` for observations/actions, optional `bbox` for screenshots. Pointer and box are mutually exclusive. Bounding box is integer `(x0,y0,x1,y1)` in decoded pixels, upper-left origin, half-open right/bottom bounds; require `0 <= x0 < x1 <= width` and equivalent y constraint. `grounding` is one of `reference_validated`, `assertion_checked`, `model_inferred`. Reference validation proves existence/in-bounds only; it does not prove semantic grounding. Backend findings cannot claim `assertion_checked`; the core assigns it only after running a deterministic assertion.

## Artifact store and trusted context

`ArtifactStore` maps declared artifact IDs to immutable bytes. `ArtifactStore.from_bytes(id, bytes)` is a convenience specification; multiple artifacts use a mapping constructor. The core has no automatic file/URL resolver. Callers explicitly read their own files. Serialization of the request includes artifact descriptors, never bytes. Evaluation manifests use bounded relative files under a declared root and build the byte store separately.

`TrustBinding` is host-only configuration: `evidence_id`, `sha256`, `source_id`, `subject`, `checkpoint_id`. The host constructs it after independently authorizing and collecting external data; it is not read from trace JSON or model output. Binding source and digest prevents a forged item merely reusing an allowlisted source name. `external` criteria accept only observation channels `external_api` or `database` with a matching binding. Captured time/freshness and phase are still checked. Bindings attest what the host trusts; Nitelos supplies no cryptographic source-authentication claim.

`Verifier` configuration: optional `backend` (default `DeterministicBackend`), `policy` (default strict policy), tuple of trust bindings (default empty), and bounded artifact handling. Trust context is immutable for that verifier. Do not reuse a bound verifier for a different request's external artifacts; construct a new one. Built-in deterministic verification can run without optional dependencies.

## Findings and result

`BackendFinding` contains exactly `criterion_id`, `state` (`supported`, `refuted`, `unknown`), `evidence_refs` (0–16), optional `score`, and optional `rationale` (<=2,048 characters, model-reported and untrusted). Findings are backend claims. Every requested visual criterion must have exactly one finding. Unsupported/missing/duplicate IDs or illegal references are backend errors, not invented unknowns.

A supported/refuted visual finding must contain at least one reference to an eligible image actually provided to that inference. UNKNOWN may contain no references. Every returned reference must be a subset of that criterion's prepared evidence, not merely an ID elsewhere in the request. No pointer is allowed on a screenshot; no bounding box on structured data. Missing required support refs are `INVALID_EVIDENCE_REFERENCE`. These checks constrain attribution without establishing that the pixels support the claim.

`Score` fields: `kind` (`uncalibrated_score`, `uncalibrated_probability`, `calibrated_probability`), finite `value`, `target` (must name an event such as `criterion_satisfied`), `scale` (required for arbitrary score), optional `calibration_id`. Probability values are in [0,1]. Calibrated kind is reserved: v0.1 rejects it with `backend_error/UNSUPPORTED_CALIBRATION` because no calibration registry/validator is shipped. A capability flag alone cannot authorize it. Neither deterministic checks nor SmolVLM supply scores; they use null. Custom adapters may supply uncalibrated scores for reporting only; policy thresholds are unsupported in v0.1. No aggregate confidence field.

`CriterionResult` contains criterion ID, final state (`supported`, `refuted`, `unknown`), `basis` (`deterministic`, `model_inferred`, `none`), `scope`, validated evidence refs, ordered `reason_codes`, optional backend score, and `limitations` (e.g. `VISUAL_GROUNDING_UNVERIFIED`). A valid model reference is still model-inferred. There is no “verified” boolean on evidence.

`VerificationResult` fields:

| Field | Meaning |
|---|---|
| `schema_version`, `request_id`, `verification_id` | Schema and correlation |
| `execution_status` | `ok`, `input_error`, `backend_error` |
| `decision` | `success`, `failure`, `abstained` iff status is ok; null otherwise |
| `criteria` | Ordered CriterionResults; empty on input errors; completed partial results allowed on backend error, explicitly nonauthoritative |
| `reason_codes` | Deduplicated ordered machine codes; no hidden reason in free text |
| `error` | null iff status ok; otherwise `{code, safe_message, field_path?, retryable}` |
| `diagnostics` | Versions, fingerprints, duration, nullable measurements, limitations per architecture |

Legal state table: `(ok,success)`, `(ok,failure)`, `(ok,abstained)`, `(input_error,null)`, `(backend_error,null)` only. Error has a null decision even if some deterministic criteria already refuted the objective. This prioritizes faithful execution accounting over a partial-success shortcut. All criteria supported gives success; any refuted gives failure; otherwise abstained. Contradiction within one criterion becomes unknown, not refuted. See document 05 for order and admissibility.

### Exact diagnostics shape

`Diagnostics` contains `package_version`, `schema_version`, nullable `request_hash` and `evidence_manifest_hash`, `policy_id`, `policy_version`, `policy_hash`, `backend` (BackendDescriptor), `elapsed_ms` (finite nonnegative number), nullable `model_load_ms`, `criterion_durations_ms` (criterion-ID to finite nonnegative milliseconds), `omitted_context_ids` (ordered evidence IDs), `preprocessing` (ordered records described below), `measurements`, `limitations` (ordered codes). Request/verification IDs live in the result, not duplicated here. On input errors, fingerprints not safely computable are null; durations and configured policy/backend identity remain available. Do not hash arbitrary malformed input without limits.

`BackendDescriptor` exact fields: `id`, `version`, nullable `model_id`, `model_revision`, `prompt_hash`, `preprocessing_hash`, `runtime_lock_hash`. `measurements` has nullable `input_tokens`, `output_tokens`, `peak_rss_bytes`, `peak_device_bytes`, `cost_amount`, `cost_currency`, `cost_source`, `cost_as_of`, plus `unavailable_reasons` (field-name to code map). Tokens are nonnegative integers only when actually counted; cost_amount finite nonnegative; cost currency/source/as_of required together when amount is present. Built-in verification leaves memory/cost null; isolated evaluation may enrich the report, without altering the original result. Cost estimates require a report-level `cost_is_estimate` boolean, absent when cost is null.

`preprocessing` records contain `evidence_id`, `input_width`, `input_height`, `color_conversion` (`none`, `grayscale_to_rgb`, `rgba_on_white`), `processor_longest_edge` (1024 for shipped local adapter, otherwise null), and nullable `output_width`/`output_height`/`patch_count` when actually observable from the processor. Never invent tensor-to-image dimensions when the processor exposes only patches. Trace/assertion runs use an empty preprocessing list. Diagnostics must serialize without request text, subject maps, paths or payload values.

`CriterionResult` additionally records `evaluations`, an ordered list of `{evidence_ref, state, reason_codes}` for deterministic per-reference comparisons; visual results use an empty list. This makes conflicting observations inspectable without exposing values. Default result serialization omits rationale entirely; custom finding rationale can only be exported through an explicit unsafe-content option and must retain its model-reported label.

## Errors and abstention reasons

| Category | Codes | Behavior |
|---|---|---|
| Input | `INVALID_SCHEMA`, `UNSUPPORTED_SCHEMA`, `LIMIT_EXCEEDED`, `UNKNOWN_REFERENCE`, `DUPLICATE_ID`, `INVALID_SEQUENCE`, `INVALID_TIMESTAMP`, `INVALID_POINTER`, `INVALID_IMAGE`, `HASH_MISMATCH`, `MISSING_ARTIFACT`, `UNSUPPORTED_CAPABILITY`, `INVALID_POLICY`, `PATH_NOT_ALLOWED` | No backend inference; safe field path; retryable false |
| Backend | `DEPENDENCY_MISSING`, `MODEL_UNAVAILABLE`, `MODEL_LOAD_FAILED`, `INVALID_OUTPUT`, `INVALID_EVIDENCE_REFERENCE`, `UNSUPPORTED_CALIBRATION`, `RESOURCE_EXHAUSTED`, `TIMEOUT`, `BACKEND_EXCEPTION`, `BUSY`, `CLOSED` | Null decision; no fabricated finding; retryable only TIMEOUT/BUSY in v0.1 |
| Abstention / unknown | `MISSING_EVIDENCE`, `MISSING_VALUE`, `STALE_EVIDENCE`, `SUBJECT_MISMATCH`, `CHECKPOINT_MISMATCH`, `UNTRUSTED_EXTERNAL`, `PENDING_STATE`, `CONTRADICTORY_EVIDENCE`, `MODEL_UNCERTAIN`, `MODEL_INFERENCE_DISALLOWED` | Execution remains ok; no retries or automatic acquisition |
| Decision | `ALL_CRITERIA_SUPPORTED`, `CRITERION_REFUTED`, `INSUFFICIENT_EVIDENCE` | Result-level aggregate codes |

`verify(mapping_or_request, artifacts=...)` returns structured input errors for invalid mappings and runtime evidence. Direct Pydantic construction can raise its ValidationError before verification; expose `parse_request(mapping)` returning a request or raising documented `RequestValidationError` with safe fields. Do not include offending values in error messages. Misconfigured Verifier constructors raise `ConfigurationError`; invalid serialized policy is rejected before construction. No broad suppression of `BaseException`; KeyboardInterrupt/SystemExit/cancellation propagate. Other adapter exceptions become `BACKEND_EXCEPTION` without leaking exception text. Internal programmer bugs remain visible in tests through an explicit development-only re-raise setting, off by default and forbidden in release examples.

## Limits (hard ceilings, not automatic truncation)

At most 16 screenshots/request; 2 per visual criterion for the built-in SmolVLM adapter; 8 MiB encoded bytes/image, 32 MiB total images, 4,194,304 pixels/image, maximum side 4,096 pixels; PNG/JPEG only, single frame, no EXIF orientation other than absent/1. Reject orientation-bearing rotated images; caller normalizes explicitly. RGB/RGBA/grayscale accepted; alpha composited on white, grayscale converted to RGB as recorded preprocessing. Metadata is not model input.

JSON request maximum 1 MiB UTF-8 excluding image bytes; JSON nesting <=16; observation/action payload <=64 KiB each; at most 64 actions; metadata <=8 KiB. Model context has a further adapter-specific 2,048 text-token ceiling before image expansion and 4,096 total processor input tokens; no silent crop, truncation or image dropping. Output <=8 generated tokens per visual criterion. Limits may only be lowered in v0.1; raising ceilings requires contract review.

## API specifications: illustrative pseudocode

These sketches omit constructor syntax details but all field names and behavior above are fixed. String labels below are enum values. Do not run these blocks as programs.

### 1. Deterministic verification

```text
observation := Evidence.observation(id="form-state", sequence=0,
  captured_at=T, checkpoint_id="after-submit", source_id="app-collector",
  subject={form:"registration-1"}, phase="final", channel="dom",
  data={validation_error:true})               # helper computes payload digest
criterion := AssertionCriterion(id="no-errors", description="No validation error remains",
  scope="observed_state", evidence_ids=["form-state"], subject={form:"registration-1"},
  pointer="/validation_error", operator="equals", expected=false)
request := VerificationRequest(request_id="demo-1", objective="Complete registration",
  checkpoint_id="after-submit", as_of=T, criteria=[criterion], evidence=[observation])
with Verifier() as verifier:
  result := verifier.verify(request)
result.execution_status == "ok"; result.decision == "failure"
```

### 2. VLM verification

```text
artifacts := ArtifactStore.from_bytes("final-image", caller_read_bytes("final.png"))
shot := Evidence.screenshot(id="screen", artifact_id="final-image", bytes=artifacts["final-image"],
  sequence=0, captured_at=T, checkpoint_id="final", source_id="screen-collector",
  subject={form:"registration-1"}, phase="final")  # helper inspects MIME/dimensions/hash
criterion := VisualCriterion(id="appearance", description="The form shows a completion banner",
  scope="visual", evidence_ids=["screen"], subject={form:"registration-1"})
request := VerificationRequest(request_id="visual-1", objective="Show completed form",
  checkpoint_id="final", as_of=T, criteria=[criterion], evidence=[shot])
with Verifier(backend=SmolVLMBackend(model_dir=PREPROVISIONED_PATH, revision=PIN),
              policy=VerificationPolicy(allow_model_inference=true)) as verifier:
  result := verifier.verify(request, artifacts=artifacts)
if result.execution_status != "ok": handle_safe_error(result.error)
else if result.decision == "abstained": request_more_evidence_outside_nitelos()
else: read(result.decision, result.criteria[0].basis, result.criteria[0].limitations)
```

### 3. Screenshots and traces

```text
trace := parse_trace(caller_read_json("trace.json"))  # only schema-v1, never execute actions
request := trace.to_request(objective=GOAL, criteria=EXPLICIT_CRITERIA,
                            request_id=ID, checkpoint_id=FINAL, as_of=T)
result := await verifier.averify(request, artifacts=SUPPLIED_BYTES)
# Earlier frames/actions are context; only cited eligible evidence decides each criterion.
# A tool status "completed" cannot satisfy an external or visual criterion.
```

### 4. Batch evaluation / backend comparison

```text
manifest := load_evaluation_manifest("manifest.json", artifact_root=ROOT)
report := evaluate(manifest, verifier_factory=FACTORY, output_dir=NEW_RUN_DIR)
report2 := evaluate(the_same_manifest, verifier_factory=SECOND_FACTORY, output_dir=OTHER_DIR)
compare_reports(report, report2)  # reject differing evidence/policy/criterion fingerprints
# Evaluate sequentially; one result for every case; unknown outcome labels excluded only
# from binary correctness denominators and always disclosed.
```

### 5. Custom backend registration

```text
my_backend := instance implementing Backend:
  descriptor -> BackendDescriptor
  capabilities -> BackendCapabilities
  infer(prepared_visual_criterion, context) -> BackendFinding
  close() -> no value, idempotent
verifier := Verifier(backend=my_backend, policy=EXPLICIT_POLICY)
# Passing an instance is registration. No import string, entry point scan or global registry.
```

### 6. Future MK-SH-V (not v0.1)

```text
adapter := FutureStructuredDecisionBackend(
  transport=CALLER_CONFIGURED, model_id=RELEASED_ID, revision=RELEASED_PIN,
  option_mapping={done:"supported", not_done:"refuted", abstain:"unknown"})
# Validate actual task_done family, options and multimodal capabilities when released.
# Map native abstention; store probabilities as uncalibrated unless an independently
# validated calibration artifact matches model, preprocessing, policy and domain.
result := Verifier(backend=adapter, policy=EXPLICIT_POLICY).verify(request, artifacts=bytes)
```

## Versioning

Package follows SemVer with explicit 0.x instability notices; no breaking changes within 0.1 patch releases. Wire schema `1` is versioned independently. Reject unknown versions and unknown fields; do not silently ignore them. Export JSON Schema snapshots in the later implementation and test round trips. Public names listed here are supported; underscore/internal modules are not. A contract change requires ADR, migration notes, tests and author approval before implementation, even before 1.0.
