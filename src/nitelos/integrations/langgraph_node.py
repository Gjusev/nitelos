"""The LangGraph verification node (plan F9, NIT-025; extra ``langgraph``).

A ``verify_outcome`` node factory: :func:`verify_outcome_node` takes the
criteria (v0.1 wire form, host-authored — never derived from the agent's
messages) and an evidence provider callable that returns the evidence list
the HOST captured (typically by running collectors). The node verifies and
writes a :class:`NitelosVerification` into graph state under the
``nitelos`` key, preserving the incoming state. Routing is the graph
author's choice; :func:`route_on_decision` provides the default mapping
(success → "continue", failure → "interrupt", everything else → "abstain")
for conditional edges, and the failure→``interrupt()`` pairing is the
documented pattern (see the module tests for a working example graph).

The node NEVER raises: a failing provider or verifier becomes a
``backend_error`` verification in state (decision None) with safe codes
only — a graph stays debuggable instead of crashing mid-run. The result
object carries decision, execution_status, reason codes and evidence ids;
raw evidence values never enter it.

Graph-author notes: state schemas MUST be module-level TypedDicts —
langgraph serializes node/router function source for checkpointing and a
function-local class raises NameError at invoke time (verified against
langgraph 1.2.16). ``NitelosVerification.criterion_states`` is a tuple of
``(criterion_id, state)`` pairs.

Requires the ``langgraph`` extra; importing this module without the package
raises :class:`ImportError` naming the install command. Importing
``nitelos`` itself never loads langgraph.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from nitelos import Verifier
from nitelos.errors import RequestValidationError
from nitelos.schemas import parse_request

try:
    from langgraph.types import interrupt  # noqa: F401  # re-exported for graph authors
except ImportError as _exc:  # pragma: no cover - exercised via subprocess test
    raise ImportError(
        "nitelos.integrations.langgraph_node requires the langgraph extra; "
        'install it with: pip install "nitelos[langgraph]"'
    ) from None

__all__ = ["NitelosVerification", "route_on_decision", "verify_outcome_node"]


class NitelosVerification(BaseModel):
    """The graph-state summary of one verification (safe fields only)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    decision: str | None = None
    execution_status: str = "ok"
    reason_codes: tuple[str, ...] = ()
    evidence_ids: tuple[str, ...] = ()
    criterion_states: tuple[tuple[str, str], ...] = Field(default=())


def route_on_decision(decision: str | None) -> str:
    """Default routing: success continues, failure interrupts, else abstains."""
    if decision == "success":
        return "continue"
    if decision == "failure":
        return "interrupt"
    return "abstain"


def verify_outcome_node(
    *,
    criteria: Sequence[Mapping[str, Any]],
    evidence_provider: Callable[[], Sequence[Mapping[str, Any]]],
    checkpoint_id: str = "cp",
    verifier: Verifier | None = None,
) -> Callable[[Mapping[str, Any]], dict[str, Any]]:
    """Build a LangGraph node that verifies and updates state.

    ``criteria`` are v0.1 wire-form documents (host-authored).
    ``evidence_provider`` is called once per node execution and returns the
    evidence list (v0.1 wire form) the host captured. The node returns a
    state UPDATE (``{"nitelos": NitelosVerification}``) — LangGraph merges
    it; the incoming state is otherwise untouched.
    """
    effective_verifier = verifier if verifier is not None else Verifier()
    criteria_docs = [dict(criterion) for criterion in criteria]
    all_ids = {eid for criterion in criteria_docs for eid in criterion.get("evidence_ids", [])}

    def node(state: Mapping[str, Any]) -> dict[str, Any]:
        try:
            evidence = [dict(item) for item in evidence_provider()]
        except Exception:  # noqa: BLE001 - the node never raises
            return {
                "nitelos": NitelosVerification(
                    execution_status="backend_error",
                    reason_codes=("BACKEND_EXCEPTION",),
                )
            }
        collected = {str(item.get("id")) for item in evidence}
        maps = []
        for raw in criteria_docs:
            entry = dict(raw)
            entry["evidence_ids"] = [eid for eid in entry.get("evidence_ids", []) if eid in collected]
            maps.append(entry)
        document = {
            "schema_version": "1",
            "request_id": "langgraph-verify",
            "objective": "Verify the outcome the graph claimed",
            "checkpoint_id": checkpoint_id,
            "as_of": _now_iso(),
            "criteria": maps,
            "evidence": evidence,
            "metadata": {},
        }
        try:
            request = parse_request(json.dumps(document))
        except (RequestValidationError, ValueError, TypeError):
            return {
                "nitelos": NitelosVerification(
                    execution_status="input_error", reason_codes=("INVALID_SCHEMA",)
                )
            }
        result = effective_verifier.verify(request)
        summary = NitelosVerification(
            decision=str(result.decision) if result.decision is not None else None,
            execution_status=str(result.execution_status),
            reason_codes=tuple(sorted({str(code) for code in result.reason_codes})),
            evidence_ids=tuple(all_ids & collected),
            criterion_states=tuple((c.criterion_id, str(c.state)) for c in result.criteria),
        )
        return {"nitelos": summary}

    return node


def _now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")
