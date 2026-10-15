# Performance measurement

What we measure, how, and what is honestly unknown:

- **Deterministic path**: linear in criteria and referenced observations, plus
  hashing/decoding. Assertions run in microseconds; the measured unit is the
  per-criterion duration recorded in diagnostics (`criterion_durations_ms`).
- **Local visual backend**: load time is reported separately from warm
  inference; latency reporting uses nearest-rank median/p95 with n, cold and
  warm separated. Peak RSS is read via `ru_maxrss` on Linux and is null with
  a reason where not measurable per-process (Windows). Throughput counts the
  runner wall clock including model load, labeled end-to-end.
- **No published numbers yet.** The frozen benchmark has not run; nothing in
  these docs cites an accuracy, latency or memory figure. When NIT-013
  executes, its reports will name CPU/GPU, memory method, model/prompt
  revisions, the dependency lock and input sizes.
- **Known failure modes** (documented, not hidden): a local model may decode
  a label the strict parser rejects (`INVALID_OUTPUT` — reported, never
  repaired); pending or unreadable evidence abstains rather than guessing;
  contradictory snapshots become unknown; in-flight native kernels cannot be
  forcibly stopped (see [lifecycle.md](lifecycle.md)).
- Costs stay null without a price source. Synthetic performance is not
  evidence of production payment/upload reliability.
