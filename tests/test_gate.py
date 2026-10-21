"""GATE-01..14: F14 pre-action gate port (NIT-033, extra ``gate``).

Synthetic labeled records only (ADR-017 finding 3): no tau-bench data is
copied. The threshold and policy layers are pure Python and run in the core
environment; the calibrator layer needs numpy and is gated on its presence.
"""

from __future__ import annotations

import pytest

from nitelos.gate import (
    ALPHAS,
    FIXED_THRESHOLD,
    TIER_VALUES,
    CalibratedPolicy,
    ConfirmAllPolicy,
    FixedThresholdPolicy,
    GateDecision,
    StepRecord,
    approvals_needed,
    choose_lambda,
    expected_approvals,
    make_policy,
    trajectory_loss,
)


def _step(
    *,
    tier: str = "write",
    verbalized: float | None = None,
    agreement: float | None = None,
    correct: bool | None = None,
    step_index: int = 0,
    p_hat: float | None = None,
) -> StepRecord:
    return StepRecord(
        task_id=1,
        split="cal",
        trial=0,
        step_index=step_index,
        tool_name="host_tool",
        kwargs={},
        tier=tier,
        verbalized=verbalized,
        agreement=agreement,
        correct=correct,
        p_hat=p_hat,
    )


def _traj(steps: list[StepRecord], p_hats: list[float]) -> tuple[list[StepRecord], list[float]]:
    return steps, p_hats


def test_gate01_trajectory_loss_counts_only_executed_wrong_writes() -> None:
    wrong = _step(correct=False)
    right = _step(correct=True)
    assert trajectory_loss([wrong], [0.99], 0.9) == 1.0
    assert trajectory_loss([wrong], [0.5], 0.9) == 0.0  # below lambda: would ask
    assert trajectory_loss([right], [0.99], 0.9) == 0.0
    irreversible = _step(tier="irreversible", correct=False)
    assert trajectory_loss([irreversible], [0.99], 0.9) == 0.0  # always asks
    read = _step(tier="read", correct=False)
    assert trajectory_loss([read], [0.99], 0.9) == 0.0  # ungated tier


def test_gate02_mean_loss_and_choose_lambda_bound() -> None:
    wrong = _step(correct=False)
    right = _step(correct=True)
    by_traj = {0: ([wrong], [0.99]), 1: ([right], [0.99]), 2: ([right], [0.99])}
    steps = {t: v[0] for t, v in by_traj.items()}
    p_hats = {t: v[1] for t, v in by_traj.items()}
    lam = choose_lambda(steps, p_hats, alpha=0.5)
    # N=3: bound at lam=0.99 is (3/4)*(1/3) + 1/4 = 0.5 <= 0.5 -> accepted
    assert lam == 0.99
    assert choose_lambda(steps, p_hats, alpha=0.2) == 1.0  # unreachable


def test_gate03_choose_lambda_small_n_unreachable_and_empty() -> None:
    wrong = _step(correct=False)
    assert choose_lambda({0: [wrong]}, {0: [0.99]}, alpha=0.05) == 1.0
    assert choose_lambda({}, {}, alpha=0.5) == 1.0


def test_gate04_choose_lambda_smallest_grid_value_first() -> None:
    # two trajectories, one wrong write at p 0.6, one at p 0.95: the grid is
    # sorted ascending, and the smallest lambda satisfying alpha wins.
    low_wrong = _step(correct=False)
    high_wrong = _step(correct=False)
    steps = {0: [low_wrong], 1: [high_wrong]}
    p_hats = {0: [0.6], 1: [0.95]}
    lam = choose_lambda(steps, p_hats, alpha=0.5)
    # N=2: at lam=0.6 mean loss is 1.0 -> bound 2/3+1/3=1.0 > 0.5;
    # at lam=0.95 mean loss 0.5 -> bound (2/3)*0.5+1/3 = 2/3 > 0.5;
    # at lam=1.0 mean loss 0.0 -> bound 1/3 <= 0.5.
    assert lam == 1.0


def test_gate05_approvals_and_expected() -> None:
    steps = [
        _step(tier="read"),
        _step(tier="write", p_hat=0.5),
        _step(tier="write", p_hat=0.99),
        _step(tier="irreversible"),
    ]
    assert approvals_needed(steps, [0.9, 0.5, 0.99, 0.9], 0.9) == 2
    assert expected_approvals({0: steps}, {0: [0.9, 0.5, 0.99, 0.9]}, 0.9) == 2.0
    assert expected_approvals({}, {}, 0.9) == 0.0


def test_gate06_confirm_all_policy() -> None:
    policy = ConfirmAllPolicy()
    assert policy.needs_signals is False
    assert policy.decide(_step(tier="write")).action == "ask"
    assert policy.decide(_step(tier="irreversible")).action == "ask"
    assert policy.decide(_step(tier="read")).action == "act"


def test_gate07_fixed_threshold_boundaries_and_none() -> None:
    policy = FixedThresholdPolicy()
    assert FIXED_THRESHOLD == 0.7
    assert policy.decide(_step(verbalized=0.7)).action == "act"
    ask = policy.decide(_step(verbalized=0.69))
    assert ask.action == "ask"
    assert ask.p_hat == 0.69
    assert policy.decide(_step(verbalized=None)).action == "ask"


def test_gate08_calibrated_policy_boundaries_and_none() -> None:
    policy = CalibratedPolicy(lam=0.9)
    assert policy.decide(_step(p_hat=0.9)).action == "act"
    assert policy.decide(_step(p_hat=0.89)).action == "ask"
    assert policy.decide(_step(p_hat=None)).action == "ask"


def test_gate09_irreversible_always_asks_in_every_policy() -> None:
    record = _step(tier="irreversible", verbalized=1.0, p_hat=1.0)
    assert ConfirmAllPolicy().decide(record).action == "ask"
    assert FixedThresholdPolicy().decide(record).action == "ask"
    assert CalibratedPolicy(lam=0.01).decide(record).action == "ask"


def test_gate10_make_policy_dispatch() -> None:
    assert isinstance(make_policy("confirm_all"), ConfirmAllPolicy)
    assert isinstance(make_policy("fixed_threshold"), FixedThresholdPolicy)
    assert isinstance(make_policy("calibrated", lam=0.5), CalibratedPolicy)
    with pytest.raises(ValueError, match="lambda"):
        make_policy("calibrated")
    with pytest.raises(ValueError, match="unknown policy"):
        make_policy("nope")


def test_gate11_gate_decision_is_decoupled_from_verification() -> None:
    import nitelos
    import nitelos.gate as gate_module

    decision = GateDecision(policy="confirm_all", action="ask", reason="x")
    assert gate_module.__name__ not in (m for m in ())
    # no shared base with the verification result types
    assert not isinstance(decision, nitelos.VerificationResult)
    assert "VerificationResult" not in dir(gate_module)
    assert TIER_VALUES == ("write", "irreversible")
    assert ALPHAS == (0.02, 0.05, 0.10, 0.20)


def test_gate11b_missing_extra_is_actionable_not_import_error() -> None:
    pytest.importorskip("builtins")  # always present; numpy check below inverts
    try:
        numpy = __import__("importlib").import_module("numpy")
    except ImportError:
        numpy = None
    if numpy is not None:
        pytest.skip("numpy present: the gate extra is installed")
    from nitelos import gate

    with pytest.raises(gate.GateExtraRequired, match="Install the gate extra"):
        gate.TemperatureScaling().fit(_rows_dummy())


def _rows_dummy() -> list[dict[str, object]]:
    return [{"verbalized": 0.5, "agreement": 0.5, "tier": "write", "step_index": 0, "correct": True}]
