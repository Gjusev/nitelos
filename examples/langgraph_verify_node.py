"""Verify an outcome inside a LangGraph graph (extra `langgraph`).

Runnable offline. A two-node graph verifies one criterion from host
evidence and routes on the decision: success reaches the end, failure
interrupts. Without the `langgraph` extra installed the example exits 0
after printing the gate requirements.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from typing import Any

from typing_extensions import TypedDict

try:
    from langgraph.graph import END, START, StateGraph
    from langgraph.types import interrupt
except ImportError:
    print("skip: install 'nitelos[langgraph]' to run this example")
    raise SystemExit(0) from None

from nitelos import canonical_json
from nitelos.integrations.langgraph_node import verify_outcome_node


class GraphState(TypedDict, total=False):
    """Module-level on purpose: langgraph checkpointing needs it resolvable."""

    nitelos: Any
    reached_end: bool


CRITERIA = [
    {
        "id": "deployed",
        "description": "The service reports deployed",
        "kind": "assertion",
        "scope": "observed_state",
        "evidence_ids": ["obs-deploy"],
        "subject": {"service": "billing"},
        "pointer": "/deployed",
        "operator": "equals",
        "expected": True,
    }
]


def _evidence() -> list[dict[str, Any]]:
    captured = (datetime.now(UTC) - timedelta(seconds=10)).isoformat().replace("+00:00", "Z")
    data = {"deployed": True}
    observation = {
        "id": "obs-deploy",
        "kind": "observation",
        "sequence": 0,
        "captured_at": captured,
        "checkpoint_id": "cp-demo",
        "source_id": "my-runner",
        "subject": {"service": "billing"},
        "phase": "final",
        "channel": "dom",
        "data": data,
    }
    observation["sha256"] = hashlib.sha256(canonical_json(data).encode("utf-8")).hexdigest()
    return [observation]


def _finish(state: GraphState) -> GraphState:
    return {"reached_end": True}


def _guard(state: GraphState) -> GraphState:
    node = verify_outcome_node(criteria=CRITERIA, evidence_provider=_evidence, checkpoint_id="cp-demo")
    update = node(state)
    if update["nitelos"].decision == "failure":
        interrupt({"reason": "verification failed"})
    return update


def main() -> int:
    graph = (
        StateGraph(GraphState)
        .add_node("verify", _guard)
        .add_node("finish", _finish)
        .add_edge(START, "verify")
        .add_edge("verify", "finish")
        .add_edge("finish", END)
        .compile()
    )
    result = graph.invoke({})
    print(f"decision: {result['nitelos'].decision}")
    print(f"reason codes: {result['nitelos'].reason_codes}")
    print(f"reached_end: {result['reached_end']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
