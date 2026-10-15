# AR-4 — freeze dossier for the synthetic-v1 final runs

Status: **proposed for orchestrator approval**. This document is the AR-4 review
artifact. It records what is frozen NOW, each with the digest or SHA that proves
immutability and where it lives in-repo, and what freezes only after the G4 human
gate. Nothing here changes any frozen item; it declares them.

All digests are SHA-256 over git-blob bytes (LF-normalized; the repo's
`.gitattributes` enforces `eol=lf`, so a Linux checkout hashes identically).

## 1. Protocol freeze (effective now)

| Item | Value | Where it lives |
|---|---|---|
| Prompt `smolvlm-criterion-v1` | `08fde1e3776018111c0a1de8796b0660c7df2c5b2ac9623357fda1d6087d706d` | `src/nitelos/backends/smolvlm.py` `_TEMPLATES["v1"]`; frozen text, merged @ `37e4b8a` |
| Preprocessing declaration | resize longest-edge 1024; `PREPROCESSING_HASH = c7b4c1d1cdd44a0b19e491ae1e1f994cd03aecf7d49319dae97f9b6788046fd6` (of `resize-longest-edge-1024;patches`) | same module, `LONGEST_EDGE = 1024` @ `37e4b8a` |
| Strict parser | whitespace-only strip, case-sensitive, greedy `max_new_tokens=8` | same module @ `37e4b8a` |
| Model pin | `HuggingFaceTB/SmolVLM2-2.2B-Instruct @ 482adb537c021c86670beed01cd58990d01e72e4` (ADR-012, user-approved 2026-10-15); Apache-2.0 | id/revision constants in the same module; per-file SHA-256 verification against upstream LFS oids is orchestrator-held outside the repo (weights are never redistributed — see `docs/implementation/dependency-licenses.md`) |
| Smoke provenance | 2.2B smoke record `97482b008e7339f7ef1342fc1ec3782713bbd83925885a707969389675040ba6`; D3 sanity `e96a449caea01f59e28bd570b7286240de98b2ceb7710049fc5399dcc4b721f2` | `benchmarks/smoke-run-2.2B.json`, `benchmarks/d3-2.2B-sanity.json` (records at `nit/008-smolvlm @ f1140e3`, carried on integration) |
| Policy definitions | `strict` (assertion view): `ade7d024af1a4c58f7cf49730d5789c28c74155d8a067fa44d42e73ba0440f9e`; `strict` + `allow_model_inference` (visual view): `5160a8cbe0450933fcc0ba68f4983ad3b23e28110453e9c084fda5b99dc21ddb` | `src/nitelos/policy.py` `policy_hash` @ `42ef33a`; the two hashes are the ones declared inside every manifest below |
| Deterministic evaluator | assertion criteria: RFC 6901 pointer grammar, operators `equals` / `in` / `exists`; canonical JSON v1 digests; strict conjunction, contradiction → unknown | `src/nitelos/policy.py` @ `42ef33a`, `src/nitelos/evidence.py` @ `cf25f7b`, `src/nitelos/schemas.py` (canonical JSON) |
| Metric definitions | doc-06 rate rows: proportions with Wilson 95% (z = 1.959963984540054; exact boundaries k=0 → 0.0, k=n → 1.0), Clopper-Pearson upper bounds, 2000-replicate group/paired bootstrap, nearest-rank latency, undefined-with-reason on empty denominators (never 0/NaN) | definitions: `docs/implementation/nit-011-metrics-design.md`; code: `src/nitelos/evaluation/statistics.py` @ `5ffd8e8`, `src/nitelos/evaluation/metrics.py` @ `236b868` |
| View definitions | assertion view: `dev.json` `d880cfb96e7ad700b5cd06eb5c7971b079ee00b33f8b96ce45bd9a31de8860c4`; visual view: `dev-visual.json` `247426149d859bcfbba64d3202b9330982582279679c23bcf95208389309a632` — external criteria remain external in both views (doc 06) | `benchmarks/synthetic_v1/dev*.json` (the view construction the test manifests share) |
| Runner | sequential, one case at a time, no retries/resume, per-case errors are results; shared-backend mode (one backend per run, closed once); exit codes 0/2/3 | `src/nitelos/evaluation/runner.py` @ `7fb9e09` (merged `d8c491a`) |
| Report validator | RUN-01 structure/coherence/leak-scan (oracle tokens never in run dirs), RUN-02 per-family completeness | `src/nitelos/evaluation/report_validation.py` @ `b451a6a` |
| Environment lock | `uv.lock` `83a01dc0ed54a5137979727c64a00ffa4aa2adadc0896a7078267d32cb96bb98` (unchanged since `d945626`; the dev runs of 2026-10-15 ran on this lock — the `60381e31…` value still visible in older records predates the torchvision/num2words additions and is stale) | `uv.lock`; local extra: torch 2.14.1+cpu, transformers 5.19.0, torchvision 0.29.1+cpu, num2words 0.5.14 |
| Package | nitelos `0.1.0` | `src/nitelos/__init__.py` |

Preflight contract (decisions.md, 2026-10-15): assertion criteria are ALWAYS
core-evaluated and NEVER consult backend capabilities; the backend-kind preflight
applies only to visual criteria. This interaction is part of the frozen protocol.

## 2. Data freeze

**Dev split — frozen now, because it has been used.** The deterministic and
visual dev runs of 2026-10-15 read this data; it must never change again:

| Artifact | Digest |
|---|---|
| `dev.json` (60 cases, assertion) | `d880cfb96e7ad700b5cd06eb5c7971b079ee00b33f8b96ce45bd9a31de8860c4` |
| `dev-visual.json` (60 cases, visual) | `247426149d859bcfbba64d3202b9330982582279679c23bcf95208389309a632` |
| `fixture-collector.json` | `967e497a0af99ba4a0cfd50bee2aedd0671486f810dd57c28a24c11b942a9917` |
| `oracle/` (120 per-case records) | covered by the tree digest below |

**Final split — inputs frozen now; oracles pending the human gate.** The final
manifests, requests and artifact bytes are label-independent and are frozen now:
`test.json` `d66b898f548bb6723ac96daca90a3aa9c09b22539c58608d172dfe43dfb197b5`,
`test-visual.json` `22de9869ce8a62a7c51d29647e879193c2bcefb99839fa9401f569c9922c0cec`
(60 cases each). The 60 final-test oracles stay `pending_human_review`, and the
freeze tool refuses the final freeze while any record is (exit 1 — agents cannot
satisfy the gate by design).

Final-freeze procedure (G4): (1) audit — two independent human reviewers work the
60 packets in `benchmarks/synthetic_v1/review-packets/` (`REVIEWER-INSTRUCTIONS.md`:
image-vs-state match, per-view expected findings, outcome_truth,
evidence_sufficiency, expected decision/reason codes, scope tags; ~3–4 min/case;
no cross-consultation; reviewers never see model output); (2) adjudication of
disagreements — unresolved cases keep unknown labels and are reported; (3) sign-off
fields written per record (`annotation_status: approved`, non-empty `annotators`,
non-null `sign_off`); (4) `tools/freeze.py` final run writes `freeze.sha256` over
the whole tree. A provisional tree digest `0496378d58bbc7b8ac2dac6f49901476453100921f6f2524e54ab64dd6cf1cff`
is recorded in `freeze.sha256.provisional` and becomes the final value only after
the oracle sign-offs (the oracle edits will change it — that is expected and is
exactly what the final digest then seals).

## 3. Negative-result reporting commitments (G8)

- Per-family tables for every reported metric, with denominators always shown:
  errors, abstentions and coverage are reported alongside every rate; undefined
  metrics carry their reason, never a silent 0.
- The 2.2B over-support observation is carried as a headline limitation wherever
  results appear (dev-label agreement 41/60 on the fixed re-run; S03/S14/S12/S09
  over-claim patterns; smoke-era 4/12 agreement) — reported, not tuned, with no
  accuracy claim of any kind attached to the checkpoint.
- No real-world or deployment claims from synthetic-v1 results; results are
  labeled synthetic and benchmark-scoped.

## 4. Final-run plan (after AR-4 approval + G4 sign-off)

WSL clone of the approved integration branch, nothing else heavy running;
`NITELOS_MODEL_DIR` → the verified 2.2B directory; `uv sync --frozen --group dev
--extra local --extra eval`; the gated real-model integration test
(`NITELOS_RUN_LOCAL=1 … pytest -m local_model tests/integration/test_local_model.py`)
must pass first. Then, via the CLI (single shared backend per run, closed once):

```text
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

Expected durations from the measured dev runs: deterministic view in seconds;
visual view ~880 s wall for 60 cases (~40 model invocations at 59.0 s cold /
18.6 s warm median, 34.6 s p95; peak RSS ~10.3 GB) — plan ~15 min plus margin.
Both runs are validated with `validate_run_report` (RUN-01/02) and the family
tables regenerated from the run records. run.json will carry the real
`preprocessing_hash` (the probe defect found at shared-backend time is fixed;
the dev-split records stand as run with `null`, which is harmless — the hash is
constant for this pinned era). Rule: final-test labels and results never feed
back into prompts, parsing, policies, thresholds or data; any such change is a
new experiment.

## 5. Change policy after approval

Any change to a frozen item above — prompt text, parser, preprocessing, model
pin, policy definitions, metric formulas, view construction, evaluator grammar,
runner/validator semantics, or the dev-split data — ends synthetic-v1 as the
current experiment and requires a new experiment (synthetic-v2) with its own
design record, per docs 05 and 06. The final-split oracles change exactly once,
through the G4 sign-off fields, before the final freeze seals them.
