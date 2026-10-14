# Evaluation methodology

Evaluate the verifier, not the acting agent. A run fixes objective, criteria, evidence view, policy and oracle before comparing backends. Required implementation tasks: NIT-010 through NIT-013. No benchmark results exist yet.

## Three separate evaluation products

1. **Contract conformance suite:** hand-authored deterministic cases with exact expected errors, decisions and references. Required to pass 100%. Includes malformed inputs and mocked model outputs. It establishes implementation correctness, not VLM accuracy.
2. **Synthetic outcome benchmark v1:** 120 cases, 15 families × 8 cases. Each family has four development and four final-test cases from different template/entity groups. Outcome labels and evidence sufficiency are distinct. Layouts, strings, entity values and generation seeds differ by group; pairs stay together. Freeze generation specification and manifest before final evaluation. Synthetic results are labeled synthetic throughout.
3. **Real-world audit:** later separately obtained CUAVerifierBench subset, and AgentHorizon only after license permission. Prefer all eligible cases under a predeclared rule; do not cherry-pick examples that suit the local model. v0.1 release does not depend on third-party permissions, and must make no real-world generalization claim without this audit. A two-image projection is a new derived evidence-view experiment, not reproduction of a full-trajectory benchmark.

The local executable smoke set has 12 fixed development images spanning readable success/failure, pending, missing-context and injection cases. Its purpose is interface/hardware testing. It is not a final accuracy benchmark. At least one non-abstained valid output is an adapter-execution requirement, not a performance claim.

Smoke fixtures are authored in NIT-008 and are separate from the 120 benchmark cases produced in NIT-010; this avoids a task dependency cycle. Cases are specified in document 04. Each benchmark case has two declared request views: an assertion view using normalized supplied observations, and a visual view replacing only visually assessable interface criteria with visual criteria and the corresponding screenshot references. **External criteria remain external in both views**; neither view gives the verifier hidden oracle state. Behavioral criteria stay behavioral. Both views are scheduled on all 120 cases, split 60/60, and results are reported separately. If a case has no visual criterion, the selected visual backend is simply unused and diagnostics record that; do not count it toward model-inference accuracy. Model-specific reporting includes the number of actual model invocations.

## Required scenario matrix

| Family | Oracle source | Evidence-view expectation | Mandatory behavioral check |
|---|---|---|---|
| S01 Clear completion | Fixture final state | Sufficient visible or structured final state | Supported criteria can succeed |
| S02 Clear failure | Fixture rejected state | Explicit final error | Failure rather than “tool succeeded” |
| S03 Incomplete form | Required-field state | Error/empty mandatory field | Refute no-error assertion |
| S04 Misleading success screen | Independent backend fixture | UI says success, external absent/false | External missing abstains; false refutes |
| S05 Loading/pending | State machine checkpoint | Pending is explicitly nonfinal | Unknown, never infer settled outcome |
| S06 Hidden backend failure | Backend fixture oracle withheld from image view | Visually indistinguishable success/failure | External criterion abstains on image-only view |
| S07 Wrong user/object | Exact fixture subject and record ID | Confirmation for different identity | Reject subject mismatch / refute explicit wrong ID |
| S08 Missing visual evidence | Oracle plus empty evidence view | Insufficient | Abstain; corrupt declared file is separately input error |
| S09 Contradictory evidence | Conflicting final snapshots | Contradiction visible in structured values | Unknown for same criterion |
| S10 Tool success, task failure | Action completed + final error | Both evidence types supplied | Behavior cannot override required final state |
| S11 Task success, misleading summary | Confirmed final state + false summary | Independent evidence sufficient | Summary cannot veto authoritative assertion |
| S12 Ambiguity | Two human annotators / fixture ambiguity | Illegible, cropped or underspecified evidence | Unknown expectation, not forced binary label |
| S13 Counterfactual image changes | Paired fixture render state | One task-relevant value changed | Measure paired label sensitivity; also irrelevant-edit invariance |
| S14 Model hallucinations | Known absent UI content; mock fabricated ref | Valid address does not prove grounding | Fabricated ref => backend error; wrong inference => model error |
| S15 Multi-step trajectories | Final conjunction of fixture predicates | History plus required final checkpoint | Earlier apparent success cannot substitute for missing final predicate |

At least two cases per family exercise external vs visual/observed scope where applicable; all scope labels appear in reports. S13 pairs and shared scene variants are grouping units. Scenarios overlap; designate one primary family and optional secondary tags, never count duplicate cases as independent samples.

## Ground truth and annotation

Each case has `outcome_truth` = success/failure/unknown, independent `evidence_sufficiency` = sufficient/insufficient/contradictory, `expected_decision` for policy conformance where determinable, oracle source ID, rationale, annotator IDs, and scope. Hidden oracle state is never included in the prepared backend context. A case with unknowable real-world outcome has truth unknown; do not convert it into a negative. A known failure with insufficient evidence still expects abstention in the conformance view.

For authored fixtures, the state machine and renderer derive from one declared fixture seed; an independently written oracle reads state, not the screenshot caption. Review that the rendering matches state. Use two independent human reviewers for all final-test cases and for real-world annotations. Reviewers see objectives, criteria and necessary oracle evidence but no candidate model output. Disagreements are adjudicated; unresolved cases retain unknown and are reported. Record agreement rate and a confusion table; Cohen's kappa is optional with class prevalence caveats. Dataset contributor asserts rights and absence of real credentials/PII.

Use neutral filenames and UUID-like case IDs; do not expose labels through paths, scenario names, alternate text or metadata. Image pixels may naturally contain status words. Backend sees only requested evidence and objective/criteria. Split and oracle metadata remain runner-side. Benchmark author may know labels; implementation agent must not inspect final labels during tuning. Public labels cannot be made cryptographically secret after release: procedural discipline and immutable experiment logs are the controls.

## Splits and leakage controls

- No training split is needed for v0.1 because no model is trained. Development data is used for prompts and engineering; calibration is empty/not fitted; final-test is independently frozen.
- Future model training must introduce disjoint train, development, calibration-fit, threshold-selection, audit, and final-test groups. For tiny data, use a clearly labeled exploratory study rather than pretend every split is statistically adequate.
- Group by source task, base trajectory, template lineage, application/domain, user/entity and counterfactual siblings. For AgentHorizon, instruction/steps sibling lineage is required, not just UUID disjointness.
- Deduplicate exact SHA-256 and perceptual near-duplicates with human review in dataset preparation; record algorithm/version/threshold. Do not delete examples after seeing candidate errors. Predefine any exclusions.
- Keep domain-shift groups (unseen site layouts, languages, resolution, error style) separate from in-domain reports. Public benchmark contamination in foundation-model pretraining cannot be ruled out; disclose it.
- MK-SH-V final tests and training-protocol assets must never enter Nitelos iterative fixtures. Require independent data lineage before evaluating its future adapter.

## Manifest and runner contract

`EvaluationManifest` schema `1`: benchmark ID/version; split; seed; evidence-view ID; policy configuration/hash; case list with case ID, group ID, primary scenario, request relative path, artifact mappings (ID/path/hash), oracle relative path; dataset provenance/license record; configuration fingerprint; expected count. All paths are normalized relative paths confined to an explicit artifact root, rejecting absolute/UNC paths, traversal and symlinks/reparse points escaping the root. No archive extraction. Maximum manifest 4 MiB; at most 10,000 cases; each request obeys document 03 limits.

Oracle files are loaded by reporting after inference. Future loader implementation must use separate structures for backend inputs and oracle data; no catch-all metadata passthrough. External trust is never enabled by a manifest field. For authored fixture evaluation, a trusted runner configuration explicitly authorizes the fixture collector and verifies artifact digests against a separately reviewed oracle manifest; it constructs runtime bindings. This simulates a trusted collector and is labeled synthetic. Arbitrary imported traces cannot authorize their own bindings.

`evaluate(manifest, verifier_factory, output_dir)` runs sequentially; factory receives the current case's host-authorized trust bindings, not labels. Creates a new run directory and writes run metadata, one result per case, then aggregate metrics. Refuse overwrite. If interrupted, leave an incomplete report with scheduled/completed counts; v0.1 does not resume silently. Re-run into a new directory. Persist errors as case results. Run configuration includes package/source revision, lock hash, model file manifest, processor/prompt/policy hashes, device/dtype, seeds, dependency versions, and OS/hardware. Record whether generation is deterministic on that hardware; do not promise cross-device bit equality.

Matched comparison requires identical case IDs, objective/criteria, raw evidence bytes/order, trust eligibility and policy hashes; model/backend versions and inference timings are expected to differ. Record each adapter's declared preprocessing; differing processor transformations are disclosed as part of the system comparison, never described as identical tensor inputs. Reject incompatible evidence views or a backend that silently omitted evidence. An experiment claiming a preprocessing-controlled comparison must additionally match preprocessing fingerprints. Model invocation/unused-backend counts prevent deterministic-only cases from inflating a visual model's reported accuracy.

Developer utility: `python -m nitelos.evaluation run --manifest PATH --artifacts ROOT --output NEW_DIR --backend deterministic|smolvlm --model-dir PATH`. Model directory required only for smolvlm. Policy comes from reviewed manifest configuration, and no host external binding can be created from a CLI flag naming an untrusted source. Fixture trust uses the reviewed built-in fixture collector only. Exit codes: 0 complete run (regardless of model accuracy), 2 invalid manifest/config, 3 run infrastructure/incomplete failure. Per-case backend errors do not abort the run and are counted; `compare` refuses incompatible manifests unless explicitly labeled different-evidence analysis in a future version. No v0.1 general verification CLI.

## Metric definitions

Let N be scheduled valid benchmark cases, E input errors, B backend errors, O ok executions, A ok abstentions, D ok decisive results. Then N=E+B+O, O=A+D. Report raw counts first, by split, family, scope, domain and backend. `K` denotes cases with binary oracle truth. `TP`, `FP`, `TN`, `FN` use only decisive predictions with binary truth. Unknown oracle cases are excluded from binary truth metrics, but remain in execution/abstention and sufficiency reporting.

| Metric | Definition and denominator |
|---|---|
| Execution success rate | O/N; separately E/N and B/N |
| Overall coverage | D/N, and binary-label coverage D_K/N_K |
| Conditional coverage | D/O (label as conditional; never sole reported coverage) |
| Abstention | A/N and A/O, both named explicitly |
| Decisive accuracy | (TP+TN)/(TP+TN+FP+FN) |
| Selective risk | (FP+FN)/(TP+TN+FP+FN); always alongside coverage |
| End-to-end correct decision rate | (TP+TN)/N_K, counting errors/abstentions in denominator but not calling them model misclassifications |
| False acceptance rate | FP / all scheduled binary-negative cases, including error/abstained negatives; also report FP/(FP+TN) as **decisive-negative FAR** |
| False rejection rate | FN / all scheduled binary-positive cases; also FN/(FN+TP) as **decisive-positive FRR** |
| Success precision / recall | TP/(TP+FP); TP/N_positive respectively (abstentions/errors reduce recall) |
| Failure precision / recall | TN/(TN+FN); TN/N_negative respectively |
| Unsafe acceptance under insufficient evidence | success predictions on insufficient/contradictory cases / all such cases |
| Policy conformance accuracy | exact expected execution status/decision/reason match / all conformance cases; no probabilistic interpretation |
| Reference validity | Valid emitted refs / all emitted refs, measured before validator rejection; report invalid outputs too |
| Semantic grounding | Human-supported claims / human-audited claims, with sampling protocol; Smol label-to-image assessment, not automatically 100% because IDs resolve |
| Counterfactual sensitivity | both predictions match pair's expected decisions / complete labeled pairs; report errors and unknowns separately |
| Irrelevant-change invariance | same decision across controlled irrelevant-edit pairs / all such pairs, plus correctness to avoid rewarding constant answers |
| Latency | per-case monotonic wall elapsed; median/p95 nearest-rank with n, cold/warm separated; include errors in all-attempt series |
| Cost | sum measured/estimated costs with source and currency; unknown if incomplete, not zero; local API spend zero, electricity/amortization unmeasured |
| RAM/VRAM | isolated process observed peak RSS / framework peak device allocation, with method and baseline; null if unavailable |
| Throughput | completed cases / measured runner wall seconds, including model load when labeled end-to-end; no speculative batching claim |

Empty denominators yield JSON null and `undefined_reason`, never 0/NaN. An all-abstain model has zero coverage and undefined selective risk, not perfect accuracy. A missing provider measurement stays null. An invalid request present in the fixed benchmark remains counted in an integrity/error table; report binary truth metrics on its scheduled binary label if available rather than silently dropping it.

Probability metrics apply only to a score explicitly targeting the binary criterion/outcome event and a predefined corresponding oracle label. Shipped adapters have no such scores, so calibration metrics and risk-coverage curves are `not_applicable`. Never rank a null score as zero. Custom uncalibrated probabilities may be assessed for calibration quality without calling them calibrated: binary Brier mean `(p-y)^2`; log loss with documented clipping epsilon 1e-12; ECE with 10 fixed equal-width bins weighted by sample count. Report bin counts, average predicted probability and empirical frequency. Criterion probabilities cannot be treated as overall conjunction probabilities. Calibration-error estimates are noisy and depend on binning; report uncertainty and reliability diagrams before strong conclusions.

Future risk-coverage curves sort a predefined confidence/ranking score on eligible binary cases, with deterministic case-ID tie breaking; include errors in the scheduled denominator. Declare whether curve is across model scores or policy thresholds, and preserve evidence and model output. Do not optimize the displayed threshold on final-test labels. Baseline without scores is a single operating point, not an invented curve.

## Statistical plan

Use 95% Wilson intervals for descriptive independent binomial proportions; implement through tested formulas or statistical library routines with hand-known tests. For clustered templates/trajectories and counterfactual pairs, primary uncertainty is a group bootstrap (2,000 replicates, fixed seed), resampling complete groups. Stratify by primary scenario when reporting macro summaries. Small group counts yield descriptive intervals with explicit limitations, not reliable universal guarantees.

Compare backends on identical cases via paired group bootstrap of accuracy/coverage/FAR differences. Report absolute counts and effect intervals, not only p-values. Exact McNemar may be secondary on independent paired binary correctness labels; it does not solve clustered dependence or unequal abstention behavior. Predeclare comparisons; multiple exploratory comparisons are labeled exploratory (or Holm adjustment for a fixed family). Never compare raw accuracy among different decisive subsets as if matched.

For a future fixed acceptance rule, a one-sided 95% Clopper–Pearson upper bound on error rate uses k errors among n independent accepted examples. For k=0, upper bound is `1 - 0.05^(1/n)`; n=0 is undefined. About 299 independent zero-error acceptances are needed for an upper bound below 1%, under iid Bernoulli assumptions. Template variants are not independent evidence. Selecting thresholds on the same samples invalidates a naive guarantee: use an independent audit set or a justified simultaneous/selective risk procedure. Scope the statement to the frozen distribution, label quality and selection rule. No v0.1 fixed-risk guarantee.

Temperature scaling later fits positive T on calibration-fit logits by minimizing NLL; freeze before threshold-selection and audit. Do not fit on final tests or conflate temperature with decoder sampling temperature. Domain shift, option-order changes, quantization, image preprocessing or prompt edits require reassessment.

## Reporting and negative results

Publish every scheduled case's status, decision, reasons, refs and configuration hash with privacy-safe IDs. Provide aggregate AND scenario tables, insufficient-evidence errors, model invalid-output rate, and examples of failures cleared for sharing. Include all-null metrics and failed execution runs. Disclose task-trained vs zero-shot models, provider versions, evidence differences, exclusions and all explored development configurations. Final-test reruns after tuning are a new test version or explicitly contaminated exploratory results. A poor local model can still be an honest experimental baseline; do not hide it behind deterministic aggregate performance.
