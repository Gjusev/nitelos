# Implementation decisions and carried-forward requirements

Binding records from architectural reviews. Briefs for later tasks must include the items addressed to them.

## AR-1 (NIT-002 contracts) — 2026-10-14

Reviewer: nitelos-0f (independent of implementer nitelos-69). Verdict: APPROVE-WITH-CHANGES, no blockers.

Accepted interpretations (doc 03 ambiguity resolutions, not contract changes):
- Collection counts and byte/depth ceilings → `LIMIT_EXCEEDED`; scalar/string bounds and empty criteria list → `INVALID_SCHEMA`.
- `parse_request` reports only the first issue (deterministic doc-05 ordering); issue tuple shape leaves room for more.
- `action.tool_result_id` must reference a `tool`-channel observation with a strictly greater sequence.
- `exists` must omit `expected`; explicit `expected: null` is rejected; `equals` accepts `null`.
- Wire timestamps: RFC3339 with `Z`, at most 6 fractional digits.

Public names beyond the doc-11 inventory, accepted as deliberate v1 public API (additive; NIT-014 documents them):
- `canonical_json` (Nitelos canonical JSON v1, named in doc 03), the schema enums (Scope, Phase, Channel, …, LimitationCode) and `Issue`.
- Note for NIT-003: canonical JSON keeps `1` and `1.0` textually distinct, so their payload digests differ; document this.

JSON Schema snapshots (`tests/schemas/`) are a generated, non-exhaustive subset of the runtime contract, not a standalone validator.

Carried forward:
- **NIT-006 (binding):** `Verifier.verify` must re-check the request byte ceiling (1 MiB canonical), the metadata (8 KiB) and per-payload (64 KiB) ceilings, and nesting depth for typed requests that bypass `parse_request`, returning `input_error/LIMIT_EXCEEDED`. This needs acceptance tests on the typed-request path. It must also guarantee that `(ok, *)` results always carry one CriterionResult per request criterion (the schema permits an empty list).
- **NIT-003:** evidence factories return the concrete variants (the `Evidence` base is instantiable but cannot enter a request).
- **NIT-004:** reuse the RFC 6901 pointer grammar from `schemas.py` rather than a second implementation.

## NIT-003 review — 2026-10-14

Reviewer: nitelos-0f. Verdict: APPROVE-WITH-CHANGES. Accepted: factories perform header-level checks only; `prepare_evidence` is the full safety gate (decode of every store artifact). bbox OOB / bbox-on-structured → `INVALID_IMAGE`; pointer-on-screenshot → `INVALID_POINTER`. LA mode accepted as `rgba_on_white`. Artifact error paths use `$.artifacts[<id>]`.

Carried forward:
- **NIT-006 (binding):** `verify()` must call `prepare_evidence` unconditionally on every invocation, before any assertion or backend runs.
- **NIT-004/005/007:** `validate_evidence_ref` reports a generic `$.evidence_refs` path; callers re-path to the criterion position.

## NIT-011 reviews — 2026-10-15

Part A reviewer nitelos-69 (APPROVE-WITH-CHANGES, fixed); part B reviewer nitelos-69 (APPROVE, MET-01 recomputed by hand).
Accepted interpretations: cold/warm latency series contain ok executions only and the all-attempts series includes errors; nearest-rank percentiles (the even-length median is the lower middle); `calibrated_probability` is treated as a non-probability (no validated calibration in v0.1); conformance requires the full expected triple.

Carried forward to **NIT-012**:
- The manifest/oracle loader must validate the conformance expectation triples: an error status requires a null expected decision, and `ok` requires a decision.
- Cost, RAM/VRAM and throughput are run-level report fields, not CaseRecord fields. Unmeasured values stay null with a reason. Semantic grounding needs a human-audit protocol and is not automated.

## NIT-010 design (docs/implementation/nit-010-benchmark-design.md) — 2026-10-15

Author: nitelos-0f. The orchestrator accepted readings A1–A6:
- A1: 8 disjoint lineage groups per family (L1–L4 dev, L5–L8 final). S13 uses 4 pairs as grouping units.
- A2: four 60-case manifests (dev, dev-visual, test, test-visual).
- A3: the frozen benchmark's S14 cases are known-absent-content scenes. Fabricated-reference injection is covered by the NIT-007 BAK suite, not by a benchmark arm.
- A4: aHash 8×8, Hamming ≤ 6, as a detector only; hits go to human review and are never deleted automatically.
- A5: the visual-view `expected_decision` assumes a correct visual finding under strict policy plus the explicit opt-in configuration declared in the manifest.
- A6: the visual view keeps the external observations its external criteria need; S06 alone withholds them.
The deterministic dry run over the assertion view runs at NIT-010 implementation time, after NIT-006.
The design is an input to AR-4; any change after AR-4 creates synthetic-v2.
**Open (user decision):** staffing of the two independent human reviewers plus an adjudicator for all 60 final-test cases (estimated 6–8 person-hours). Agents cannot satisfy this gate.

## NIT-004 review — 2026-10-15

Reviewer: nitelos-0f. Verdict: APPROVE-WITH-CHANGES. Required: an over-long canonical array-index token (e.g. 5,000 digits) → out of range → unknown/MISSING_VALUE instead of a raw ValueError.
Accepted: "-", leading zeros and non-digit tokens on an array → INVALID_POINTER, decided at traversal time; -0.0 equals 0 (numeric equality); no Unicode normalization.
Carried forward to **NIT-006**: re-export `DeterministicBackend` at top level (an additive public name); `evaluate_assertion`/`evaluate_reference` stay in `nitelos.backends`.

## NIT-008 adapter design (docs/implementation/nit-008-adapter-design.md) — 2026-10-15

Author: nitelos-0f. The orchestrator accepted readings A1–A7:
- A1: the upstream `pad_token_id` warning is recorded, and the model config is never mutated.
- A2: a manifest digest mismatch is `MODEL_UNAVAILABLE`.
- A3: text tokens are counted with compact image markers; the total is `input_ids.shape[-1]`.
- A4: Windows is declared unvalidated for `local` until a recorded smoke run.
- A5: prompt template v1, including "Do not add punctuation", is fixed before any smoke result. The parser stays strict. Each dev-only iteration is logged in this file, and the template freezes before AR-4.
- A6: the cooperative deadline runs between generation steps; there is no hard-stop claim.
- A7: images are reconstructed from `PreparedImage.rgb`, with no second decode.
The initial validated combination is CPU float32 only.

## NIT-005 review — 2026-10-15

Reviewer: nitelos-0f. Verdict: APPROVE-WITH-CHANGES. No path to success was found under adversarial trust probes.
Accepted: no scope admits the `human` channel (citing it gives `UNSUPPORTED_CAPABILITY`); basis is NONE for empty or all-ineligible criteria; MISSING_EVIDENCE applies only to empty citations; ValueError is raised for a missing finding when eligible images exist (a programming-error guard).
Required: visual results carry the validated finding refs (model_inferred); a pure `eligible_evidence` helper is shared by the policy and NIT-006; `CriterionOutcome.ineligible` is immutable.

## NIT-012 runner design (docs/implementation/nit-012-runner-design.md) — 2026-10-15

Author: nitelos-0f. The orchestrator accepted readings A1–A7:
- A1: one oracle file per case, amending the NIT-010 layout.
- A2: the output directory must not exist.
- A3: an atomic COMPLETE marker signals a complete run.
- A4: manifests use extra=forbid, so trust-like fields are a hard error.
- A5: peak RSS is read via ru_maxrss on Linux and GetProcessMemoryInfo on Windows; null otherwise, and the baseline is not subtracted.
- A6: cases.jsonl is flushed after each case.
- A7: control exceptions are caught only at the CLI top level to write the incomplete state, then re-raised.

## ADR-011 — Nullable result `request_id` on unreadable input (user-approved 2026-10-15)

**Context:** Doc 02 (invocation lifecycle step 1) says to keep a valid caller request ID and otherwise use null. The doc 03 result schema (implemented in NIT-002) requires an ID string. NIT-006 initially used a placeholder `"unknown-request"`, which could collide with a real caller ID.
**Decision (user-approved):** `VerificationResult.request_id` is `ID | null`. Null is legal only when `execution_status == "input_error"` and no valid caller ID can be read from the input. A readable valid ID is always preserved. No placeholder IDs are used.
**Alternatives rejected:** a placeholder, because of collision risk and fabricated identity; raising instead of returning, because it contradicts structured input errors.
**Impact:** additive v1 wire change. The result snapshot is regenerated; CON-01 rules are extended (ok/backend_error require a non-null request_id); NIT-006 tests are updated. Migration: callers must treat `request_id` as optional on input errors.

## G4 human annotation

User decision 2026-10-15, updated 2026-10-15: the two independent reviewers and the adjudicator will be organized by the user AT THE END of all implementation work. Consequences, accepted by the user:
- G4, the final-test oracle audit, the final freeze hash and the final-test benchmark runs (NIT-013) wait for that human gate at the end; v0.1 cannot be declared ready before it.
- All work that does not depend on the frozen final split proceeds now: dev-split runs, the 12-case smoke set, prompt protocol on dev data only, docs, packaging.
- Review packets are prepared (benchmarks/synthetic_v1/review-packets/) and stay ready; the freeze tool refuses until sign-off is complete.

## AR-2 (deterministic slice NIT-002..006) — 2026-10-15

Reviewer: nitelos-0f (independent of implementer nitelos-69). Verdict: APPROVE, conditional on the NIT-006 fixes F1–F3 and the ADR-011 commit. End-to-end trust attacks through `verify()` found no path to a false success.
Accepted:
- BUSY takes precedence over CLOSED while a call is in flight.
- Async lifecycle tests run in a subprocess, because Windows asyncio's self-pipe uses loopback socketpair, which the socket-deny conftest blocks. The conftest is not weakened.
- A `NITELOS_DEV_RERAISE` env fallback is acceptable, provided its value parsing is strict.
Additive public name: limitation code `PARTIAL_RESULTS_NONAUTHORITATIVE`, placed in `diagnostics.limitations` on backend_error results that carry partial criteria.
Model integration (NIT-007/008) is authorized once the conditions are met.

## NIT-009 review — 2026-10-15

Reviewer: nitelos-3a. Verdict: APPROVE-WITH-CHANGES. Required: `Trace.to_request` must reject a naive `as_of` and normalize aware non-UTC values (it raised a raw TypeError).
Accepted: the parse-time `as_of` stand-in is `datetime.max` (only the captured_at ≤ as_of check consumes it, and the real check runs at `to_request`); model criteria are revalidated through the mapping validators; the recipe's code blocks are illustrative fragments.

## NIT-010 review — 2026-10-15

Reviewer: nitelos-3a. Verdict: APPROVE-WITH-CHANGES. Required before any human audit or freeze:
1. S11 outcome_truth must be `success` (it was hardcoded `failure`). A state→truth consistency test is added.
2. The visual-view compositions are corrected to the accepted design: S06 withholds the database observation; S07 v1 uses a visual criterion; S15 replaces its observed criterion with a visual one. A per-family composition test is added.
3. The group-index numeral is removed from renders. The orchestrator made this required as leakage hygiene, because in S04/S12/S15 the group determines the variant or truth.
Lesson recorded: the deterministic dry run validates decisions, not oracle truth labels and not visual-view composition; both now need their own tests.

## NIT-007 implementer decisions (pending review) — 2026-10-15

- Rationale export (an unsafe-content option) is deferred to NIT-012/014 reporting; v0.1 results carry no rationale field.
- Finding validation raises `BackendOutputError` (backend codes); the verifier converts it to backend_error. `validate_backend_finding` is public as the conformance helper for custom backends.
- `InferenceContext.deadline` is None until the NIT-008 adapter-level 120 s cooperative deadline.

## NIT-007 review — 2026-10-15

Reviewer: nitelos-f2 (independent of implementer). Verdict: APPROVE-WITH-CHANGES; no smuggling path found under adversarial probing of finding validation, preflight, isolation and lifecycle. All four implementer decisions accepted (see the NIT-007 implementer decisions section above; the reviewer read a worktree predating it).
F1 ruling (orchestrator): the `already_emitted` duplicate-criterion guard is kept as defense-in-depth for NIT-008 batch paths, and an explanatory test documenting why a duplicate is structurally impossible in the sequential verifier is required before merge.

## NIT-008 G3 attempt 1 — prompt v1 result and iteration ruling (2026-10-15)

Result (implementer nitelos-14, WSL Ubuntu CPU, torch 2.14.1+cpu/transformers 5.19.0, manifest-verified checkpoint a7da5b9, prompt_hash 08fde1e3…, lock 60381e31…): 0/11 valid labels. Every generation decoded to exactly ' UNKNOWN.' (leading space, trailing period) — byte-identical across all 11 diverse inputs. SMK-005 resolved by policy alone (ok/abstained, 69.8 ms, no model call) exactly as designed. Timings: load 1,754.8 ms; cold case 10,428.6 ms; warm mean 5,070.8 ms; wall 66.2 s; peak RSS ~3.2 GiB (ru_maxrss). Raw JSON: benchmarks/smoke-run-local-smoke-run.json on the NIT-008 branch. The strict parser correctly produced INVALID_OUTPUT for all 11 (design A5 holds; parser is normative and unchanged).

Orchestrator ruling — one pre-declared diagnostic/iteration round, dev smoke images only, candidates fixed BEFORE any run:
- v2: instruction-last format — the answer instruction appears as the final lines, verbatim: "Answer with the single word SUPPORTED, REFUTED or UNKNOWN. No other characters." (template text and hash logged before running).
- v3: completion suffix — prompt ends with "Answer:" after the labels list.
- D1/D2 diagnostics on smoke-01 with each template: a trivially-SUPPORTED criterion ("the screenshot contains any text at all") and a trivially-REFUTED one ("the screenshot shows a purple dinosaur"), to establish whether the checkpoint can emit any decisive label at all under the strict parser.
Decision rule, fixed in advance: if no candidate yields at least one valid decisive label (parser untouched), G3 is declared unreachable for this checkpoint; Nitelos escalates the doc-10 viability review to the user with options (delay v0.1, or release candidate with G3 recorded as a failed mandatory gate). No parser weakening, no model/preprocessing/max_new_tokens change, no mocks, ever.

## NIT-008 iteration round result — G3 declared unreachable (2026-10-15)

Executed exactly as ruled (candidates committed at acf9535 before any run; v2 hash 90c63743…, v3 hash f5633dc6…): all 44 generations — both templates, both trivially-answerable diagnostics D1/D2, and both full 11-case runs — decoded to exactly ' UNKNOWN.'. The checkpoint cannot emit ANY decisive label under the normative strict parser, invariant to prompt wording and criterion content. Per the fixed decision rule, G3 is unreachable for HuggingFaceTB/SmolVLM-500M-Instruct @ a7da5b9 on the declared CPU path. Mean ~4.6 s/case; peak RSS ~4.0 GiB; raw records: benchmarks/smoke-run-local-smoke-run.json and benchmarks/iteration-round.json on the NIT-008 branch. No parser weakening, no model or generation-parameter change, no mocks — the adapter implementation is complete; the gate is failed.
Follow-up diagnostic D3 (open captions, outside the verifier path) commissioned to distinguish choice-format instruction-following failure from a multimodal wiring defect before the user escalation.

## NIT-008 D3 diagnostic — wiring intact; choice-format compliance absent (2026-10-15)

D3 (open captions on smoke-01, outside the verifier path; records at benchmarks/d3-diagnostic.json, branch commit 98dd2a1): "Describe this image briefly." -> an accurate scene-specific description of the Export-complete fixture; "What is shown…" -> " Page showing export details." The image pipeline and scene comprehension work; the collapse is exclusively single-word three-label format compliance. Corollary recorded: even with the trailing period accepted, ' UNKNOWN.' is an abstention, and G3 requires a decisive label — no parser reading can reach G3 with this checkpoint. NIT-007 F1 explanatory test landed (2294091) and NIT-007 merged.
