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

## ADR-012 — Replace the pinned visual checkpoint with SmolVLM2-2.2B-Instruct (user-approved 2026-10-15)

**Context:** G3 is unreachable with HuggingFaceTB/SmolVLM-500M-Instruct @ a7da5b9: 0/44 generations ever produced a decisive label (all ' UNKNOWN.'), while D3 open captions prove the pipeline and scene comprehension work. The collapse is single-word choice-format compliance, and even with the trailing period accepted the output would remain an abstention — no parser reading reaches G3. The doc-10 viability review was escalated to the user.
**Decision (user option "Probar SmolVLM-2.2B"):** one swap attempt to **HuggingFaceTB/SmolVLM2-2.2B-Instruct @ 482adb537c021c86670beed01cd58990d01e72e4** (Apache-2.0; same Idefics3 architecture and processor pipeline; the 2.2B exists in the SmolVLM2 series — the original series shipped no 2.2B-Instruct). The 500M failure records stay in the repository as honest history. The smoke procedure, prompt protocol (v1 first), strict parser, preprocessing and all contract rules are unchanged; only the checkpoint and its manifest change. If the 2.2B also fails to produce ≥1 valid decisive label on the 12-case smoke set, Nitelos falls back automatically to the release-candidate-with-G3-failed path (no further model swaps without new user approval).
**Impact:** weights ~9 GB in two shards (orchestrator pre-provisions and verifies per-file SHA-256 against upstream LFS oids outside the repo); CPU float32 peak RSS projected ~12 GiB on the declared 32 GiB machine; per-case latency expected to rise several-fold — acceptable for dev smoke; benchmark runtimes are re-estimated at AR-3.

## NIT-008 phase B — G3 PASSED with the ADR-012 checkpoint (2026-10-15)

SmolVLM2-2.2B-Instruct @ 482adb5, UNCHANGED prompt v1 (hash 08fde1e3…), WSL Ubuntu CPU float32 (torch 2.14.1+cpu / transformers 5.19.0): 11/11 generations valid under the strict parser; 10 decisive SUPPORTED + 1 UNKNOWN abstention (SMK-002); SMK-005 policy-only (74 ms, no model call). Load 3,303.7 ms; cold case 52,490.4 ms; warm mean 28,294.9 ms; wall 363.7 s; peak RSS ≈ 9.9 GiB (ru_maxrss). Records: benchmarks/smoke-run-2.2B.json, d3-2.2B-sanity.json, compatibility report, all on nit/008-smolvlm @ f1140e3.
Orchestrator independent verification: mocked suite 374 passed + 1 deselected (Windows, local extra); the gated real-model integration test re-run by the orchestrator on WSL PASSED (63.7 s).
Honest accuracy observation (dev labels only, no tuning): smoke agreement 4/12; the 2.2B is format-compliant but over-supports (SUPPORTED on REFUTED-authored 004/007/009). Recorded as a model-judgment limitation for AR-3, the benchmark interpretation and all reporting; the executability gate is unaffected.
Dependency additions under the pre-authorization (both required by the processor chain, justified in-branch): torchvision 0.29.1+cpu (unguarded import in transformers 5.19 smolvlm image processor) and num2words 0.5.14 (SmolVLM2 processor requirement), plus their transitives; core/eval closures unchanged; core import stays torch-free.

## NIT-012 review — 2026-10-15

Reviewer: nitelos-14. Verdict: APPROVE-WITH-CHANGES. Adversarial probes (Linux): path-escape table extended, symlink chains, kill-mid-run semantics, collector-shape attacks, trust-fingerprint tampering — all held.
Required: wire the `--backend smolvlm` CLI factory to SmolVLMBackend now that NIT-008 has landed.
Orchestrator rulings on the info findings: (2) collector-shape errors are reclassified as configuration → exit 2 (doc 06 treats the fixture collector as trusted runner configuration); (4) capture the backend descriptor's preprocessing_hash in run.json and compare it in compare_reports together with the finding-1 wiring — required before any visual comparison is reported as matched; (3) the realpath→open TOCTOU window is recorded as a residual (host-local tampering out of doc-07 scope); future hardening via dir_fd-relative opens.

## AR-3 — APPROVED (2026-10-15)

Reviewer: nitelos-f2 (independent). Evidence authenticity confirmed from raw records (hashes recomputed live; the 12-case aggregates reproduce by counting rows; 500M-era history intact); prompt v1 byte-stable across all branch revisions; parser byte-identical across history; v2/v3 candidates match the pre-declared hashes committed before the round; torchvision confirmed as an unguarded module-level import in the installed transformers 5.19 smolvlm image processor (wheel source read); num2words confirmed as a construction-time requirement; dependency/licenses rows added by the reviewer on nit/015-release (548ac96); over-support observation reported, not tuned. NIT-008 merged into integration/v0.1 (375 passed + 1 deselected core/eval; Linux strict replay OK).
Recording notes: (N1) at the AR-4 docs pass, confirm installation.md's weight-provisioning wording names the manifest layout the adapter actually requires; (N2) release-checklist G3 row to be updated to DONE(PASSED) with the over-support observation attached by its owner.

## NIT-010 re-verification — APPROVED and merged (2026-10-15)

Reviewer: nitelos-14. The full 120-oracle state→truth table was rebuilt independently from design 4.1–4.15 with zero mismatches; S11 fixed systemically and pinned by a mechanical test; visual compositions verified structurally over every case; numeral removal spot-checked on regenerated renders (only labeled data values carry digits). Merged into integration/v0.1 (511 passed + 1 deselected; Linux strict replay OK). Final-test annotation and freeze remain PENDING the user-scheduled human gate (G4).

## NIT-014 review — 2026-10-15

Reviewer: nitelos-14 (ran the demos live; DOC-01..04 verified). Verdict: APPROVE-WITH-CHANGES.
Required at merge (docs were written pre-ADR-012 and must not suppress the pass): (a) "executability gate under review" → passed on the dev smoke set, with the honest accuracy observation attached and benchmark numbers still pending NIT-013; (b) pinned model id/revision updated everywhere to SmolVLM2-2.2B-Instruct @ 482adb5; (c) the visual demo actually wired (the stub's "wiring arrives with NIT-008" is now false) — finding 2 folded into the required update; (d) the tautological `or True` assert replaced by a real benchmark-number ban.
Windows-unsupported status for `local` stays (A4).

## NIT-013 part B (dev-split runs) and preflight ruling — 2026-10-15

Dev runs (WSL CPU, frozen local extra, manifest-verified 2.2B, final-test data untouched):
- dev.json deterministic: 60/60 ok, RUN-01/02 validated, dev-label agreement 60/60 exact.
- dev-visual.json: 60 scheduled → 30 ok (19 success / 10 abstain / 1 failure), 30 input_error/UNSUPPORTED_CAPABILITY, 20 model invocations; wall 491.4 s; cold 48.4 s; warm median 18.6 s; peak RSS 10.27 GB. Executed-case dev-label agreement 13/30; the over-support bias is confirmed and extended (S03/S14 failure→success; S12 abstain→success; S09 mixed). Reported, not tuned; no accuracy claim.

Preflight ruling (finding 1, orchestrator): doc 02 lifecycle step 5 — "Run assertion criteria in request order using the deterministic evaluator. Run visual criteria … using the explicitly supplied visual backend" — and doc 04's capability table (assertion criteria → "Core evaluator remains responsible" in every column) settle the interaction: assertion criteria are ALWAYS core-evaluated and NEVER consult backend capabilities. The NIT-007 preflight incorrectly checked every criterion kind against backend.criterion_kinds. Fix: the backend-kind preflight applies ONLY to visual criteria; assertion criteria are admissible with any backend and evaluated by the core evaluator; a visual criterion with a backend whose criterion_kinds lacks "visual" still gives input_error/UNSUPPORTED_CAPABILITY. DeterministicBackend declaring ("assertion",) and SmolVLMBackend ("visual",) remain truthful. After the fix, the dev-visual run is re-run and both records kept (the first documents the interaction, the re-run the corrected pipeline).

## Shared-backend mode and the preprocessing-probe defect — 2026-10-15

The runner's smolvlm path constructed one backend PER CASE (per-case lazy load ≈59 s + ~10 GB). Fixed by nit/shared-backend: evaluate(backend=...) shares ONE instance across per-case verifiers (bindings stay per-case), closed exactly once on every exit path; the CLI uses it; the temporary dev-visual driver is removed.
Latent defect found during wiring: the preprocessing-hash probe read a nonexistent public Verifier.backend attribute, so EVERY prior run.json recorded preprocessing_hash=null and compare_reports matched vacuously. Fixed with a read-only backend property. NOTE: the delivered dev-split records stand as run with preprocessing_hash=null (the hash is constant for the pinned checkpoint+prompt era, so no comparison was actually misled); the final runs record the real hash.

## AR-4 — APPROVED for protocol and inputs; final-oracle seal pending the human gate (2026-10-15)

Orchestrator approval of docs/implementation/ar-4-freeze.md (d357037). Independently recomputed and matched: prompt v1 hash (from the code constant), test.json / test-visual.json manifest digests, uv.lock digest; suite 590 passed.
Frozen now: prompt v1, strict parser + generation protocol, SmolVLM2-2.2B @ 482adb5 pin (per-file digests orchestrator-held outside the repo at C:\Code Main
itelos-models\*.sha256; WSL copies verified — no redistribution), preprocessing, both policy hashes, metric definitions, view definitions, runner/validator SHAs, deterministic grammar, lock 83a01dc0…, dev-split data as-used, and final-split INPUTS (label-independent). The preflight contract ruling is part of the frozen protocol.
Pending the G4 human gate: the 60 final-test oracle audits → adjudication → sign-off → final freeze hash; then the final runs per the dossier's plan. Any change to frozen items after this point is a new experiment (synthetic-v2).
Record fixes accepted: the stale dev-run lock hash corrected in the methodology; the final-run commands now reference the CLI shared-backend path only.

## ADR-013 — G4 final-test audit performed by agent reviewers (user-approved 2026-10-15)

**Context:** The plan requires two independent human reviewers for the 60 final-test oracles; the user scheduled humans "at the end" and then approved completing now with agent reviewers.
**Decision:** The G4 audit is performed by two agent reviewers independent of the fixture author (nitelos-f2 is excluded): reviewer 1 = nitelos-14 (knows the accepted design; not an author), reviewer 2 = a fresh no-prior-context agent. The orchestrator adjudicates disagreements; unresolved cases keep outcome_truth unknown and are reported. Reviewers judge ONLY from the review packets (objective, criteria, images, state, labels) — never the generator, the oracle-derivation code, other reviewers' output, or any model output.
**Labeling (binding):** every resulting artifact — data card, freeze record, benchmark reports, README/release notes — carries the explicit label "final-test labels audited by two independent AI reviewers plus adjudication; NO human annotation audit was performed", and human annotation review remains a precondition for any publication. The freeze sign-off fields record agent reviewer identities as such.
**Consequence accepted:** the G4 gate is satisfied for the release CANDIDATE under this user amendment; scientific caveat (AI reviewers may share biases the human audit was designed to catch) is disclosed in G8 reporting.
