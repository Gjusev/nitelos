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

Expected durations from the dev runs: the deterministic view ≈ tens of seconds;
the visual view ≈ 30–35 min wall on the reference CPU (dev run measured;
~28–30 s mean per one-image case, ~50 s per two-image case, one ~3 s model
load). Both runs are then validated with `validate_run_report` and the family
tables regenerated. Any result is reported as found — a poor accuracy number is
a finding, never a tuning input.
