# Pre-action gate (extra `gate`), an experimental research port

[nitelos.gate](https://github.com/Gjusev/nitelos/blob/main/src/nitelos/gate.py)
answers the "before" question: should the agent act, or ask a human first?
It is a port of the decision math of the maintainer's `gate-calibrated`
repository (MIT, copyright 2026 Gjusev), relicensed to Apache-2.0 by the
copyright holder per ADR-017. One library then covers both halves: gate
before acting, verify after acting.

## What was ported, and what was not

Ported: the two calibrators (temperature scaling; logistic regression on
logit of the verbalized confidence, agreement, tier and step position), the
conformal risk-controlled threshold, the three policies
(`confirm_all`, `fixed_threshold`, `calibrated`) and the shared types.
NOT ported: the source's model calls (litellm), signal collection and
tau-bench middleware. Confidence signals arrive as NUMBERS supplied by the
host, so nitelos still never calls a model and opens no network. The tier
map (read / write / irreversible) is host configuration, like criteria.
Irreversible actions ALWAYS ask; that is the source repository's invariant
and it is tested here.

## Install

```text
pip install 'nitelos[gate]'
```

The threshold and policy layers are pure Python and work without the extra;
only the calibrators need numpy, loaded lazily with an actionable error.

## Minimal example

```python
from nitelos.gate import CalibratedPolicy, StepRecord, make_policy

record = StepRecord(
    task_id=1,
    split="live",
    trial=0,
    step_index=4,
    tool_name="update_order",
    kwargs={"order_id": 7},
    tier="write",
    verbalized=0.93,
    agreement=0.75,
    p_hat=0.91,
)
decision = CalibratedPolicy(lam=0.9).decide(record)  # action "act"
policy = make_policy("confirm_all")  # ask on every gated action
```

Calibration workflow: fit a calibrator on labeled records
(`TemperatureScaling` or `LogisticRegression`, `to_json`/`from_json` for
storage), compute `p_hat` for each calibration step, then
`choose_lambda(steps_by_traj, p_hat_by_traj, alpha)` picks the smallest
threshold whose conformal bound holds, and `expected_approvals` estimates
the human load.

## The result, as written in the source

This is an experimental research port, not a validated improvement. The
source's main result: risk control held on the live test split in point
estimates (every calibrated configuration kept the share of trajectories
with an executed wrong write at or under its alpha), but it did not beat
the simple alternatives: at alpha 0.10 and above the calibrated gate never
asks on a write step and is in practice the same policy as the fixed 0.7
threshold, and at alpha 0.02 it removes wrong writes at a rate per extra
approval indistinguishable from confirming every write. The likely reason
is the signal: glm-5.3-flash stated a confidence of 0.9 or more on all 43
wrong write steps in the collected data, so the calibrator's only useful
feature was the position of the step in the conversation.

## Assumptions and limitations (verbatim from the source)

- "The risk guarantee assumes exchangeability between calibration and test
  trajectories and is computed on ungated runs; under the gate, a rejection
  changes the path the agent takes afterwards."
- The evaluation's approving human was "a perfect oracle built from the gold
  actions of tau-bench. A real reviewer errs and tires."
- `GateDecision` and nitelos verification results are separate types with
  no coupling; recording gate decisions as verification context would need
  its own ADR (ADR-017 finding 4).
- Tests in this repository use synthetic labeled records only; no tau-bench
  data was copied (ADR-017 finding 3).
