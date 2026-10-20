"""EX: verify an Inspect AI task's outcome with nitelos (F8, offline).

A tiny Inspect ``Task`` whose solver simulates an agent that (a) claims the
deployment succeeded and (b) leaves the real deployment record behind as
evidence (what a collector-backed tool would store). The nitelos scorer then
verifies the CLAIM against the EVIDENCE, not against the agent's own words:
``build_task(claim=..., actual_status=...)`` lets you replay both the honest
and the over-claiming agent. Run pieces directly with ``run_solver_on_sample``
and ``score_state`` (offline, no model, no eval loop); a full ``eval`` run
needs a model and is out of this example's scope.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any

from inspect_ai import Task
from inspect_ai.dataset import Sample
from inspect_ai.scorer import Target
from inspect_ai.solver import TaskState

from nitelos import Evidence, TrustBinding
from nitelos.integrations.inspect_scorer import NITELOS_EVIDENCE_KEY, nitelos_scorer


def _captured_at() -> str:
    """Fresh timestamp (10 s ago) so the 300 s freshness gate always passes."""
    return (datetime.now(UTC) - timedelta(seconds=10)).isoformat().replace("+00:00", "Z")


SUBJECT = {"repo": "example/app"}


def _criteria() -> list[dict[str, Any]]:
    return [
        {
            "id": "c-deployed",
            "description": "The deployment record reports status=deployed",
            "kind": "assertion",
            "scope": "external",
            "evidence_ids": ["obs-deploy-1"],
            "subject": dict(SUBJECT),
            "pointer": "/status",
            "operator": "equals",
            "expected": "deployed",
        }
    ]


def _evidence(actual_status: str) -> dict[str, Any]:
    item = Evidence.observation(
        id="obs-deploy-1",
        sequence=0,
        captured_at=_captured_at(),
        checkpoint_id="cp-example",
        source_id="deployment-status",
        subject=dict(SUBJECT),
        phase="final",
        channel="external_api",
        data={"status": actual_status},
    )
    return item.model_dump(mode="json")


def _binding(actual_status: str) -> TrustBinding:
    item = Evidence.observation(
        id="obs-deploy-1",
        sequence=0,
        captured_at=_captured_at(),
        checkpoint_id="cp-example",
        source_id="deployment-status",
        subject=dict(SUBJECT),
        phase="final",
        channel="external_api",
        data={"status": actual_status},
    )
    return TrustBinding(
        evidence_id="obs-deploy-1",
        sha256=item.sha256,
        source_id="deployment-status",
        subject=dict(SUBJECT),
        checkpoint_id="cp-example",
    )


def build_task(*, claim: str, actual_status: str) -> Task:
    """One-sample task: the agent's claim vs the record the task captured."""
    sample = Sample(
        input=f"Deploy the service. Report: {claim}",
        target="status is deployed",
        metadata={
            "nitelos_criteria": _criteria(),
            "nitelos_subject": dict(SUBJECT),
            "nitelos_checkpoint_id": "cp-example",
            "nitelos_request_id": "req-example-1",
            "actual_status": actual_status,
        },
    )

    async def solve(state: TaskState) -> TaskState:
        actual = str(state.metadata.get("actual_status", "unknown"))
        # the tool's real record (what a collector-backed tool would store)
        state.store.set(NITELOS_EVIDENCE_KEY, [_evidence(actual)])
        # the agent's own words: context only, never evidence
        state.completed = True
        return state

    scorer = nitelos_scorer(trust_bindings=(_binding(actual_status),))
    return Task(dataset=[sample], solver=solve, scorer=scorer)


def run_solver_on_sample(task: Task, sample: Any) -> TaskState:
    """Run the task's solver on its sample offline (no model, no eval loop)."""
    state = TaskState(
        model="test/model",
        sample_id=1,
        epoch=1,
        input=sample.input,
        messages=[],
        metadata=dict(sample.metadata or {}),
    )
    return asyncio.run(task.solver(state))


def score_state(task: Task, state: TaskState) -> Any:
    """Run the task's scorer on the state offline."""
    scorer = task.scorer[0] if isinstance(task.scorer, list) else task.scorer
    target = Target(str(task.dataset[0].target or ""))
    return asyncio.run(scorer(state, target))


if __name__ == "__main__":
    for claim, actual in (("deployment succeeded", "deployed"), ("deployment succeeded", "failed")):
        task = build_task(claim=claim, actual_status=actual)
        (sample,) = task.dataset
        score = score_state(task, run_solver_on_sample(task, sample))
        print(f"claim={claim!r} actual={actual!r} -> {score.value} ({score.explanation})")
