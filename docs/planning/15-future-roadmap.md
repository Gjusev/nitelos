# Optional future roadmap

This is a prioritized set of options, not committed scope or permission to start them. v0.1 release gates come first. Demand and measured failures determine the next increment.

| Priority | Capability | Impact / complexity | Dependencies and entry criteria | Explicit non-promise |
|---|---|---|---|---|
| P1 | Inspect scorer / caller Playwright helper | High adoption / low-medium | Stable schema, real user integration need, read-only collection tests | No agent lifecycle ownership |
| P1 | CUAVerifierBench local evaluator | High scientific value / medium | Rights/privacy review, original blind annotations, fixed evidence-view protocol | No full-benchmark reproduction claim from projected two-frame view |
| P1 | Additional stronger local VLM | Potential accuracy / medium | v0.1 negative results, permissive checkpoint, tested hardware and processor API | No presumed accuracy improvement |
| P1 | Explicit hosted OpenAI/Anthropic adapters | Broader comparisons / medium | Remote opt-in, exact protocol conformance, safe credentials, retry/cost tests | No automatic cloud fallback or paid dependency |
| P2 | Universal Verifier wrapper | High overlap reuse / medium | Upstream version/license review, result semantics and limits mapping | Do not duplicate rubric/context algorithms |
| P2 | Native async backend extension | Latency/concurrency / medium | Hosted demand, lifecycle ADR and compatibility migration | Async facade does not become hard isolation |
| P2 | Calibration fitting/registry and threshold policy | High reliability research / high | Stable probability target, independent data, audit-set power, fingerprint validation | No universal fixed-risk guarantee |
| P2 | Structured decision/System One adapter | Efficient finite decisions / medium | Published endpoint/schema, option mapping, true modality and abstention validation | No claim of a universal compatibility standard |
| P2 | MK-SH-V adapter | Author ecosystem evaluation / medium | Released checkpoint/license/interface, independent Nitelos data, no final-test contamination | No promised accuracy, calibration or availability date |
| P2 | Authorized external observer/receipt import | Stronger state assurance / medium-high | Host authorization, least privilege, fresh subject binding, investigate AgentVerify reuse | No mutation/remediation authority |
| P3 | Longer trajectories and temporal comparison | More tasks / high | Memory/context measurements, explicit selection/provenance, benchmark long-horizon audits | No silent summary/caption substitution for evidence |
| P3 | Multi-model disagreement | Failure detection / high | Comparable criteria/evidence, distinct model identities and costs | No naive score averaging or voting-as-calibration |
| P3 | Counterfactual benchmark generation | Better sensitivity studies / medium | Semantics-preserving irrelevant changes, rights-cleared rendering and pair auditing | Synthetic diversity is not real-world coverage |
| P3 | Native batching/performance profiling | Throughput / medium-high | Measured bottleneck, device memory bounds, batch independence tests | No speculative speedup numbers |
| P3 | OpenTelemetry/export integration | Production diagnostics / low-medium | Stable safe fields and evolving semantic convention pin | No default raw-content export |
| P4 | Trace inspection UI | Debugging / high | Users unable to use existing AgentLab/Langfuse/Playwright views | Prefer external viewers; no mandatory server/database |

## MK-SH-V integration isolation

MK-SH-V is independent approximately-260M-parameter research as described by the author, with intended image/text encoding, finite-option scoring, abstention and task_done family. These are intentions, not verified released capabilities. Do not access or change its training runs, synthetic/real-world protocols, calibration choices or final test examples as part of Nitelos.

When released, obtain a versioned adapter spec: modality limits, option identifiers/order, batch semantics, output normalization, probability target, abstention representation, device/runtime requirements and checkpoint/license hashes. Map to the existing normalized finding; do not turn null/abstain into failure. Validate probabilities separately from calibration evidence. Use disjoint Nitelos datasets with lineage records, disclose whether task-specific training occurred, and report negative results alongside other backends on matched evidence. Calibration trained for another domain does not automatically carry over.

## Roadmap governance

Each accepted feature receives a new numbered task, tests, scope decision and ADR amendment where it changes the contract. Reassess ecosystem reuse first. Full SaaS, training infrastructure, autonomous remediation and a replacement agent framework are not natural extensions of this project's purpose and should not be promised.
