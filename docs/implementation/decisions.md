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
