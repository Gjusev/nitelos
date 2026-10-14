# Risk register, architecture decisions and adversarial review

Planning baseline 2026-10-14. Likelihood/impact are qualitative design judgments, not measured frequencies. The release gates reduce implementation risk; they do not establish model reliability in arbitrary domains.

## Risk register

| Risk | Likelihood / impact | Detection | Mitigation | Residual uncertainty |
|---|---|---|---|---|
| False success | High / critical | S04/S06/S07/S10; FAR and insufficient-evidence acceptance | External scope binding, all-required criteria, strict policy default | Misdesigned criteria/lying collectors/model errors remain possible |
| False rejection | Medium / high | S01/S11, FRR and decisive-positive denominator | Explicit criteria, distinguish missing/pending from refuted | UI ambiguity and overly strict criteria can reject legitimate completion |
| Hallucinated evidence | High / high | Invalid refs and human semantic grounding audit | Reference validation, model-inferred basis, no new observations | Correctly addressed image citations can still be semantically wrong |
| Incorrect calibration | High if enabled / high | Score target/type tests, independent audit | No calibrated outputs/thresholds in v0.1; later fingerprint-bound calibration | Finite samples and shifts defeat broad guarantees |
| Dataset leakage | Medium / high | Group/hash overlap and experiment logs | Split by lineage, frozen test, no MK-SH-V final data | Foundation-model pretraining contamination unknown |
| Misleading benchmarks | High / high | Denominator/report checks, scenario tables | Errors separate, all scheduled cases, labeled evidence views | Synthetic results remain narrow; annotator bias possible |
| Provider/runtime incompatibility | Medium / high | Pinned actual integration smoke | One local adapter, lazy extras, tested compatibility lock | Native wheel/platform changes and upstream APIs evolve |
| Forged screenshots/DOM | High in hostile inputs / high | Digest/context checks, adversarial fixtures | State authority separate from pixels; trust host | Hash cannot prove original authenticity |
| Prompt injection | High / high | SEC-01 and model stress cases | No tools/authority, data-only prompt, strict output parser | Model label itself may still be manipulated |
| Privacy leakage | Medium / critical | Secret sentinel/log/wheel audits | Local-first, no raw logging/upload/persistence | Caller acquisition, memory and custom backend behavior remain outside control |
| Fragile integrations | Medium / medium | Trace conformance tests | Small SDK/schema, no trace archive parsing in MVP | Callers can normalize data incorrectly |
| Dependency bloat | Medium / medium | Core wheel/import/extras audit | Two core dependencies, isolated local/eval extras | Local Torch stack is still large |
| Excessive latency/resource use | High / medium | Actual CPU smoke and per-case measurements | Bounded images/tokens, sequential execution, optional local inference | Native kernels/loading may overrun cooperative deadline |
| Scope creep | High / high | Ticket/ADR diff review | Fixed MVP exclusions, no future auto-execution | User demand may justify later changes |
| Unreproducible research | Medium / high | Clean-run validation and manifest comparison | Pins/hashes/device/view/run records, no overwrite | Hardware determinism and external live sites not guaranteed |
| Unclear asset/license rights | Medium / high | Dependency/data inventory | Original fixtures; no third-party bundled data; rights gates | Model-training-data rights not exhaustively independently audited |
| Duplicating mature tools | High / medium | Competitor/use-case review | Prefer Inspect/BrowserGym/Universal Verifier integrations | Small SDK value hypothesis remains unvalidated |
| Caller trusts own agent's fabricated state | Medium / critical | Host integration review | Separate acquisition authority and digest-bound host configuration | An unsafe host can authorize false evidence; library cannot repair its trust root |

Top remaining release risks are false success, hallucinated visual judgment, insufficient model utility, evaluation leakage/misreporting, and rights/privacy gaps. They require different controls; no confidence threshold alone addresses them.

## ADR-001 — Modular single Python package

**Context:** Verification is a bounded library call, with no demonstrated need for independently deployed services.

**Decision:** One `src/nitelos` package with schemas, evidence, policy, backends and optional evaluation modules.

**Alternatives:** REST-first microservices; mandatory database; integrating the entire product into one existing agent orchestrator.

**Consequences:** Easy embedding and offline testing; callers retain lifecycle/storage ownership.

**Tradeoffs:** No centralized artifact management or scalable hosted scheduling. Optional inference dependencies remain large but isolated.

**Revisit conditions:** Measured multi-tenant deployment requirements or repeated cross-process integration demand, not speculative scale.

## ADR-002 — Separate execution status and verification decision

**Context:** Timeout, invalid input and evidence insufficiency have different meanings and metrics.

**Decision:** Three execution statuses, nullable three-way outcome; only five legal combinations.

**Alternatives:** Single five-value enum; booleans plus exception-only errors.

**Consequences:** Complete reports retain operational errors without claiming task failure; callers must inspect status first.

**Tradeoffs:** Slightly more verbose API; strict schema prevents contradictory combinations. Some partial conclusions are withheld when another backend operation fails.

**Revisit conditions:** Streaming/partial verification requirements; preserve distinction in any revision.

## ADR-003 — Structured evidence list and host-bound trust

**Context:** Provenance matters, but a hash or source label does not establish authenticity.

**Decision:** Ordered evidence list, hashes and typed references; runtime bindings match exact external evidence context. No graph or trust flag in imported JSON.

**Alternatives:** General evidence DAG; signed receipt infrastructure; allowlisted source name alone.

**Consequences:** Minimal auditable provenance; callers must provide authorized state collection.

**Tradeoffs:** No cryptographic attestation or provenance-chain verification. Exact trust binding imposes host integration work and cannot stop a malicious host.

**Revisit conditions:** Multiple derived artifact chains or signed observer receipts justify graph/receipt adapters; consider AgentVerify reuse first.

## ADR-004 — Fixed assertions and conjunctive policy

**Context:** Tasks need explicit criteria without a general workflow or policy programming language.

**Decision:** equals/in/exists on structured values; explicit evidence scope; all required criteria; contradiction becomes unknown.

**Alternatives:** Arbitrary Python predicates from config, JSONLogic/DSL, weighted criterion scores, majority vote.

**Consequences:** Deterministic behavior and small testable surface; task definitions may require normalized collector facts.

**Tradeoffs:** No temporal logic, numeric-range operators or automatic DOM selectors. Observed state is relative to collector accuracy.

**Revisit conditions:** Repeated concrete use cases cannot be expressed without unsafe caller workarounds; add only justified typed operators with tests.

## ADR-005 — Advisory visual inference with explicit opt-in

**Context:** A VLM can misread screens or invent success while producing syntactically valid references.

**Decision:** Visual criteria permit model-inferred support/refutation only with explicit policy opt-in; never external confirmation. Ref existence and semantic grounding stay distinct.

**Alternatives:** Treat any model citation as verified evidence; disallow all visual decisions until an independent pixel oracle exists.

**Consequences:** Visual path remains useful but its epistemic limitation is part of the result.

**Tradeoffs:** The framework cannot guarantee visual truth. Default strict policy abstains on supported visual inference paths unless opted in; a deterministic backend still reports unsupported visual capability.

**Revisit conditions:** Independently evaluated localization/grounding methods or deployment-specific evidence requirements, not a higher self-reported confidence.

## ADR-006 — SmolVLM as experimental local baseline

**Context:** v0.1 must have an actual vision backend without paid APIs or an unreleased checkpoint.

**Decision:** Pinned Apache-2.0 SmolVLM-500M, offline pre-provisioned CPU baseline, fixed short label parser, no training or quantization.

**Alternatives:** Hosted VLM only; larger Qwen family; MK-SH-V; multiple runtime formats.

**Consequences:** Independently executable path with modest model size, single integration to test. A genuine smoke run is a release gate.

**Tradeoffs:** GUI accuracy and strict-output compliance unknown until measured; CPU latency may be high. A tiny model is not automatically reliable.

**Revisit conditions:** Actual smoke/benchmark data shows unusable valid-output behavior or required capability absent. Replacement requires review and a new frozen baseline, never silent fallback.

## ADR-007 — No shipped calibrated confidence

**Context:** Models' verbal confidence and heterogeneous scores are not interchangeable probabilities; no dedicated calibration data exists.

**Decision:** Null scores in built-in backends, explicit uncalibrated types for custom outputs, reject calibrated claims in v0.1, defer fitting/threshold enforcement.

**Alternatives:** Hardcode 0.8 threshold, average model confidence, present softmax as calibrated.

**Consequences:** Scientifically honest API; risk-coverage curves/calibration metrics may be inapplicable for built-ins.

**Tradeoffs:** Less automated coverage/risk tuning at launch; future calibrated backend needs registry validation rather than only a capability flag.

**Revisit conditions:** Stable probability/logit-producing adapter plus disjoint calibration/selection/audit data and a reviewed statistical protocol.

## ADR-008 — SDK first, synchronous backend with async facade

**Context:** Core assertions and local Transformers are synchronous; no hosted adapter ships initially.

**Decision:** Sync protocol; one in-flight call per instance; bounded async facade; explicit resource ownership and cancellation limits.

**Alternatives:** Async-only native protocol; arbitrary concurrent calls; subprocess inference server.

**Consequences:** Simple caller API and no event-loop blocking; async cancellation does not imply native kernel termination.

**Tradeoffs:** Limited throughput and no hard timeout isolation. Native async hosted clients will require a compatible future extension or separate adapter runner.

**Revisit conditions:** Measured provider/batch use case; define migration without hiding lifecycle behavior.

## ADR-009 — Reuse ecosystem components, avoid full harness duplication

**Context:** Inspect, BrowserGym, Playwright, Universal Verifier and observability tools already cover large parts of the surrounding workflow.

**Decision:** Implement only small outcome contract/policy/evaluation accounting; integrate mature collectors/harnesses through adapters later. Do not reproduce browser actions, trajectory viewers or rubric generation.

**Alternatives:** Own agent lifecycle, full evaluation platform, new GUI benchmark infrastructure.

**Consequences:** Smaller scope, honest novelty framing, independent usability.

**Tradeoffs:** Users supply collection/normalization; standalone value relative to an Inspect scorer is still a hypothesis.

**Revisit conditions:** External developer feedback demonstrates no independent value; shrink to integration package rather than expand features for differentiation.

## ADR-010 — Reproducible authored fixtures before real-world claims

**Context:** Third-party trajectories have licensing/privacy issues; synthetic-only scores cannot establish generalization.

**Decision:** Authored deterministic conformance and 120-case synthetic benchmark; separately obtained real-world audit later, with clear evidence views and all scheduled errors counted.

**Alternatives:** Bundle public screenshots under presumed code license; claim universal accuracy from a small demo; require heavyweight OSWorld setup for core tests.

**Consequences:** Release possible without third-party assets; reports remain narrow and reproducible.

**Tradeoffs:** No initial real-world reliability claim. Authored fixture/test leakage remains a procedural risk and requires grouped freeze and reviewers.

**Revisit conditions:** Rights-cleared real-world data and an independent test protocol are available.

## Adversarial self-review

The following review was performed against this specification, not software. Revisions introduced by review are reflected in the normative documents.

| Skeptical question | Finding and resolution |
|---|---|
| 1. Rebuilding existing functionality? | Significant overlap found, especially Universal Verifier/AgentVerify. Novelty claim reduced to small contract/integration; orchestration, observers and viewers excluded. |
| 2. Works without paid API? | Yes by design: deterministic default and separately provisioned local model. Actual execution remains a release gate. |
| 3. Works without MK-SH-V? | Yes; no dependency or checkpoint assumption. |
| 4. Defensible confidence? | No builtin numerical confidence; calibrated claims rejected until validation infrastructure exists. |
| 5. Could it falsely claim external completion? | Unsafe host/collector remains a trust-root risk. Screenshot/model/trace alone cannot satisfy external criteria; runtime exact bindings added. |
| 6. Can hallucinations become fabricated evidence? | Model cannot add evidence IDs or checked grounding. Semantic hallucinations remain possible and explicitly model-inferred. |
| 7. Errors versus abstention? | Five-state invariant and complete error-aware metrics; invalid output is not an abstention. |
| 8. Security/privacy explicit? | No tool authority or network collector; local-first, bounded input, safe logs, runtime host trust. Custom Python adapters explicitly trusted code. |
| 9. MVP too complex? | Removed hosted adapters, general CLI, native Playwright adapter, calibration fitting, graph, server and persistent store. |
| 10. Independently reproducible? | Manifest/lock/model/processor pins and authored fixture recipes specified; cannot claim bitwise hardware-independent inference. |
| 11. Major choices left to GLM? | Core semantics, limits, model, parser, lifecycle, modules, tasks and gates fixed. Exact compatible dependency lock requires real execution, an explicit task. |
| 12. API examples consistent? | All use explicit criteria, artifact bytes and separate policy/backend; future MK-SH-V example clearly non-MVP pseudocode. Trace fields specified explicitly. |
| 13. Critical requirements linked to tests? | MVP and security/semantic requirements mapped in document 16; task tests are observable, not vague coverage demands. |
| 14. Correct dependency order? | Contracts precede evidence/policy/backend; data+metrics+model join before final reports; review checkpoints gate downstream work. |
| 15. Release without training? | Yes. Only released local weights are provisioned during implementation; no model training task exists. |

Review also resolved four subtle traps: missing JSON values are not negative proof; all-abstain scores have undefined selective risk; visually and structurally different evidence views cannot form a matched model leaderboard; async thread cancellation does not guarantee that a native model stopped. None of these limitations is hidden behind an optimistic release claim.
