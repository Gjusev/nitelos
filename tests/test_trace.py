"""TRC-01..04: schema-v1 trace ingestion, context view and parity (NIT-009).

Authority: docs/planning/11-glm-implementation-handoff.md ("Trace schema-v1, exact
minimum" — normative), 03 (Evidence, action.tool_result_id rules, limits, traces
pseudocode), 04 step 5 (context actions view), 07 (untrusted trace JSON), 12 (TRC
family). All expected values are literals; the action-context helper is pure.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

import pytest

from nitelos import ExecutionStatus, Verifier, canonical_json, parse_trace
from nitelos.context import ActionContextItem, select_action_context
from nitelos.errors import InputErrorCode, RequestValidationError
from nitelos.schemas import VerificationRequest
from test_contract import _action, _criterion, _observation, _request, _screenshot

SUBJECT = {"form": "registration-1"}


def _digest(payload: Any) -> str:
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def _obs(**over: Any) -> dict[str, Any]:
    over.setdefault("data", {"validation_error": True})
    over["sha256"] = _digest(over["data"])
    return _observation(**over)


def _act(**over: Any) -> dict[str, Any]:
    name = over.get("name", "submit-form")
    arguments = over.get("arguments", {"email": "x@example.test"})
    reported_status = over.get("reported_status", "completed")
    tool_result_id = over.get("tool_result_id")
    over["sha256"] = _digest(
        {
            "name": name,
            "arguments": arguments,
            "reported_status": reported_status,
            "tool_result_id": tool_result_id,
        }
    )
    return _action(**over)


def _trace(evidence: list[dict[str, Any]], metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    doc: dict[str, Any] = {"schema_version": "1", "evidence": evidence}
    if metadata is not None:
        doc["metadata"] = metadata
    return doc


def _tool_obs(evidence_id: str, sequence: int) -> dict[str, Any]:
    return _obs(id=evidence_id, sequence=sequence, channel="tool", data={"ok": True})


def assert_trace_error(data: Any, code: str, path: str | None = None) -> RequestValidationError:
    with pytest.raises(RequestValidationError) as excinfo:
        parse_trace(data)
    issues = excinfo.value.issues
    assert issues, "RequestValidationError carried no issues"
    first = issues[0]
    assert first.code == code, f"expected {code}, got {first.code} at {first.field_path}"
    if path is not None:
        assert first.field_path == path, f"expected path {path}, got {first.field_path}"
    return excinfo.value


# --------------------------------------------------------------------------
# TRC-01: ordered records round-trip
# --------------------------------------------------------------------------


def _multi_step_evidence() -> list[dict[str, Any]]:
    return [
        _act(id="act-open", sequence=0, name="open-form"),
        _act(id="act-fill", sequence=1, name="fill-email", tool_result_id="tool-fill"),
        _tool_obs("tool-fill", 2),
        _obs(id="obs-final", sequence=3, data={"validation_error": False}),
    ]


def test_trc01_round_trip_preserves_order_and_defaults() -> None:
    trace = parse_trace(_trace(_multi_step_evidence(), metadata={"run": "r-1"}))
    assert [item.id for item in trace.evidence] == ["act-open", "act-fill", "tool-fill", "obs-final"]
    assert dict(trace.metadata) == {"run": "r-1"}
    dumped = trace.model_dump(mode="json")
    assert dumped["schema_version"] == "1"
    assert [e["id"] for e in dumped["evidence"]] == ["act-open", "act-fill", "tool-fill", "obs-final"]
    reparsed = parse_trace(json.dumps(dumped))
    assert reparsed == trace
    assert dict(reparsed.metadata) == {"run": "r-1"}


def test_trc01_metadata_defaults_to_empty_object() -> None:
    trace = parse_trace(_trace([_action(sequence=0)]))
    assert dict(trace.metadata) == {}
    assert parse_trace(json.dumps(_trace([_action(sequence=0)]))) == trace


def test_trc01_empty_evidence_list_is_valid() -> None:
    trace = parse_trace(_trace([]))
    assert trace.evidence == ()


# --------------------------------------------------------------------------
# TRC-02: structural and wire-level input errors
# --------------------------------------------------------------------------


def test_trc02_tool_result_rules() -> None:
    # dangling reference
    assert_trace_error(
        _trace([_act(sequence=0, tool_result_id="ghost")]),
        InputErrorCode.UNKNOWN_REFERENCE,
        "$.evidence[0].tool_result_id",
    )
    # target exists but is not a tool-channel observation
    assert_trace_error(
        _trace([_act(sequence=0, tool_result_id="obs-1"), _obs(id="obs-1", sequence=1)]),
        InputErrorCode.UNKNOWN_REFERENCE,
        "$.evidence[0].tool_result_id",
    )
    # target sequence is not greater: the target is an earlier item with a lower
    # sequence (equal sequences are unreachable — ordering fires first)
    assert_trace_error(
        _trace([_tool_obs("tool-1", 0), _act(id="act-1", sequence=1, tool_result_id="tool-1")]),
        InputErrorCode.UNKNOWN_REFERENCE,
        "$.evidence[1].tool_result_id",
    )
    # legal: tool channel with a greater sequence
    parse_trace(_trace([_act(sequence=0, tool_result_id="tool-1"), _tool_obs("tool-1", 1)]))


def test_trc02_duplicate_ids_sequences_and_timestamps() -> None:
    assert_trace_error(
        _trace([_action(sequence=0), _action(id="act-1", sequence=1)]),
        InputErrorCode.DUPLICATE_ID,
        "$.evidence[1].id",
    )
    assert_trace_error(
        _trace([_action(sequence=1), _action(id="act-2", sequence=1)]),
        InputErrorCode.INVALID_SEQUENCE,
        "$.evidence[1].sequence",
    )
    assert_trace_error(
        _trace(
            [
                _observation(id="o1", sequence=0, captured_at="2024-06-01T10:00:00Z"),
                _observation(id="o2", sequence=1, captured_at="2024-06-01T09:59:00Z"),
            ]
        ),
        InputErrorCode.INVALID_TIMESTAMP,
        "$.evidence[1].captured_at",
    )
    # ties are allowed
    parse_trace(
        _trace(
            [
                _observation(id="o1", sequence=0, captured_at="2024-06-01T10:00:00Z"),
                _observation(id="o2", sequence=1, captured_at="2024-06-01T10:00:00Z"),
            ]
        )
    )


def test_trc02_future_timestamps_rejected_at_to_request_not_parse() -> None:
    future = "2025-01-01T00:00:00Z"
    trace = parse_trace(_trace([_observation(id="o1", sequence=0, captured_at=future)]))
    with pytest.raises(RequestValidationError) as excinfo:
        trace.to_request(
            objective="o",
            criteria=[_criterion(evidence_ids=["o1"], operator="equals", expected=True)],
            request_id="r",
            checkpoint_id="cp",
            as_of="2024-06-01T10:00:00Z",
        )
    assert excinfo.value.issues[0].code == InputErrorCode.INVALID_TIMESTAMP
    assert excinfo.value.issues[0].field_path == "$.evidence[0].captured_at"
    # with a later as_of the same trace converts fine
    request = trace.to_request(
        objective="o",
        criteria=[_criterion(evidence_ids=["o1"], operator="equals", expected=True)],
        request_id="r",
        checkpoint_id="cp",
        as_of=future,
    )
    assert isinstance(request, VerificationRequest)


def test_trc02_wire_level_discipline() -> None:
    assert_trace_error("{", InputErrorCode.INVALID_SCHEMA, "$")
    assert_trace_error("[]", InputErrorCode.INVALID_SCHEMA, "$")
    text = json.dumps(_trace([_action(sequence=0)], metadata={"a": 1}))[:-1] + ', "metadata": {"b": 2}}'
    assert_trace_error(text, InputErrorCode.INVALID_SCHEMA, "$.metadata")
    doc = _trace([_action(sequence=0)])
    doc["extra"] = 1
    assert_trace_error(doc, InputErrorCode.INVALID_SCHEMA, "$.extra")
    doc = _trace([_action(sequence=0)])
    doc["schema_version"] = "2"
    assert_trace_error(doc, InputErrorCode.UNSUPPORTED_SCHEMA, "$.schema_version")
    doc = _trace([_action(sequence=0)])
    del doc["schema_version"]
    assert_trace_error(doc, InputErrorCode.INVALID_SCHEMA, "$.schema_version")
    # unknown evidence kinds are rejected, never dropped
    doc = _trace([dict(_action(sequence=0), kind="replay")])
    assert_trace_error(doc, InputErrorCode.INVALID_SCHEMA, "$.evidence[0]")
    # limits: metadata over 8 KiB and payload over 64 KiB
    assert_trace_error(
        _trace([_observation(sequence=0)], metadata={"filler": "x" * 9000}),
        InputErrorCode.LIMIT_EXCEEDED,
        "$.metadata",
    )
    assert_trace_error(
        _trace([_observation(sequence=0, data={"filler": "y" * 66000})]),
        InputErrorCode.LIMIT_EXCEEDED,
        "$.evidence[0].data",
    )


# --------------------------------------------------------------------------
# TRC-03: tool completion and summaries never satisfy external/visual criteria
# --------------------------------------------------------------------------


def test_trc03_tool_completion_cannot_satisfy_external_criterion() -> None:
    trace = parse_trace(
        _trace(
            [
                _act(sequence=0),
                _tool_obs("tool-1", 1),
            ]
        )
    )
    request = trace.to_request(
        objective="Upload the file",
        criteria=[
            _criterion(
                id="stored",
                scope="external",
                evidence_ids=[],
                pointer="/status",
                operator="equals",
                expected="stored",
                subject=dict(SUBJECT),
            )
        ],
        request_id="r",
        checkpoint_id="cp",
        as_of="2024-06-01T10:00:00Z",
    )
    result = Verifier().verify(request)
    assert result.execution_status == ExecutionStatus.OK
    assert result.decision is not None
    assert result.decision.value == "abstained"
    assert result.criteria[0].reason_codes == ("MISSING_EVIDENCE",)


def test_trc03_action_cited_by_external_or_visual_criterion_is_unsupported() -> None:
    trace = parse_trace(_trace([_act(sequence=0)]))
    external_request = trace.to_request(
        objective="o",
        criteria=[
            _criterion(
                id="c",
                scope="external",
                evidence_ids=["act-1"],
                pointer="/reported_status",
                operator="equals",
                expected="completed",
                subject=dict(SUBJECT),
            )
        ],
        request_id="r",
        checkpoint_id="cp",
        as_of="2024-06-01T10:00:00Z",
    )
    result = Verifier().verify(external_request)
    assert result.execution_status == ExecutionStatus.INPUT_ERROR
    assert result.error is not None
    assert result.error.code == InputErrorCode.UNSUPPORTED_CAPABILITY
    assert result.error.field_path == "$.criteria[0].evidence"


def test_trc03_summary_metadata_cannot_authorize_anything() -> None:
    trace = parse_trace(
        _trace(
            [_act(sequence=0)],
            metadata={"summary": "task succeeded", "trusted": True, "external_status": "stored"},
        )
    )
    request = trace.to_request(
        objective="o",
        criteria=[
            _criterion(
                id="stored",
                scope="external",
                evidence_ids=[],
                pointer="/status",
                operator="equals",
                expected="stored",
                subject=dict(SUBJECT),
            )
        ],
        request_id="r",
        checkpoint_id="cp",
        as_of="2024-06-01T10:00:00Z",
    )
    result = Verifier().verify(request)
    assert result.decision is not None
    assert result.decision.value == "abstained"
    assert result.criteria[0].reason_codes == ("MISSING_EVIDENCE",)


# --------------------------------------------------------------------------
# TRC-04: bounded action-context view
# --------------------------------------------------------------------------


def _context_evidence() -> tuple[Any, ...]:
    """Parsed models: an initial screenshot at sequence 0 and eleven actions at 1..11."""
    evidence = [_screenshot(id="shot-a", sequence=0)]
    evidence += [_act(id=f"act-{i}", sequence=i, name=f"step-{i}") for i in range(1, 12)]
    trace = parse_trace(_trace(evidence))
    return trace.evidence


def test_trc04_last_eight_actions_with_sequence_bound() -> None:
    items, omitted = select_action_context(_context_evidence(), max_image_sequence=10)
    # actions with sequence <= 10 are act-1..act-10; the last 8 are act-3..act-10
    assert [item.evidence_id for item in items] == [f"act-{i}" for i in range(3, 11)]
    assert [item.sequence for item in items] == list(range(3, 11))
    assert all(item.name == f"step-{i}" for i, item in zip(range(3, 11), items, strict=True))
    assert all(item.reported_status.value == "completed" for item in items)
    assert omitted == ("act-1", "act-2")
    # arguments never appear in the view: the item type has exactly these fields
    fields = set(ActionContextItem.__dataclass_fields__)
    assert fields == {"evidence_id", "sequence", "name", "reported_status"}


def test_trc04_actions_after_the_highest_cited_sequence_are_excluded() -> None:
    items, omitted = select_action_context(_context_evidence(), max_image_sequence=5)
    assert [item.evidence_id for item in items] == [f"act-{i}" for i in range(1, 6)]
    assert omitted == ()
    # act-6..act-11 (sequence > 5) are excluded by the sequence rule, not "omitted"


def test_trc04_limit_and_safe_repr() -> None:
    items, omitted = select_action_context(_context_evidence(), max_image_sequence=10, limit=3)
    assert [item.evidence_id for item in items] == ["act-8", "act-9", "act-10"]
    assert omitted == tuple(f"act-{i}" for i in range(1, 8))
    text = repr(items[0])
    assert "evidence_id='act-8'" in text
    assert "reported_status=completed" in text
    assert "step-8" not in text  # name is caller text and stays out of the repr


# --------------------------------------------------------------------------
# parity: identical results via direct request and imported trace
# --------------------------------------------------------------------------


def test_parity_direct_request_and_trace_import_agree() -> None:
    evidence = _multi_step_evidence()
    criteria = [
        _criterion(id="no-errors", evidence_ids=["obs-final"], operator="equals", expected=False),
        _criterion(
            id="submitted",
            scope="behavioral",
            evidence_ids=["act-fill"],
            pointer="/reported_status",
            operator="equals",
            expected="completed",
        ),
    ]
    direct = Verifier().verify(parse_direct(criteria, evidence))
    trace = parse_trace(_trace(evidence, metadata={"source": "caller-capture"}))
    imported = Verifier().verify(
        trace.to_request(
            objective="Complete registration",
            criteria=criteria,
            request_id="demo-1",
            checkpoint_id="cp",
            as_of="2024-06-01T10:00:00Z",
        )
    )
    assert direct.execution_status == imported.execution_status == ExecutionStatus.OK
    assert direct.decision == imported.decision
    assert [c.model_dump(exclude={"evidence_refs"}) for c in direct.criteria] == [
        c.model_dump(exclude={"evidence_refs"}) for c in imported.criteria
    ]
    assert direct.reason_codes == imported.reason_codes
    assert direct.verification_id != imported.verification_id


def parse_direct(criteria: list[dict[str, Any]], evidence: list[dict[str, Any]]) -> VerificationRequest:
    from nitelos import parse_request

    return parse_request(_request(criteria=criteria, evidence=evidence))


def test_to_request_rejects_dangling_criterion_references() -> None:
    trace = parse_trace(_trace([_observation(id="o1", sequence=0)]))
    with pytest.raises(RequestValidationError) as excinfo:
        trace.to_request(
            objective="o",
            criteria=[_criterion(evidence_ids=["ghost"], operator="equals", expected=True)],
            request_id="r",
            checkpoint_id="cp",
            as_of="2024-06-01T10:00:00Z",
        )
    assert excinfo.value.issues[0].code == InputErrorCode.UNKNOWN_REFERENCE
    assert excinfo.value.issues[0].field_path == "$.criteria[0].evidence_ids[0]"


def test_to_request_accepts_datetime_objects() -> None:
    trace = parse_trace(_trace([_observation(id="o1", sequence=0)]))
    request = trace.to_request(
        objective="o",
        criteria=[_criterion(evidence_ids=["o1"], operator="equals", expected=True)],
        request_id="r",
        checkpoint_id="cp",
        as_of=datetime(2024, 6, 1, 12, 0, tzinfo=UTC),
    )
    assert request.as_of == datetime(2024, 6, 1, 12, 0, tzinfo=UTC)
