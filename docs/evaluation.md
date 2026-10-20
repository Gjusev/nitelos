# Evaluation and calibration limitations

The evaluation module is a bounded research utility, not a product feature:

- **Sequential, reproducible, no retries.** One case at a time into a new
  user-selected directory; interrupted runs are explicitly incomplete; every
  scheduled case produces a result, including input and backend errors
  (`scheduled = errors + ok`).
- **Synthetic-first.** The v0.1 benchmark is 120 authored synthetic cases with
  frozen splits. The final runs on the sealed tree are complete: four runs (both
  views, both splits), every figure with its denominator in
  [reports/v0.1/SUMMARY.md](../reports/v0.1/SUMMARY.md). These docs quote no
  numbers; the summary is the single source. Final-test labels were audited by
  two independent AI reviewers plus adjudication; no human annotation audit was
  performed, and human review remains a precondition for broader claims.
  Real-world audit data is a separate, later step with its own licensing and
  privacy review.
- **Uncertainty is honest.** Wilson intervals for descriptive proportions,
  group bootstrap for clustered comparisons; empty denominators are null with
  a reason, never 0 or NaN. An all-abstain model has zero coverage and
  undefined selective risk — it is not "perfectly cautious".
- **No calibration claims.** Shipped backends expose no numerical confidence;
  calibration metrics are `not_applicable`. `calibrated_probability` scores
  are rejected outright in v0.1. Custom uncalibrated scores may be *reported*
  (Brier, log loss, ECE exist for them) but are never called calibrated, and
  no threshold fitting ships.
- **Oracle separation is structural.** Backend inputs and oracle data are
  distinct types with distinct loaders; labels are loaded only after inference
  and never reach a model or a per-case report (sentinel-tested).
- Model-invocation counts prevent deterministic-only cases from inflating a
  visual backend's reported accuracy; matched comparisons require identical
  evidence, policy and trust fingerprints.
