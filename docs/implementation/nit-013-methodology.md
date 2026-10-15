# NIT-013 part B — development-split runs and report methodology

Status: **development split executed; preflight finding resolved by ruling and
the visual view re-run on the fixed pipeline; FINAL-TEST RUNS DEFERRED**
pending the AR-4 freeze approval and the G4 human-annotation gate. Nothing in
this document was tuned on observed results; the deterministic run and the two
visual records below are first runs of their respective pipelines, kept
side by side.

## What ran (development split only)

Environment: WSL Ubuntu, Python 3.12.15, AMD Ryzen 5 7600X, 15 GiB allocation,
nothing else heavy running. torch 2.14.1+cpu / transformers 5.19.0 /
torchvision 0.29.1+cpu / num2words 0.5.14 (the frozen `local` extra); lock hash
`83a01dc0…` (sha256 of `uv.lock` at the run refs — the earlier `60381e31…` value
predates the torchvision/num2words lock commits the same sentence names and was
stale); package version from the branch HEAD. The pinned checkpoint is
`HuggingFaceTB/SmolVLM2-2.2B-Instruct @ 482adb537c021c86670beed01cd58990d01e72e4`
(ADR-012), manifest-verified per file before the run; the honest history of the
500M era (attempt 1, bounded iteration round, D3) is in
`docs/implementation/nit-008-compatibility-report.md`.

| Run | Manifest | View | Backend | Output |
|---|---|---|---|---|
| dev-deterministic | `benchmarks/synthetic_v1/dev.json` | assertion | `DeterministicBackend` via the evaluation CLI | `reports/dev-split/dev-deterministic/` |
| dev-visual-smolvlm | `benchmarks/synthetic_v1/dev-visual.json` | visual | `SmolVLMBackend` (2.2B) via the temporary driver `benchmarks/run_dev_visual_013b.py` (git history; pre-preflight-fix pipeline) | `reports/dev-split/dev-visual-smolvlm/` |
| dev-visual-smolvlm-fixed | `benchmarks/synthetic_v1/dev-visual.json` | visual | same driver, pipeline with the preflight fix (assertion criteria core-evaluated on any backend) | `reports/dev-split/dev-visual-smolvlm-fixed/` |

Both dev-visual records were produced with a TEMPORARY labeled driver that
reused the runner's own `evaluate()` pipeline with one shared, lazily loaded
backend and the runner's exact report shapes, so the RUN-01/02 validator
applied unchanged. At delivery time the CLI was not yet equivalent (its
factory constructed one `SmolVLMBackend` per case — a per-case cold load of
~59 s and ~10 GB); the shared-backend change (nit/shared-backend) closed that
gap — the CLI now constructs the backend once per run and closes it once —
and the driver was removed in favor of the CLI. The two dev-visual records
above stand as run: the first documents the pre-fix preflight interaction and
is superseded (for conclusions) by the fixed re-run below.

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
  --backend smolvlm --model-dir "$NITELOS_MODEL_DIR"
```

Expected durations from the dev runs: the deterministic view completed in
seconds; the fixed visual re-run measured 880 s wall (~14.7 min) for 60 cases
— 40 model invocations at 59.0 s cold / 18.6 s warm median (34.6 s p95), peak
RSS 10.33 GB (ru_maxrss). The final visual run should land near the re-run's
shape (60 executed cases, ~40 invocations under the same policy).
Both runs are then validated with `validate_run_report` and the family tables
regenerated. Any result is reported as found — a poor accuracy number is
a finding, never a tuning input.

## Dev-run findings (reported, not tuned)

1. **Preflight rejected carried external/behavioral criteria on a visual-only
   backend (30/60 dev-visual cases, all UNSUPPORTED_CAPABILITY) — RESOLVED
   by ruling.** The visual-view requests of 7 families (S01/S02/S04/S06/
   S07-v2/S10/S11/S15) legitimately carry external or behavioral criteria
   alongside their visual criterion (doc 06: external criteria remain
   external in both views). The NIT-007 preflight validated every criterion
   kind against the backend's declared `criterion_kinds`, and the SmolVLM
   backend declares `("visual",)` per the NIT-008 design §10 — so those
   requests were rejected before any inference, while doc 02 step 5 / doc 04
   assign assertion criteria to the core evaluator for every backend. The
   ruling (decisions.md, integration commit 3454f0b) settles it: assertion
   criteria are ALWAYS core-evaluated and NEVER consult backend capabilities;
   the kind check applies to visual criteria only. The preflight fix landed
   on this branch; `reports/dev-split/dev-visual-smolvlm/` is retained as
   the record of the interaction, and
   `reports/dev-split/dev-visual-smolvlm-fixed/` is the corrected pipeline's
   record.
2. **Dev-label agreement, first visual record (pre-fix, 30 executed of 60):
   13/30.** The mismatch patterns confirm and extend the smoke-set
   over-support observation: every S03/S14 case answered success where the
   dev oracle expects failure (refuted-by-state scenes over-claimed), S12
   ambiguous scenes answered success where abstain was expected, S09
   contradictory scenes split 3 success / 1 failure where abstain was
   expected, and one S13 counterfactual member flipped. Model-invoked cases
   only (20); the 10 abstentions without model invocation (S05 pending, S08
   empty-evidence and 2 S07-v1 subject-mismatch cases resolved by policy,
   correctly) are not model behavior. Consistent with the honest NIT-008
   record (format compliant, over-claiming); no tuning was performed or is
   proposed on dev labels.
3. **Dev-label agreement, fixed re-run (60/60 executed): 41/60.** All 60
   cases now execute; 40 invoke the model and 20 resolve without any model
   call (S05, S06, S08 and S10 in full — S10 as policy failures — plus two
   S07-v1 and two S15 members). Decisions: 29 success /
   13 failure / 18 abstained. The 30 previously-executed cases reproduce
   their first-record decisions identically — the fix changed admission,
   not evaluation. The 30 newly-admitted cases agree with their dev oracles
   in 28/30: every newly-admitted family (S01, S02, S04, S06, S10, S11, S15)
   matches its expected decisions in full, and the only two new mismatches
   are S07-v2's two model-invoked members (expected failure, answered
   success — the same over-support pattern). Total mismatch table:
   S03 failure→success ×4, S14 failure→success ×4, S12 abstain→success ×4,
   S09 abstain→success ×3 + abstain→failure ×1, S13 failure→success ×1,
   S07 failure→success ×2. The over-support observation is unchanged by the
   fix and now measured over 40 invocations; reported, not tuned.
