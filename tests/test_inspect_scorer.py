"""INS-01..09: F8 Inspect AI scorer (NIT-024, extra ``nitelos[inspect]``).

Offline: the async scorer runs in a subprocess (tests/_inspect_runner.py —
the v0.1 pattern for Windows, where a proactor event loop needs a loopback
self-pipe the offline conftest denies). The missing-extra case is simulated
with the sys.modules[...]=None subprocess pattern. The scorer tests require
inspect-ai in the dev environment (same flow as the otel extra); verified
locally with ``uv run --with inspect-ai``.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "tests" / "_inspect_runner.py"

_SUBPROCESS_CODE = (
    "import sys\n"
    'sys.modules["inspect_ai"] = None\n'
    "import nitelos\n"
    'print("core-ok")\n'
    "try:\n"
    "    import nitelos.integrations.inspect_scorer\n"
    "except Exception as exc:\n"
    "    print(type(exc).__name__)\n"
    '    print("nitelos[inspect]" in str(exc))\n'
    "else:\n"
    '    raise SystemExit("should have raised")\n'
)

pytest.importorskip("inspect_ai", reason="nitelos[inspect] extra required for the scorer tests")


_CRITERIA = [
    {
        "id": "c-status",
        "description": "The deployment record reports the expected status",
        "kind": "assertion",
        "scope": "external",
        "evidence_ids": ["obs-1"],
        "subject": {"repo": "example/app"},
        "pointer": "/status",
        "operator": "equals",
        "expected": "deployed",
    }
]


def _run(scenario: dict[str, Any]) -> dict[str, Any]:
    proc = subprocess.run(
        [sys.executable, str(RUNNER)],
        input=json.dumps(scenario),
        check=True,
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    return json.loads(proc.stdout)


def _needs_inspect_ai() -> None:
    try:
        import inspect_ai  # noqa: F401
    except ImportError:
        pytest.skip("inspect-ai not installed in this environment")


# --------------------------------------------------------------------------
# INS-01: isolation
# --------------------------------------------------------------------------


def test_ins01_missing_extra_is_actionable_and_core_stays_clean() -> None:
    proc = subprocess.run(
        [sys.executable, "-c", _SUBPROCESS_CODE],
        check=False,
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    assert proc.returncode == 0, proc.stderr
    assert "core-ok" in proc.stdout
    assert "ImportError" in proc.stdout
    assert "True" in proc.stdout


# --------------------------------------------------------------------------
# INS-02..04: the score mapping
# --------------------------------------------------------------------------


def test_ins02_success_failure_abstain_map_to_c_i_a() -> None:
    good = _run({"status": "deployed", "bindings": True})
    assert good["value"] == "C"
    bad = _run({"status": "failed", "bindings": True})
    assert bad["value"] == "I"
    unbound = _run({"status": "deployed"})  # no bindings -> abstained
    assert unbound["value"] == "A"
    assert "UNTRUSTED_EXTERNAL" in unbound["metadata"]["nitelos"]["reason_codes"]


def test_ins02b_abstain_is_excluded_from_nitelos_accuracy() -> None:
    from inspect_ai.scorer import Score, accuracy
    from inspect_ai.scorer._metric import SampleScore

    from nitelos.integrations.inspect_scorer import nitelos_accuracy

    scores = [
        SampleScore(score=Score(value="C", explanation="", metadata={})),
        SampleScore(score=Score(value="I", explanation="", metadata={})),
        SampleScore(score=Score(value="A", explanation="", metadata={})),  # our abstain
    ]
    assert nitelos_accuracy()(scores) == 0.5  # C/(C+I); the A is excluded by design
    # documented contrast: stock accuracy() maps unknown values to 0.0 and
    # keeps them in the denominator, counting an abstention like a failure
    assert accuracy()(scores) == pytest.approx(1 / 3)


def test_ins03_score_metadata_carries_reasons_limitations_fingerprints() -> None:
    import hashlib

    from nitelos import canonical_json

    bad = _run({"status": "failed", "bindings": True})
    meta = bad["metadata"]["nitelos"]
    assert meta["decision"] == "failure"
    assert "CRITERION_REFUTED" in meta["reason_codes"]
    assert isinstance(meta["limitation_codes"], list)
    expected = hashlib.sha256(canonical_json({"status": "failed"}).encode("utf-8")).hexdigest()
    assert meta["evidence_fingerprints"] == [expected]
    assert meta["execution_status"] == "ok"


def test_ins04_missing_criteria_metadata_is_a_loud_configuration_error() -> None:
    proc = subprocess.run(
        [sys.executable, str(RUNNER)],
        input=json.dumps({"criteria": []}),
        check=False,
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    assert proc.returncode != 0
    assert "KeyError" in proc.stderr or "criteria" in proc.stderr


def test_ins04b_dangling_citation_scores_a_not_a_crash() -> None:
    # probe 1 (review): criteria cite obs-1 but the store lacks it -> the
    # PRIMARY honest-abstention scenario must score A, never a traceback
    dangling = _run(
        {
            "criteria": _CRITERIA,  # cites obs-1
            "evidence": [],  # agent captured nothing
        }
    )
    assert dangling["value"] == "A"
    assert "MISSING_EVIDENCE" in dangling["metadata"]["nitelos"]["reason_codes"]


def test_ins04c_malformed_agent_evidence_scores_a_not_a_crash() -> None:
    # probe 2 (review): malformed agent-written evidence in the store ->
    # A with INVALID_SCHEMA; only author-level criteria faults stay loud
    malformed = _run(
        {
            "criteria": _CRITERIA,
            "evidence": [{"id": "obs-1", "kind": "observation", "bogus_field": True}],
        }
    )
    assert malformed["value"] == "A"
    assert malformed["metadata"]["nitelos"]["execution_status"] == "input_error"
    assert "INVALID_SCHEMA" in malformed["metadata"]["nitelos"]["reason_codes"]


def test_ins04d_author_misconfiguration_stays_loud() -> None:
    # broken criteria (missing required field) -> loud crash, not a silent A
    proc = subprocess.run(
        [sys.executable, str(RUNNER)],
        input=json.dumps({"criteria": [{"id": "c-broken"}], "evidence": []}),
        check=False,
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    assert proc.returncode != 0
    assert "RequestValidationError" in proc.stderr or "ValidationError" in proc.stderr


def test_ins04b_no_citable_evidence_abstains_with_missing_evidence() -> None:
    # a criterion citing nothing + no stored evidence -> MISSING_EVIDENCE
    # abstention (criteria citing ids that are not declared raise loudly)
    empty = _run(
        {
            "criteria": [
                {
                    "id": "c-none",
                    "description": "No evidence is citable",
                    "kind": "assertion",
                    "scope": "external",
                    "evidence_ids": [],
                    "subject": {"repo": "example/app"},
                    "pointer": "/status",
                    "operator": "equals",
                    "expected": "deployed",
                }
            ],
            "evidence": [],
        }
    )
    assert empty["value"] == "A"
    assert "MISSING_EVIDENCE" in empty["metadata"]["nitelos"]["reason_codes"]


def test_ins04c_execution_error_maps_to_a_with_the_error_code() -> None:
    # a visual criterion on the default deterministic verifier: verify()
    # RETURNS an input_error result (UNSUPPORTED_CAPABILITY) — schema-level
    # mistakes in criteria documents raise loudly at parse instead
    broken = _run(
        {
            "criteria": [
                {
                    "id": "c-visual",
                    "description": "The banner is visible",
                    "kind": "visual",
                    "scope": "visual",
                    "evidence_ids": ["obs-1"],
                    "subject": {"repo": "example/app"},
                }
            ],
            "bindings": True,
        }
    )
    assert broken["value"] == "A"
    assert broken["metadata"]["nitelos"]["execution_status"] == "input_error"
    assert "UNSUPPORTED_CAPABILITY" in broken["metadata"]["nitelos"]["reason_codes"]


# --------------------------------------------------------------------------
# INS-05: request building
# --------------------------------------------------------------------------


def test_ins05_request_uses_checkpoint_and_request_id_from_metadata() -> None:
    result = _run(
        {
            "status": "deployed",
            "bindings": True,
            "checkpoint_id": "cp-custom",
            "request_id": "req-custom",
        }
    )
    assert result["value"] == "C"
    assert result["explanation"].startswith("nitelos success")


def test_ins05b_scorer_name_is_configurable() -> None:
    result = _run({"status": "deployed", "bindings": True, "name": "nitelos-strict"})
    assert result["value"] == "C"


# --------------------------------------------------------------------------
# INS-06..08: the bundled offline task
# --------------------------------------------------------------------------


def test_ins07_bundled_task_claim_vs_evidence_scores_incorrect() -> None:
    result = _run({"example": {"claim": "deployment succeeded", "actual_status": "failed"}})
    assert result["value"] == "I"  # the agent claimed success; evidence refutes


def test_ins08_bundled_task_honest_success_scores_correct() -> None:
    result = _run({"example": {"claim": "deployment succeeded", "actual_status": "deployed"}})
    assert result["value"] == "C"
    assert result["metadata"]["nitelos"]["reason_codes"] == ["ALL_CRITERIA_SUPPORTED"]


def test_ins09_example_module_exists_and_task_shape_is_sane() -> None:
    _needs_inspect_ai()
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "example_inspect_verify_task", ROOT / "examples" / "inspect_verify_task.py"
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    task = module.build_task(claim="x", actual_status="deployed")
    assert task.scorer is not None
    (sample,) = task.dataset
    assert sample.metadata is not None
    assert sample.metadata["nitelos_criteria"]
