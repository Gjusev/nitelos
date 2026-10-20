"""Subprocess runner for the inspect scorer tests (v0.1 async precedent).

The conftest denies sockets to ordinary tests; a Windows proactor event loop
needs a loopback self-pipe, so the async scorer runs here instead, driven by
a JSON scenario on stdin, and prints a JSON result on stdout.
"""

from __future__ import annotations

import asyncio
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT / "src"))

from nitelos import Evidence, TrustBinding  # noqa: E402


def _captured_at() -> str:
    """Fresh timestamp (10 s ago) so the 300 s freshness gate always passes."""
    return (datetime.now(UTC) - timedelta(seconds=10)).isoformat().replace("+00:00", "Z")


def _evidence(status: str, evidence_id: str = "obs-1", checkpoint_id: str = "cp-inspect") -> dict:
    item = Evidence.observation(
        id=evidence_id,
        sequence=0,
        captured_at=_captured_at(),
        checkpoint_id=checkpoint_id,
        source_id="deployment-status",
        subject={"repo": "example/app"},
        phase="final",
        channel="external_api",
        data={"status": status},
    )
    return item.model_dump(mode="json")


def _bindings(status: str, checkpoint_id: str = "cp-inspect") -> list[dict]:
    item = Evidence.observation(
        id="obs-1",
        sequence=0,
        captured_at=_captured_at(),
        checkpoint_id=checkpoint_id,
        source_id="deployment-status",
        subject={"repo": "example/app"},
        phase="final",
        channel="external_api",
        data={"status": status},
    )
    binding = TrustBinding(
        evidence_id="obs-1",
        sha256=item.sha256,
        source_id="deployment-status",
        subject={"repo": "example/app"},
        checkpoint_id=checkpoint_id,
    )
    return [binding.model_dump(mode="json")]


def _criteria(pointer: str = "/status", expected: object = "deployed") -> list[dict]:
    return [
        {
            "id": "c-status",
            "description": "The deployment record reports the expected status",
            "kind": "assertion",
            "scope": "external",
            "evidence_ids": ["obs-1"],
            "subject": {"repo": "example/app"},
            "pointer": pointer,
            "operator": "equals",
            "expected": expected,
        }
    ]


def main() -> int:
    scenario = json.loads(sys.stdin.read())
    from nitelos import TrustBinding as TB
    from nitelos.integrations.inspect_scorer import nitelos_scorer

    if "example" in scenario:
        # run the bundled example task offline and score its state
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "example_inspect_verify_task", ROOT / "examples" / "inspect_verify_task.py"
        )
        assert spec is not None
        assert spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        task = module.build_task(**scenario["example"])
        (sample,) = task.dataset
        state = module.run_solver_on_sample(task, sample)
        score = module.score_state(task, state)
        print(
            json.dumps(
                {
                    "value": score.value,
                    "explanation": score.explanation,
                    "metadata": score.metadata,
                }
            )
        )
        return 0

    status = scenario.get("status", "deployed")
    criteria = scenario["criteria"] if "criteria" in scenario else _criteria()
    evidence = scenario.get("evidence")
    if evidence is None:
        evidence = [_evidence(status, checkpoint_id=scenario.get("checkpoint_id", "cp-inspect"))]
    bindings = ()
    if scenario.get("bindings"):
        bindings = tuple(
            TB.model_validate(b) for b in _bindings(status, scenario.get("checkpoint_id", "cp-inspect"))
        )
    from inspect_ai.scorer import Target
    from inspect_ai.solver import TaskState

    state = TaskState(
        model="test/model",
        sample_id=scenario.get("sample_id", 1),
        epoch=1,
        input="deploy the service and report status",
        messages=[],
        metadata={
            "nitelos_criteria": criteria,
            "nitelos_subject": {"repo": "example/app"},
            "nitelos_checkpoint_id": scenario.get("checkpoint_id", "cp-inspect"),
            "nitelos_request_id": scenario.get("request_id", "req-inspect-1"),
        },
    )
    state.store.set("nitelos_evidence", evidence)
    scorer = nitelos_scorer(name=scenario.get("name", "nitelos"), trust_bindings=bindings)
    score = asyncio.run(scorer(state, Target("status is deployed")))
    print(
        json.dumps(
            {
                "value": score.value,
                "explanation": score.explanation,
                "metadata": score.metadata,
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
