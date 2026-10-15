# Evaluation and calibration limitations

The evaluation module is a bounded research utility, not a product feature:

- **Sequential, reproducible, no retries.** One case at a time into a new
  user-selected directory; interrupted runs are explicitly incomplete; every
  scheduled case produces a result, including input and backend errors
  (`scheduled = errors + ok`).
- **Synthetic-first.** The v0.1 benchmark is 120 authored synthetic cases with
  frozen splits. **No benchmark run has been executed yet** — no accuracy,
  coverage or latency number exists to cite, and none appears in these docs.
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
