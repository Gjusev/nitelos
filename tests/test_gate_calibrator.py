"""GATE-12..14: the gate calibrator layer (needs numpy, the ``gate`` extra).

Synthetic labeled records only (ADR-017 finding 3).
"""

from __future__ import annotations

import math
from typing import Any

import pytest

numpy = pytest.importorskip("numpy", reason="nitelos[gate] extra not provisioned in this environment yet")

from nitelos.gate import (  # noqa: E402
    LogisticRegression,
    TemperatureScaling,
    calibrator_from_json,
    features_matrix,
    labels_vector,
    logit,
    raw_verbalized,
)


def _rows(n: int, verbalized: float, correct_rate: float) -> list[dict[str, Any]]:
    rows = []
    for i in range(n):
        rows.append(
            {
                "verbalized": verbalized,
                "agreement": 1.0 if i % 2 else 0.5,
                "tier": "irreversible" if i % 4 == 0 else "write",
                "step_index": i,
                "correct": (i / max(n - 1, 1)) < correct_rate,
            }
        )
    return rows


def test_gate12_temperature_scaling_recalibrates_overconfidence() -> None:
    rows = _rows(60, 0.9, 0.5)
    ts = TemperatureScaling().fit(rows)
    assert ts.T > 1.0
    p = ts.predict_proba(rows)
    assert p.mean() == pytest.approx(0.5, abs=0.15)
    blob = ts.to_json()
    assert blob["variant"] == "A_temperature_scaling"
    restored = calibrator_from_json(blob)
    assert isinstance(restored, TemperatureScaling)
    assert restored.predict_proba(rows).mean() == pytest.approx(p.mean(), abs=1e-9)


def test_gate13_logistic_regression_separates_and_round_trips() -> None:
    confident_right = [
        {"verbalized": 0.95, "agreement": 1.0, "tier": "write", "step_index": 2, "correct": True}
        for _ in range(30)
    ]
    unconfident_wrong = [
        {"verbalized": 0.3, "agreement": 0.0, "tier": "write", "step_index": 9, "correct": False}
        for _ in range(30)
    ]
    rows = confident_right + unconfident_wrong
    lr = LogisticRegression().fit(rows)
    p = lr.predict_proba(rows)
    assert p[:30].mean() > 0.8
    assert p[30:].mean() < 0.2
    blob = lr.to_json()
    restored = calibrator_from_json(blob)
    assert numpy.allclose(restored.predict_proba(rows), p)
    with pytest.raises(ValueError, match="unknown calibrator"):
        calibrator_from_json({"variant": "C_mystery"})


def test_gate14_feature_helpers() -> None:
    rows = [
        {"verbalized": 0.5, "agreement": 1.0, "tier": "irreversible", "step_index": 3, "correct": True},
        {"verbalized": 0.25, "agreement": 0.0, "tier": "write", "step_index": 0, "correct": False},
    ]
    x = features_matrix(rows)
    assert x.shape == (2, 4)
    assert x[0, 2] == 1.0
    assert x[1, 2] == 0.0
    assert x[0, 3] == math.log1p(3)
    assert x[1, 0] == logit(0.25)
    assert list(labels_vector(rows)) == [1.0, 0.0]
    assert list(raw_verbalized(rows)) == [0.5, 0.25]
