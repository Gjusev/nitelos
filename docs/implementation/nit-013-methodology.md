# NIT-013 part B — development-split runs and report methodology

Status: **development split executed; FINAL-TEST RUNS DEFERRED** pending the
AR-4 freeze approval and the G4 human-annotation gate. Nothing in this document
was tuned on observed results; the deterministic and visual dev runs below are
the first and only runs.

## What ran (development split only)

Environment: WSL Ubuntu, Python 3.12.15, AMD Ryzen 5 7600X, 15 GiB allocation,
nothing else heavy running. torch 2.14.1+cpu / transformers 5.19.0 /
torchvision 0.29.1+cpu / num2words 0.5.14 (the frozen `local` extra); lock hash
`60381e31…`; package version from the branch HEAD. The pinned checkpoint is
`HuggingFaceTB/SmolVLM2-2.2B-Instruct @ 482adb537c021c86670beed01cd58990d01e72e4`
(ADR-012), manifest-verified per file before the run; the honest history of the
500M era (attempt 1, bounded iteration round, D3) is in
`docs/implementation/nit-008-compatibility-report.md`.

| Run | Manifest | View | Backend | Output |
|---|---|---|---|---|
| dev-deterministic | `benchmarks/synthetic_v1/dev.json` | assertion | `DeterministicBackend` via the evaluation CLI | `reports/dev-split/dev-deterministic/` |
| dev-visual-smolvlm | `benchmarks/synthetic_v1/dev-visual.json` | visual | `SmolVLMBackend` (2.2B) via the labeled driver `benchmarks/run_dev_visual_013b.py` | `reports/dev-split/dev-visual-smolvlm/` |

The visual driver is TEMPORARY and clearly labeled in its docstring: it reuses
the runner's own `evaluate()` pipeline with one shared, lazily loaded backend
(the model is NOT reloaded per case), and produces the runner's exact report
shapes so the RUN-01/02 validator applies unchanged. It is replaced by
`--backend smolvlm --model-dir` as soon as the NIT-012 wiring merge lands.

Both runs are validated by `nitelos.evaluation.report_validation.validate_run_report`
(RUN-01 structure/coherence/leak scan; RUN-02 counts and per-family
completeness). The per-family tables and the label-agreement column are
produced by `benchmarks/family_table_013b.py` (pure reporting; no re-running,
no rewriting of run records) into `reports/dev-split/*-families.json`.

## What the development split is for — and what it is NOT

- It exercises the full pipeline (manifest loading, artifact/digest checks,
  fixture-collector trust, per-case verification, oracle loading, metrics) on
  real data at real scale.
- Dev-label agreement is an engineering observation, NOT an accuracy claim.
  The 2.2B checkpoint's known behavior from the NIT-008 smoke set — format
  compliant but over-claiming — is carried through the family tables (the
  SUPPORTED-heavy decision distribution and the agreement column make it
  visible); it is reported, not tuned on.
- No prompt, parser, model, preprocessing or threshold change was made on the
  basis of these runs, and none may be without a decisions.md entry.

## Frozen-pending (do not run before the gates)

- `test.json` / `test-visual.json` (the final-test manifests and their
  oracles): **FINAL-TEST RUNS DEFERRED** until (a) AR-4 approves the frozen
  dataset groups, oracles, input views, metrics, prompt/config, and (b) the G4
  human-annotation gate signs the final-test oracles (annotation_status must
  be `approved` for all 60 final cases; the freeze script refuses until then
  by design). Final-test data has not been inspected while preparing the dev
  runs.
- The prompt (`smolvlm-criterion-v1`, hash `08fde1e3…`) and the checkpoint are
  frozen for the final runs.

## Exact final-run plan (after AR-4 + G4)

Commands (WSL clone of the integration branch, nothing else heavy running;
`NITELOS_MODEL_DIR` → the verified 2.2B directory):

```text
uv sync --frozen --group dev --extra local --extra eval
NITELOS_RUN_LOCAL=1 NITELOS_MODEL_DIR=… uv run pytest -m local_model tests/integration/test_local_model.py -q
uv run python -m nitelos.evaluation run \
  --manifest benchmarks/synthetic_v1/test.json \
  --artifacts benchmarks/synthetic_v1 \
  --output reports/final-test/test-deterministic --backend deterministic
uv run python -m nitelos.evaluation run \
  --manifest benchmarks/synthetic_v1/test-visual.json \
  --artifacts benchmarks/synthetic_v1 \
  --output reports/final-test/test-visual-smolvlm \
  --backend smolvlm --model-dir "$NITELOS_MODEL_DIR"   # or the labeled driver until the wiring merges
```

Expected durations from the dev runs: the deterministic view completed in
seconds; the visual dev run measured 491.4 s wall (~8.2 min) for 60 cases —
20 model invocations at 48.4 s cold / 18.6 s warm median (37.6 s p95), peak
RSS 10.27 GB (ru_maxrss). The final visual run's wall time depends on how many
cases invoke the model after the preflight finding below is resolved.
Both runs are then validated with `validate_run_report` and the family tables
regenerated. Any result is reported as found — a poor accuracy number is
a finding, never a tuning input.

## Dev-run findings (reported, not tuned)

1. **Preflight rejects carried external/behavioral criteria on a visual-only
   backend (30/60 dev-visual cases, all UNSUPPORTED_CAPABILITY).** The
   visual-view requests of 7 families (S01/S02/S04/S06/S07-v2/S10/S11/S15)
   legitimately carry external or behavioral criteria alongside their visual
   criterion (doc 06: external criteria remain external in both views). The
   NIT-007 preflight validates every criterion kind against the backend's
   declared `criterion_kinds`, and the SmolVLM backend declares
   `("visual",)` per the NIT-008 design §10 — so those requests are rejected
   before any inference. Doc 04's capability table, however, assigns
   assertion criteria to the core evaluator for every backend. Resolution is
   a contract decision (declare assertion handling in the backend's
   capabilities vs special-case core-evaluated kinds in the preflight); per
   the task rules this is reported, not adjusted.
2. **Dev-label agreement on the 30 executed cases: 13/30.** The mismatch
   patterns confirm and extend the smoke-set over-support observation: every
   S03/S14 case answered success where the dev oracle expects failure
   (refuted-by-state scenes over-claimed), S12 ambiguous scenes answered
   success where abstain was expected, S09 contradictory scenes split
   3 success / 1 failure where abstain was expected, and one S13
   counterfactual member flipped. Model-invoked cases only (20); the 10
   abstentions without model invocation (S05 pending, S08 empty-evidence and
   2 S07-v1 subject-mismatch cases resolved by policy, correctly) are not
   model behavior. Consistent with the honest NIT-008 record (format
   compliant, over-claiming); no tuning was performed or is proposed on dev
   labels.
