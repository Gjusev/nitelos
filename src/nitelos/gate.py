"""Pre-action act/ask gate, ported from gate-calibrated (plan F14, NIT-033).

Ported from the maintainer's `gate-calibrated` repository (MIT, copyright
2026 Gjusev); relicensed to Apache-2.0 by the copyright holder for nitelos
per ADR-017. Only the DECISION MATH was ported (calibrator, conformal
threshold, policies, shared types). The source's signal collection (model
calls through litellm, tau-bench middleware) is deliberately absent:
confidence signals arrive as NUMBERS supplied by the host, so nitelos still
never calls a model and opens no network. The tier map (read / write /
irreversible, plus the source's ungated "special") is host configuration,
like criteria; irreversible ALWAYS asks (the source repository's invariant).

The negative result ships with the code, as written in the source README:
risk control held on the live test split in point estimates (every
calibrated configuration kept the share of trajectories with an executed
wrong write at or under its alpha), but it did not beat the simple
alternatives: at alpha 0.10 and above the calibrated gate never asks on a
write step and is in practice the same policy as the fixed 0.7 threshold,
and at alpha 0.02 it removes wrong writes at a rate per extra approval
indistinguishable from confirming every write. The likely reason is the
signal: glm-5.3-flash stated a confidence of 0.9 or more on all 43 wrong
write steps in the collected data, so the calibrator's only useful feature
was the position of the step in the conversation. This is an experimental
research port, not a validated improvement.

The threshold and policy layers are pure Python. The calibrator layer
needs numpy, imported lazily (the ``gate`` extra); a missing dependency
raises :class:`GateExtraRequired` naming the install command instead of an
ImportError at import time. ``GateDecision`` and ``VerificationResult``
are separate types with no coupling (ADR-017 finding 4).
"""

from __future__ import annotations

import importlib
import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

__all__ = [
    "ALPHAS",
    "FIXED_THRESHOLD",
    "TIER_VALUES",
    "GateDecision",
    "GateExtraRequired",
    "StepRecord",
    "approvals_needed",
    "choose_lambda",
    "expected_approvals",
    "mean_loss",
    "trajectory_loss",
]

ALPHAS = (0.02, 0.05, 0.10, 0.20)
FIXED_THRESHOLD = 0.7
TIER_VALUES = ("write", "irreversible")


class GateExtraRequired(RuntimeError):
    """A numpy function is needed but the ``gate`` extra is not installed."""


def _import(name: str) -> Any:
    """Import NAME lazily; missing modules become an actionable error."""
    try:
        return importlib.import_module(name)
    except ImportError as exc:
        msg = (
            f"{name} is required for the gate calibrator but is not installed. "
            "Install the gate extra, e.g. `uv sync --extra gate` "
            "or `pip install 'nitelos[gate]'`."
        )
        raise GateExtraRequired(msg) from exc


@dataclass
class StepRecord:
    """One proposed action of the agent, with its tier, signals and label.

    The host fills ``verbalized``/``agreement`` (its own model calls produce
    them) and ``correct`` (its labels); the gate only consumes the numbers.
    """

    task_id: int
    split: str
    trial: int
    step_index: int
    tool_name: str
    kwargs: dict[str, Any]
    tier: str
    verbalized: float | None = None
    agreement: float | None = None
    correct: bool | None = None
    p_hat: float | None = None


@dataclass(frozen=True)
class GateDecision:
    """The decision of a policy for one StepRecord (safe fields only)."""

    policy: str
    action: str
    p_hat: float | None = None
    reason: str = ""


def trajectory_loss(steps: Sequence[StepRecord], p_hats: Sequence[float], lam: float) -> float:
    """1.0 if some write-tier step would have been executed (p_hat >= lam)
    and was wrong, else 0.0. Irreversible steps never execute unapproved,
    so they cannot produce loss; the scan short-circuits at the first hit."""
    for step, p in zip(steps, p_hats, strict=False):
        if step.tier == "write" and p >= lam and not step.correct:
            return 1.0
    return 0.0


def mean_loss(
    steps_by_traj: dict[int, Sequence[StepRecord]],
    p_hat_by_traj: dict[int, Sequence[float]],
    lam: float,
) -> float:
    losses = [trajectory_loss(steps_by_traj[t], p_hat_by_traj[t], lam) for t in steps_by_traj]
    return sum(losses) / len(losses) if losses else 1.0


def choose_lambda(
    steps_by_traj: dict[int, Sequence[StepRecord]],
    p_hat_by_traj: dict[int, Sequence[float]],
    alpha: float,
) -> float:
    """Smallest lambda on the observed p_hat grid satisfying the conformal bound.

    The rule picks the smallest lambda such that (N/(N+1)) * mean(L_t) +
    1/(N+1) <= alpha, where the unit is the trajectory, not the step.
    Returns 1.0 (ask always) if no lambda satisfies it, including the case
    N < 1/alpha - 1 where the bound is unreachable for any lambda.

    The guarantee's assumptions travel with it (ADR-017 finding 2, verbatim
    from the source README): "The risk guarantee assumes exchangeability
    between calibration and test trajectories and is computed on ungated
    runs; under the gate, a rejection changes the path the agent takes
    afterwards." And its perfect-oracle limitation: the evaluation's
    approving human was "a perfect oracle built from the gold actions of
    tau-bench. A real reviewer errs and tires."
    """
    n = len(steps_by_traj)
    if n == 0:
        return 1.0
    grid = sorted({1.0} | {p for ps in p_hat_by_traj.values() for p in ps})
    for lam in grid:
        bound = (n / (n + 1)) * mean_loss(steps_by_traj, p_hat_by_traj, lam) + 1 / (n + 1)
        if bound <= alpha:
            return lam
    return 1.0


def approvals_needed(steps: Sequence[StepRecord], p_hats: Sequence[float], lam: float) -> int:
    """Approvals a calibrated policy would have requested on a trajectory:
    every write step with p_hat < lambda, plus every irreversible step."""
    n = 0
    for step, p in zip(steps, p_hats, strict=False):
        if step.tier == "irreversible" or (step.tier == "write" and p < lam):
            n += 1
    return n


def expected_approvals(
    steps_by_traj: dict[int, Sequence[StepRecord]],
    p_hat_by_traj: dict[int, Sequence[float]],
    lam: float,
) -> float:
    vals = [approvals_needed(steps_by_traj[t], p_hat_by_traj[t], lam) for t in steps_by_traj]
    return sum(vals) / len(vals) if vals else 0.0


class ConfirmAllPolicy:
    """Ask on every write and irreversible action (no signals needed)."""

    name = "confirm_all"
    needs_signals = False

    def decide(self, record: StepRecord) -> GateDecision:
        if record.tier in TIER_VALUES:
            return GateDecision(policy=self.name, action="ask", reason="ask on every gated action")
        return GateDecision(policy=self.name, action="act", reason="not gated")


class FixedThresholdPolicy:
    """Ask if verbalized < threshold (default 0.7, a hand-picked tutorial
    value); irreversible always asks."""

    name = "fixed_threshold"
    needs_signals = True

    def __init__(self, threshold: float = FIXED_THRESHOLD) -> None:
        self.threshold = threshold

    def decide(self, record: StepRecord) -> GateDecision:
        if record.tier == "irreversible":
            return GateDecision(policy=self.name, action="ask", reason="irreversible always asks")
        if record.tier == "write":
            v = record.verbalized
            ask = v is None or v < self.threshold
            return GateDecision(
                policy=self.name,
                action="ask" if ask else "act",
                p_hat=v,
                reason=f"verbalized={v} {'<' if ask else '>='} {self.threshold}",
            )
        return GateDecision(policy=self.name, action="act", reason="not gated")


class CalibratedPolicy:
    """Ask if p_hat < lambda or irreversible."""

    name = "calibrated"
    needs_signals = True

    def __init__(self, lam: float) -> None:
        self.lam = lam

    def decide(self, record: StepRecord) -> GateDecision:
        if record.tier == "irreversible":
            return GateDecision(policy=self.name, action="ask", reason="irreversible always asks")
        if record.tier == "write":
            p = record.p_hat
            ask = p is None or p < self.lam
            return GateDecision(
                policy=self.name,
                action="ask" if ask else "act",
                p_hat=p,
                reason=f"p_hat={p} {'<' if ask else '>='} lambda={self.lam}",
            )
        return GateDecision(policy=self.name, action="act", reason="not gated")


def make_policy(name: str, lam: float | None = None) -> Any:
    if name == "confirm_all":
        return ConfirmAllPolicy()
    if name == "fixed_threshold":
        return FixedThresholdPolicy()
    if name == "calibrated":
        if lam is None:
            raise ValueError("calibrated policy needs lambda")
        return CalibratedPolicy(lam)
    raise ValueError(f"unknown policy {name!r}")


def _field(row: Any, name: str) -> Any:
    """Read a field from a StepRecord or a mapping row (hosts may keep
    recorded calibration data as plain dicts)."""
    if isinstance(row, dict):
        return row[name]
    return getattr(row, name)


def logit(p: float) -> float:
    """Clamped log-odds; inputs are kept inside (EPS, 1 - EPS)."""
    eps = 1e-6
    p = min(max(p, eps), 1 - eps)
    return math.log(p / (1 - p))


def _sigmoid(z: Any) -> Any:
    np = _import("numpy")
    return 1.0 / (1.0 + np.exp(-np.clip(z, -30, 30)))


def features_matrix(rows: Sequence[Any]) -> Any:
    """[logit(verbalized), agreement, is_irreversible, log1p(step_index)]."""
    np = _import("numpy")
    return np.array(
        [
            [
                logit(float(_field(r, "verbalized"))),
                float(_field(r, "agreement")),
                1.0 if _field(r, "tier") == "irreversible" else 0.0,
                math.log1p(int(_field(r, "step_index"))),
            ]
            for r in rows
        ]
    )


def labels_vector(rows: Sequence[Any]) -> Any:
    np = _import("numpy")
    return np.array([1.0 if _field(r, "correct") else 0.0 for r in rows])


def raw_verbalized(rows: Sequence[Any]) -> Any:
    """Uncalibrated baseline."""
    np = _import("numpy")
    return np.array([float(_field(r, "verbalized")) for r in rows], dtype=float)


class TemperatureScaling:
    """p_hat = sigmoid(logit(verbalized) / T), T fit by grid + bisection NLL."""

    name = "A_temperature_scaling"

    def __init__(self) -> None:
        self.T = 1.0

    def fit(self, rows: Sequence[Any]) -> TemperatureScaling:
        np = _import("numpy")
        p = np.clip(np.array([float(_field(r, "verbalized")) for r in rows], dtype=float), 1e-6, 1 - 1e-6)
        y = labels_vector(rows)
        z = np.log(p / (1 - p))

        def nll(t: float) -> float:
            q = _sigmoid(z / t)
            return float(-np.mean(y * np.log(q + 1e-12) + (1 - y) * np.log(1 - q + 1e-12)))

        ts = np.exp(np.linspace(math.log(0.05), math.log(20.0), 200))
        best = ts[int(np.argmin([nll(t) for t in ts]))]
        lo, hi = best / 1.1, best * 1.1
        for _ in range(60):
            m1, m2 = lo + (hi - lo) / 3, hi - (hi - lo) / 3
            if nll(m1) < nll(m2):
                hi = m2
            else:
                lo = m1
        self.T = 0.5 * (lo + hi)
        return self

    def predict_proba(self, rows: Sequence[Any]) -> Any:
        np = _import("numpy")
        p = np.clip(np.array([float(_field(r, "verbalized")) for r in rows], dtype=float), 1e-6, 1 - 1e-6)
        return _sigmoid(np.log(p / (1 - p)) / self.T)

    def to_json(self) -> dict[str, Any]:
        return {"variant": self.name, "T": float(self.T)}

    @classmethod
    def from_json(cls, blob: dict[str, Any]) -> TemperatureScaling:
        ts = cls()
        ts.T = float(blob["T"])
        return ts


class LogisticRegression:
    """IRLS with L2 regularization and standardized features (numpy only)."""

    name = "B_logistic_regression"

    def __init__(self, l2: float = 1.0) -> None:
        self.l2 = l2
        self.w: Any = None
        self.b = 0.0
        self.mu: Any = None
        self.sd: Any = None

    def fit(self, rows: Sequence[Any]) -> LogisticRegression:
        np = _import("numpy")
        x = features_matrix(rows)
        y = labels_vector(rows)
        self.mu = x.mean(axis=0)
        self.sd = x.std(axis=0) + 1e-9
        z = (x - self.mu) / self.sd
        z = np.hstack([z, np.ones((len(z), 1))])
        w = np.zeros(z.shape[1])
        lam = np.diag([self.l2] * (z.shape[1] - 1) + [0.0])
        for _ in range(50):
            q = _sigmoid(z @ w)
            grad = z.T @ (q - y) + lam @ w
            weight = np.clip(q * (1 - q), 1e-6, None)
            h = z.T @ (z * weight[:, None]) + lam
            try:
                step = np.linalg.solve(h, grad)
            except np.linalg.LinAlgError:
                break
            w_new = w - step
            if np.max(np.abs(w_new - w)) < 1e-8:
                w = w_new
                break
            w = w_new
        self.w = w
        return self

    def predict_proba(self, rows: Sequence[Any]) -> Any:
        np = _import("numpy")
        x = features_matrix(rows)
        z = (x - self.mu) / self.sd
        z = np.hstack([z, np.ones((len(z), 1))])
        return _sigmoid(z @ self.w)

    def to_json(self) -> dict[str, Any]:
        return {
            "variant": self.name,
            "w": [float(x) for x in self.w],
            "mu": [float(x) for x in self.mu],
            "sd": [float(x) for x in self.sd],
            "l2": self.l2,
        }

    @classmethod
    def from_json(cls, blob: dict[str, Any]) -> LogisticRegression:
        np = _import("numpy")
        lr = cls(l2=float(blob.get("l2", 1.0)))
        lr.w = np.array(blob["w"])
        lr.mu = np.array(blob["mu"])
        lr.sd = np.array(blob["sd"])
        return lr


def calibrator_from_json(blob: dict[str, Any]) -> Any:
    if blob["variant"] == TemperatureScaling.name:
        return TemperatureScaling.from_json(blob)
    if blob["variant"] == LogisticRegression.name:
        return LogisticRegression.from_json(blob)
    raise ValueError(f"unknown calibrator variant {blob['variant']!r}")
