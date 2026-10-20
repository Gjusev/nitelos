"""DEV-01..07: F10 DeepEval metric (NIT-026, extra ``deepeval``)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from nitelos import Verifier, canonical_json, parse_request

ROOT = Path(__file__).resolve().parents[1]

pytest.importorskip("deepeval", reason="nitelos[deepeval] extra not provisioned in this environment yet")

from nitelos.integrations.deepeval_metric import NitelosOutcomeMetric  # noqa: E402


def _result(kind: str) -> Any:
    if kind == "success":
        request = {
            "schema_version": "1",
            "request_id": "d-1",
            "objective": "x",
            "checkpoint_id": "cp",
            "as_of": "2099-01-01T00:00:00Z",
            "criteria": [
                {
                    "id": "c1",
                    "description": "d",
                    "kind": "assertion",
                    "scope": "observed_state",
                    "evidence_ids": ["obs"],
                    "subject": {"s": "1"},
                    "pointer": "/ok",
                    "operator": "equals",
                    "expected": True,
                }
            ],
            "evidence": [],
        }
        import hashlib
        import json

        observation = {
            "id": "obs",
            "kind": "observation",
            "sequence": 0,
            "captured_at": "2099-01-01T00:00:00Z",
            "checkpoint_id": "cp",
            "source_id": "t",
            "subject": {"s": "1"},
            "phase": "final",
            "channel": "dom",
            "data": {"ok": True},
        }
        observation["sha256"] = hashlib.sha256(
            canonical_json(observation["data"]).encode("utf-8")
        ).hexdigest()
        request["evidence"] = [observation]
        return Verifier().verify(parse_request(json.dumps(request)))
    if kind == "failure":
        return Verifier().verify({"schema_version": "1", "bogus": True})  # input_error path
    if kind == "abstained":
        request = {
            "schema_version": "1",
            "request_id": "d-2",
            "objective": "x",
            "checkpoint_id": "cp",
            "as_of": "2099-01-01T00:00:00Z",
            "criteria": [
                {
                    "id": "c2",
                    "description": "d",
                    "kind": "assertion",
                    "scope": "external",
                    "evidence_ids": [],
                    "subject": {"s": "1"},
                    "pointer": "/x",
                    "operator": "equals",
                    "expected": 1,
                }
            ],
            "evidence": [],
        }
        return Verifier().verify(parse_request(json.dumps(request)))
    raise AssertionError(kind)


def test_dev01_success_scores_one() -> None:
    metric = NitelosOutcomeMetric(lambda: _result("success"))
    score = metric.measure(None)
    assert score == 1.0
    assert metric.is_successful is True
    assert metric.score == 1.0


def test_dev02_execution_error_scores_zero_not_success() -> None:
    metric = NitelosOutcomeMetric(lambda: _result("failure"))
    score = metric.measure(None)
    assert score == 0.0
    assert metric.is_successful is False
    assert "input_error" in metric.reason
    assert "decision" in metric.reason


def test_dev03_abstention_is_never_a_pass_with_distinct_reason() -> None:
    metric = NitelosOutcomeMetric(lambda: _result("abstained"))
    score = metric.measure(None)
    assert score == 0.0
    assert metric.is_successful is False
    assert metric.reason.startswith("abstained")
    assert "MISSING_EVIDENCE" in metric.reason
    assert metric.reason != "success"


def test_dev04_deterministic_mapping() -> None:
    for kind in ("success", "failure", "abstained"):
        first = NitelosOutcomeMetric(lambda k=kind: _result(k))
        second = NitelosOutcomeMetric(lambda k=kind: _result(k))
        first.measure(None)
        second.measure(None)
        assert first.score == second.score
        assert first.reason == second.reason


def test_dev05_scores_are_only_zero_or_one() -> None:
    for kind in ("success", "failure", "abstained"):
        metric = NitelosOutcomeMetric(lambda k=kind: _result(k))
        metric.measure(None)
        assert metric.score in (0.0, 1.0)


def test_dev06_isolation_and_actionable_missing_extra() -> None:
    code = (
        "import sys\n"
        'sys.modules["deepeval"] = None\n'
        "import nitelos\n"
        'print("core-ok")\n'
        "try:\n"
        "    import nitelos.integrations.deepeval_metric\n"
        "except Exception as exc:\n"
        "    print(type(exc).__name__)\n"
        '    print("nitelos[deepeval]" in str(exc))\n'
        "else:\n"
        '    raise SystemExit("should have raised")\n'
    )
    proc = subprocess.run([sys.executable, "-c", code], check=False, capture_output=True, text=True, cwd=ROOT)
    assert proc.returncode == 0, proc.stderr
    assert "core-ok" in proc.stdout
    assert "True" in proc.stdout
