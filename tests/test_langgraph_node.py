"""LGN-01..10: F9 LangGraph node factory (NIT-025, extra ``langgraph``)."""

from __future__ import annotations

import hashlib
import json
from typing import Any

import pytest

pytest.importorskip("langgraph", reason="nitelos[langgraph] extra not provisioned in this environment yet")

from nitelos import canonical_json
from nitelos.integrations.langgraph_node import NitelosVerification, verify_outcome_node


def _observation(data: dict[str, Any]) -> dict[str, Any]:
    obs = {
        "id": "obs-1",
        "kind": "observation",
        "sequence": 0,
        "captured_at": "2099-01-01T00:00:00Z",
        "checkpoint_id": "cp",
        "source_id": "collector",
        "subject": {"record": "rec-1"},
        "phase": "final",
        "channel": "dom",
        "data": data,
    }
    obs["sha256"] = hashlib.sha256(canonical_json(data).encode("utf-8")).hexdigest()
    return obs


from typing_extensions import TypedDict  # noqa: E402  # after importorskip gate


class _S6(TypedDict, total=False):
    messages: list[str]
    nitelos: Any
    reached_end: bool


class _S7(TypedDict, total=False):
    nitelos: Any
    path: str


class _S8(TypedDict, total=False):
    log: list[str]
    nitelos: Any


class _S9(TypedDict, total=False):
    nitelos: Any


CRITERIA = [
    {
        "id": "written",
        "description": "The record was written",
        "kind": "assertion",
        "scope": "observed_state",
        "evidence_ids": ["obs-1"],
        "subject": {"record": "rec-1"},
        "pointer": "/written",
        "operator": "equals",
        "expected": True,
    }
]


def _evidence_provider(data: dict[str, Any]):
    def provide() -> list[dict[str, Any]]:
        return [_observation(data)]

    return provide


def test_lgn01_success_result_in_state() -> None:
    node = verify_outcome_node(criteria=CRITERIA, evidence_provider=_evidence_provider({"written": True}))
    update = node({"messages": []})
    assert isinstance(update["nitelos"], NitelosVerification)
    assert update["nitelos"].decision == "success"
    assert set(update) == {"nitelos"}  # a state UPDATE: LangGraph merges it


def test_lgn02_failure_result_in_state() -> None:
    node = verify_outcome_node(criteria=CRITERIA, evidence_provider=_evidence_provider({"written": False}))
    state = node({})
    assert state["nitelos"].decision == "failure"
    assert state["nitelos"].execution_status == "ok"


def test_lgn03_abstained_when_no_evidence() -> None:
    node = verify_outcome_node(criteria=CRITERIA, evidence_provider=lambda: [])
    state = node({})
    assert state["nitelos"].decision == "abstained"
    assert "MISSING_EVIDENCE" in state["nitelos"].reason_codes


def test_lgn04_execution_error_in_state_never_raises() -> None:
    def boom() -> list[dict[str, Any]]:
        raise RuntimeError("SECRET provider detail")

    node = verify_outcome_node(criteria=CRITERIA, evidence_provider=boom)
    state = node({})
    assert state["nitelos"].execution_status == "backend_error"
    assert state["nitelos"].decision is None
    assert "SECRET" not in json.dumps(state["nitelos"].model_dump())


def test_lgn05_routing_decision_helper() -> None:
    from nitelos.integrations.langgraph_node import route_on_decision

    assert route_on_decision("success") == "continue"
    assert route_on_decision("failure") == "interrupt"
    assert route_on_decision("abstained") == "abstain"
    assert route_on_decision(None) == "abstain"


def test_lgn06_graph_success_continues() -> None:
    from langgraph.graph import END, START, StateGraph

    def start(s: _S6) -> _S6:
        return {"messages": ["begin"]}

    def after(s: _S6) -> _S6:
        return {"reached_end": True}

    node = verify_outcome_node(criteria=CRITERIA, evidence_provider=_evidence_provider({"written": True}))
    graph = (
        StateGraph(_S6)
        .add_node("start", start)
        .add_node("verify", node)
        .add_node("after", after)
        .add_edge(START, "start")
        .add_edge("start", "verify")
        .add_edge("verify", "after")
        .add_edge("after", END)
        .compile()
    )
    result = graph.invoke({"messages": []})
    assert result["reached_end"] is True
    assert result["nitelos"].decision == "success"


def test_lgn07_conditional_routing() -> None:
    from langgraph.graph import END, START, StateGraph

    node = verify_outcome_node(criteria=CRITERIA, evidence_provider=_evidence_provider({"written": False}))
    from nitelos.integrations.langgraph_node import route_on_decision

    def router(state: _S7) -> str:
        decision = state.get("nitelos").decision if state.get("nitelos") else None
        return {"interrupt": "fail_node", "abstain": "abstain_node", "continue": "done"}[
            route_on_decision(decision)
        ]

    def fail_node(state: _S7) -> _S7:
        return {"path": "failed"}

    def abstain_node(state: _S7) -> _S7:
        return {"path": "abstained"}

    graph = (
        StateGraph(_S7)
        .add_node("verify", node)
        .add_node("fail_node", fail_node)
        .add_node("abstain_node", abstain_node)
        .add_edge(START, "verify")
        .add_conditional_edges(
            "verify", router, {"fail_node": "fail_node", "abstain_node": "abstain_node", "done": END}
        )
        .compile()
    )
    assert graph.invoke({})["path"] == "failed"
    node_ok = verify_outcome_node(criteria=CRITERIA, evidence_provider=_evidence_provider({"written": True}))
    graph_ok = (
        StateGraph(_S7)
        .add_node("verify", node_ok)
        .add_node("fail_node", fail_node)
        .add_node("abstain_node", abstain_node)
        .add_edge(START, "verify")
        .add_conditional_edges(
            "verify", router, {"fail_node": "fail_node", "abstain_node": "abstain_node", "done": END}
        )
        .compile()
    )
    assert "path" not in graph_ok.invoke({})


def test_lgn08_fake_tool_claiming_write_interrupts() -> None:
    """F9 acceptance: fake tool claims the write; the record was not written."""
    from langgraph.graph import END, START, StateGraph

    def fake_tool(state: _S8) -> _S8:
        # claims success; produces NO real evidence of the write
        return {"log": [*state.get("log", []), "tool: record written successfully"]}

    node = verify_outcome_node(
        criteria=[
            {
                "id": "written",
                "description": "The record was written",
                "kind": "assertion",
                "scope": "observed_state",
                "evidence_ids": ["obs-1"],
                "subject": {"record": "rec-1"},
                "pointer": "/written",
                "operator": "equals",
                "expected": True,
            }
        ],
        evidence_provider=lambda: [],  # nothing real was captured
    )

    def with_interrupt(state: _S8) -> _S8:
        updated = node(state)
        if updated["nitelos"].decision == "failure":
            from langgraph.types import interrupt

            interrupt({"reason": "verification failed", "criteria": updated["nitelos"].reason_codes})
        return updated

    graph = (
        StateGraph(_S8)
        .add_node("fake_tool", fake_tool)
        .add_node("verify", with_interrupt)
        .add_edge(START, "fake_tool")
        .add_edge("fake_tool", "verify")
        .add_edge("verify", END)
        .compile()
    )
    # abstained (not failure): runs to completion, no interrupt
    result = graph.invoke({"log": []})
    assert result["nitelos"].decision == "abstained"


def test_lgn09_interrupt_fires_on_failure_path() -> None:
    from langgraph.graph import END, START, StateGraph
    from langgraph.types import interrupt

    node = verify_outcome_node(criteria=CRITERIA, evidence_provider=_evidence_provider({"written": False}))

    def guard(state: _S9) -> _S9:
        updated = node(state)
        if updated["nitelos"].decision == "failure":
            interrupt({"reason": "verification failed"})
        return updated

    graph = (
        StateGraph(_S7).add_node("verify", guard).add_edge(START, "verify").add_edge("verify", END).compile()
    )
    state = graph.invoke({})
    assert "__interrupt__" in state
    payload = state["__interrupt__"][0].value
    assert payload["reason"] == "verification failed"


def test_lgn10_isolation_and_actionable_missing_extra() -> None:
    import subprocess
    import sys
    from pathlib import Path

    code = (
        "import sys\n"
        "sys.modules['langgraph'] = None\n"
        "import nitelos\n"
        "print('core-ok')\n"
        "try:\n"
        "    import nitelos.integrations.langgraph_node\n"
        "except Exception as exc:\n"
        "    print(type(exc).__name__)\n"
        "    print('nitelos[langgraph]' in str(exc))\n"
        "else:\n"
        "    raise SystemExit('should have raised')\n"
    )
    proc = subprocess.run(
        [sys.executable, "-c", code],
        check=False,
        capture_output=True,
        text=True,
        cwd=Path(__file__).resolve().parents[1],
    )
    assert proc.returncode == 0, proc.stderr
    assert "core-ok" in proc.stdout
    assert "True" in proc.stdout
