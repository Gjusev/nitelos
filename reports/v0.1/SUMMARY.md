# Nitelos v0.1 — final benchmark summary (synthetic-v1, sealed tree)

Four runs over the sealed benchmark tree (freeze `accf8f46de2fa9be99aa31c0fe367593bbb5697cb1dd1f28fe64e38a89d7f185`),
executed 2026-10-15 on WSL Ubuntu CPU (torch 2.14.1+cpu / transformers 5.19.0,
lock `83a01dc0…`, nitelos 0.1.0, package `SmolVLM2-2.2B-Instruct @ 482adb5…`,
prompt v1 `08fde1e3…`, preprocessing `c7b4c1d1…` recorded in the visual
run.json files). Both views, both splits, one run each; every number below is
read from the run artifacts in this directory. Per-family tables:
`*-families.json` beside each run directory.

**Binding label (ADR-013):** final-test labels audited by two independent AI
reviewers plus adjudication; NO human annotation audit was performed. Human
annotation review remains a precondition for any publication.

## Four-run results (reported as found; no tuning was performed at any point)

| Run | View / split | n | ok | abstain | decisive | Policy conformance | Decisive accuracy | Unsafe acceptance |
|---|---|---|---|---|---|---|---|---|
| dev-deterministic | assertion / dev | 60 | 60 | 22 | 38 | 1.0000 | 38/38 (1.0000) | 0/18 (0.0000) |
| test-deterministic | assertion / test | 60 | 60 | 22 | 38 | 1.0000 | 38/38 (1.0000) | 0/18 (0.0000) |
| dev-visual-smolvlm | visual / dev | 60 | 60 | 18 | 42 | 0.6833 | 26/38 (0.6842) | 7/18 (0.3889) |
| test-visual-smolvlm | visual / test | 60 | 60 | 18 | 42 | 0.6833 | 26/38 (0.6842) | 7/18 (0.3889) |

Zero input errors and zero backend errors in all four runs (e=0, b=0; every
scheduled case produced exactly one result row, RUN-01/02 validated). The
deterministic engine is exact at 120/120 cases across both splits. The visual
results are IDENTICAL across the dev and test splits (same counts, same
metrics to four decimals) — the split-holdout found no generalization gap on
this synthetic benchmark, which is itself a property of the fixture design,
not a claim about the model.

Label agreement vs the per-split oracles (from the family tables):
deterministic 60/60 both splits; visual 41/60 in EACH split, with the same
mismatch distribution in both (11 failure→success, 7 abstained→success,
1 abstained→failure over the two disjoint 60-case splits' own cases). The
mismatch cases differ between splits because the splits are disjoint; the
counts and directions coincide.

## Model-judgment limitations (headline)

- **The visual backend over-supports, quantified.** Of the 38 cases where the
  oracle expects a decisive answer, the visual pipeline answered wrongly on
  12 (decisive accuracy 26/38 = 0.6842) — and every decisive error is an
  over-acceptance: decisive false-acceptance rate 0.5, false-rejection rate
  0.0 (no case the evidence supported was rejected; cases the evidence
  refuted or withheld were affirmed). Where evidence is insufficient (18
  cases), the unsafe acceptance rate is 7/18 = 0.3889 — the model asserts
  outcomes the evidence does not establish. These are the same failure shapes recorded since the
  NIT-008 smoke set (4/12 agreement) and the dev-split runs (41/60); they are
  properties of the pinned checkpoint under the frozen prompt and parser,
  reported, not tuned.
- **Deterministic evaluation is exact** (120/120, no unsafe acceptances), and
  the abstention machinery it shares with the visual path (policy gating,
  trust bindings) behaved identically in both views — the difference is model
  judgment, not policy machinery.
- **The benchmark is synthetic and small.** 15 authored families, 8 cases
  each, one renderer, English UI text. **No real-world generalization claim
  is made or implied by anything in this directory** — not for the visual
  backend's accuracy, calibration, or safety, and not for over-claiming rates
  on any other distribution.
- Final-test labels are agent-audited (ADR-013, above); AI reviewers may
  share biases a human audit was designed to catch.

## Cold/warm latency and memory (from the run records)

| Run | Wall | Cold (n=1) | Warm median / p95 | Peak RSS |
|---|---|---|---|---|
| dev-deterministic | 1.1 s | — | 11.5 ms / 18.9 ms | 0.05 GB |
| test-deterministic | 1.3 s | — | 13.9 ms / 23.5 ms | 0.05 GB |
| dev-visual-smolvlm | 917.8 s | 37 827 ms | 19 891 ms / 40 377 ms | 9.63 GB (ru_maxrss) |
| test-visual-smolvlm | 868.8 s | 38 831 ms | 17 607 ms / 39 250 ms | 9.63 GB (ru_maxrss) |

Visual runs: 40 model invocations per 60-case run (the shared-backend mode
loads the model once; the preprocessing hash `c7b4c1d1…` is recorded in
run.json — the probe defect found at shared-backend time is confirmed fixed
in these records).

## Artifacts

- `dev-deterministic/`, `test-deterministic/`, `dev-visual-smolvlm/`,
  `test-visual-smolvlm/` — run.json, cases.jsonl (one row per scheduled
  case), metrics.json, COMPLETE marker; RUN-01/02 validated.
- `*-families.json` — per-family decision/invocation/latency tables plus the
  label-agreement column (pure reporting over the run records).
- Benchmark provenance: `benchmarks/synthetic_v1/` (DATA_CARD.md, freeze
  record, audit records under `audit/`), adjudication in
  `docs/implementation/decisions.md` (2026-10-15 entries).
