# Requirements traceability and completion audit

Every committed feature has a task, observable test family and release gate. Proposed module paths are future files. Test IDs are defined in [testing](12-testing-and-ci.md) and expanded in [tickets](10-implementation-roadmap.md). G1–G8 are defined in [MVP scope](09-mvp-scope.md).

## MVP implementation traceability

| Requirement | Normative specification | Proposed modules | Tasks | Tests | Gates |
|---|---|---|---|---|---|
| MVP-01 Strict contract/status/decision | 03 | schemas, errors | NIT-002 | CON-01–04 | G1 |
| MVP-02 Evidence integrity/refs/limits | 03,05,07 | evidence | NIT-003 | EVD-01–04, SEC-05/06 | G1,G2 |
| MVP-03 Deterministic baseline | 04 | backends/deterministic | NIT-004 | DET-01–05 | G1 |
| MVP-04 Evidence scope and policy | 05 | policy | NIT-005 | POL-01–05, SEC-02 | G1,G2 |
| MVP-05 Sync/async SDK lifecycle | 02,03 | verifier, diagnostics | NIT-006 | SDK-01/02, LIFE-01/02, SEC-03/04 | G1,G2,G5 |
| MVP-06 Custom backend/capabilities | 04 | backends/base | NIT-007 | BAK-01–05 | G1,G2 |
| MVP-07 Actual local VLM | 04 | backends/smolvlm | NIT-008 | VLM-01–05, SEC-01/08, real smoke | G3,G6,G8 |
| MVP-08 Trace data integration | 03,11 | trace | NIT-009 | TRC-01–04 | G1,G2,G7 |
| MVP-09 Fifteen scenario families | 06 | authored benchmark/fixtures | NIT-010 | DATA-01–05, S01–S15 | G4,G6 |
| MVP-10 Metrics/reproducibility | 06 | evaluation | NIT-011/012 | MET-01–04, STAT-01, EVAL-01–04, SEC-07 | G4,G8 |
| MVP-11 Measured reports | 06 | reports and runner | NIT-013 | RUN-01/02 | G3,G4,G8 |
| MVP-12 Release/docs/package | 08,12,13 | package, docs, examples, CI | NIT-001/014/015 | PKG-01–03, DOC-01–04, REL-01–04 | G5,G6,G7 |

## Critical semantic and security traceability

| Invariant | Task/tests | Observable acceptance |
|---|---|---|
| Tool execution is not outcome | NIT-005/009, POL-05/TRC-03/S10 | Tool-completed evidence cannot satisfy external/visual criteria |
| Missing evidence is not task failure | NIT-004/005, DET-02/POL-03/S08 | Valid absent value => unknown; invalid supplied artifact => input_error |
| Model output cannot fabricate evidence | NIT-007, BAK-02/04/S14 | Foreign refs rejected, checked grounding cannot be self-asserted |
| External trust cannot come from JSON | NIT-005, SEC-02/POL-04 | Forged source or changed digest/subject/checkpoint never succeeds |
| Wrong identity/pending/stale state | NIT-005, POL-03/04/S05/S07 | Excluded evidence leaves unknown with exact reason |
| Contradiction and partial tasks | NIT-005, POL-01/02/S09/S15 | Same criterion contradiction unknown; independent refutation fails conjunction |
| No invented calibration | NIT-007/011, BAK-03/MET-03/04 | Calibrated claim rejected; missing score yields N/A, no threshold config |
| Errors reported separately | NIT-002/012, CON-01/EVAL-01 | Null decision on execution error; complete scheduled denominator |
| Local-first, no secret leakage | NIT-003/006/008, SEC-03/04/08 | No network/default download and no sentinel secret in outputs/logs |
| Resource/path defenses | NIT-003/012, SEC-05/06/07 | Oversized/deep/malformed/escaping input rejected before inference |
| Independent final evaluation | NIT-010/013, DATA-02/03/RUN-01 | Frozen lineage-separated split and no oracle in model context |
| MK-SH-V independence | NIT-001/015, PKG-01/REL-02 | Deterministic wheel works with no model; no MK-SH-V dependency/assets |

## Coverage of the assignment's 26 sections

| User section | Planning location | Disposition |
|---|---|---|
| 1 Identity/license | 00,01,08,13 | Identity fixed, availability observed, exact distribution rights release gate |
| 2 Motivation | 00,05,11 | Attempt/outcome distinction and offline demo |
| 3 Strategic objective | 00,09,13 | Small reliable SDK and defensible claims |
| 4 MK-SH-V relationship | 00,04,15 | Independent, future-only adapter, data isolation |
| 5 Research | 01 | Candidate and direct competitor ledger, dates/licenses/limits, realistic novelty |
| 6 Functional model | 03,05 | Precise minimum request and five legal result combinations |
| 7 Evidence/provenance | 03,05,07 | List, hashes/refs, source trust limits, no fabricated observations |
| 8 Backends | 04 | Deterministic/local committed; hosted/discrete planned; capability/error rules |
| 9 Policies/calibration | 05,06 | Fixed pure policy; fitting deferred with statistical design |
| 10 Integrations | 02,09,15 | SDK and trace MVP; no lifecycle migration; later adapters prioritized |
| 11 Security | 07 | Threats, controls, trust boundaries and SEC tests |
| 12 Evaluation | 06 | All 15 families, exact metrics, data/uncertainty/integrity protocol |
| 13 Architecture | 02,08,14 | Modules/stack choices and ADRs |
| 14 Public API | 03,11 | Typed fields, six pseudocode examples, limits/version/lifecycle |
| 15 Observability | 02,07 | Safe actual diagnostics, optional future OTel |
| 16 MVP | 09 | Fixed features/exclusions and measurable gates |
| 17 GLM strategy | 10,11 | Fifteen test-first tickets, dependency graph and reviews |
| 18 Quality | 08,12 | Packaging/locking/type/lint/tests/errors/security/release |
| 19 Documentation/adoption | 11,13 | Offline demo, exact docs and user integration feedback |
| 20 Future roadmap | 15 | Prioritized optional features and dependencies |
| 21 Risks/ADRs | 14 | Risk register and ten complete ADRs |
| 22 Output files | README index | All 18 requested Markdown documents |
| 23 Handoff quality | 10,11,16 | No conversation memory required, fixed interfaces and acceptance |
| 24 Self-review | 14 | Fifteen adversarial questions answered with revisions |
| 25 Final report/audit | 00,09,14,16 and final response | Architecture/scope/start/release/limitations summarized |
| 26 Planning-only process | This audit | Research and Markdown only; execution deferred |

## Material open issues and explicit owners

| Issue | Why not resolved by planning | Owner / consequence |
|---|---|---|
| Exact safe local dependency combination and CPU validity rate | No package install/model execution authorized | GLM NIT-008; AR-3 blocks model release if unsuccessful |
| Final asset/transitive wheel rights and advisories | Depends on resolved release artifacts and current advisories | Maintainer NIT-015; G6 blocks public release |
| Package name/publishing authority at release | 404 is not reservation or authentication | Maintainer NIT-015; choose alternative only by explicit decision |
| Real-world dataset rights and final audit | AgentHorizon rights unclear; screenshots can have third-party restrictions | Research maintainer; do not bundle; no real-world claim until cleared |
| Reviewer/hardware availability | Not supplied by task; cannot manufacture independent human audit or actual timings | Maintainer schedules AR gates and NIT-010 reviewers; report blocker if unavailable |

These are execution/release evidence gaps, not undefined core architectural choices. No routine preference question is needed to complete this plan.

## Planning completion audit

- Only Markdown documents under `docs/planning/` were created; no application README or source scaffolding was created.
- No application source or tests were written or modified; no packages installed; no model downloaded, trained or run.
- No implementation agent was invoked; no commit, push, deploy, publish or external message was performed.
- Existing workspace contained only `.git` at inspection, so no prior planning material required reconciliation.
- Research claims are linked to primary sources, with inaccessible/unclear material recorded. External implementations were not executed; no benchmark outcome is invented.
- Normative contracts, policy rules, limits, backend behavior and task dependencies were cross-checked. The adversarial review is recorded in document 14.
- Filesystem audit found exactly 18 planning Markdown files, no broken relative Markdown links, balanced fenced blocks, and only `docs/planning/` changes in Git status. All 15 task IDs have acceptance/test/DoD fields and an acyclic dependency order.
- Every MVP requirement maps to tests/tasks/gates above; GLM starts with NIT-001 and has explicit review/stop points.
- Planning completion does not mean release readiness. Actual compatibility, benchmark, licensing and human-review gates remain for the separate implementation phase.
