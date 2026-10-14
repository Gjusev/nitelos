"""CON-01..04: strict domain contracts, safe parsing and schema snapshots (NIT-002).

Authority: docs/planning/03-domain-model-and-api.md (normative contract v1),
05-evidence-and-policies.md (reason ordering), 07-security-and-privacy.md (safe
errors/repr), 12-testing-and-ci.md (CON family).

Snapshot regeneration switch (documented, deliberate):
    NITELOS_UPDATE_SNAPSHOTS=1 uv run pytest tests/test_contract.py -k snapshot
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from subprocess import run
from sys import executable
from typing import Any

import pytest
from pydantic import ValidationError

import nitelos
from nitelos import (
    AbstentionReason,
    ActionEvidence,
    AssertionCriterion,
    BackendDescriptor,
    BackendErrorCode,
    BackendFinding,
    Basis,
    ColorConversion,
    ConfigurationError,
    CriterionEvaluation,
    CriterionResult,
    CriterionState,
    Decision,
    DecisionCode,
    Diagnostics,
    ErrorInfo,
    Evidence,
    EvidenceRef,
    ExecutionStatus,
    Grounding,
    InputErrorCode,
    LimitationCode,
    Measurements,
    ObservationEvidence,
    PreprocessingRecord,
    ReportedStatus,
    RequestValidationError,
    Scope,
    Score,
    ScoreKind,
    ScreenshotEvidence,
    VerificationRequest,
    VerificationResult,
    VisualCriterion,
    canonical_json,
    parse_request,
)

SCHEMA_DIR = Path(__file__).parent / "schemas"
TS = "2024-06-01T10:00:00Z"
TS_EARLIER = "2024-06-01T09:59:00Z"
SHA = "a" * 64
SENTINEL = "SENTINEL-DO-NOT-LEAK-0d92fz"

LEGAL_PAIRS = [
    (ExecutionStatus.OK, Decision.SUCCESS),
    (ExecutionStatus.OK, Decision.FAILURE),
    (ExecutionStatus.OK, Decision.ABSTAINED),
    (ExecutionStatus.INPUT_ERROR, None),
    (ExecutionStatus.BACKEND_ERROR, None),
]


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------


def _observation(**over: Any) -> dict[str, Any]:
    item: dict[str, Any] = {
        "id": "obs-1",
        "kind": "observation",
        "sequence": 0,
        "captured_at": TS,
        "checkpoint_id": "cp",
        "source_id": "collector",
        "subject": {"form": "registration-1"},
        "phase": "final",
        "sha256": SHA,
        "channel": "dom",
        "data": {"validation_error": True},
    }
    item.update(over)
    return item


def _action(**over: Any) -> dict[str, Any]:
    item: dict[str, Any] = {
        "id": "act-1",
        "kind": "action",
        "sequence": 1,
        "captured_at": TS,
        "checkpoint_id": "cp",
        "source_id": "agent",
        "subject": {"form": "registration-1"},
        "phase": "final",
        "sha256": SHA,
        "name": "submit-form",
        "arguments": {"email": "x@example.test"},
        "reported_status": "completed",
    }
    item.update(over)
    return item


def _screenshot(**over: Any) -> dict[str, Any]:
    item: dict[str, Any] = {
        "id": "shot-1",
        "kind": "screenshot",
        "sequence": 0,
        "captured_at": TS,
        "checkpoint_id": "cp",
        "source_id": "screen",
        "subject": {"form": "registration-1"},
        "phase": "final",
        "sha256": SHA,
        "artifact_id": "art-1",
        "media_type": "image/png",
        "width": 64,
        "height": 32,
    }
    item.update(over)
    return item


def _criterion(**over: Any) -> dict[str, Any]:
    item: dict[str, Any] = {
        "id": "no-errors",
        "description": "No validation error remains",
        "kind": "assertion",
        "scope": "observed_state",
        "evidence_ids": ["obs-1"],
        "subject": {"form": "registration-1"},
        "pointer": "/validation_error",
        "operator": "equals",
        "expected": False,
    }
    item.update(over)
    return item


_ASSERTION_ONLY = ("pointer", "operator", "expected")


def _visual_criterion(**over: Any) -> dict[str, Any]:
    item = {
        "id": "appearance",
        "description": "Completion banner visible",
        "kind": "visual",
        "scope": "visual",
        "evidence_ids": ["shot-1"],
        "subject": {"form": "registration-1"},
    }
    item.update(over)
    return item


def _request(**over: Any) -> dict[str, Any]:
    doc: dict[str, Any] = {
        "schema_version": "1",
        "request_id": "demo-1",
        "objective": "Complete registration",
        "checkpoint_id": "cp",
        "as_of": TS,
        "criteria": [_criterion()],
        "evidence": [_observation()],
        "metadata": {},
    }
    doc.update(over)
    return doc


def _visual_request(**over: Any) -> dict[str, Any]:
    return _request(criteria=[_visual_criterion()], evidence=[_screenshot()], **over)


def _diagnostics(**over: Any) -> Diagnostics:
    values: dict[str, Any] = {
        "package_version": "0.1.0",
        "schema_version": "1",
        "request_hash": None,
        "evidence_manifest_hash": None,
        "policy_id": "strict",
        "policy_version": "1",
        "policy_hash": "b" * 64,
        "backend": BackendDescriptor(id="deterministic", version="1"),
        "elapsed_ms": 1.0,
        "criterion_durations_ms": {},
        "omitted_context_ids": (),
        "preprocessing": (),
        "measurements": Measurements(),
        "limitations": (),
    }
    values.update(over)
    return Diagnostics(**values)


def _criterion_result(**over: Any) -> CriterionResult:
    values: dict[str, Any] = {
        "criterion_id": "no-errors",
        "state": CriterionState.SUPPORTED,
        "basis": Basis.DETERMINISTIC,
        "scope": Scope.OBSERVED_STATE,
        "evidence_refs": (),
        "reason_codes": (),
        "limitations": (),
        "evaluations": (),
    }
    values.update(over)
    return CriterionResult(**values)


def _result(**over: Any) -> VerificationResult:
    values: dict[str, Any] = {
        "schema_version": "1",
        "request_id": "demo-1",
        "verification_id": "0f14d0ab-860c-4fb2-a7e2-2c1c0e6b0d21",
        "execution_status": ExecutionStatus.OK,
        "decision": Decision.SUCCESS,
        "criteria": (_criterion_result(),),
        "reason_codes": (DecisionCode.ALL_CRITERIA_SUPPORTED,),
        "error": None,
        "diagnostics": _diagnostics(),
    }
    values.update(over)
    return VerificationResult(**values)


def assert_parse_error(data: Any, code: str, path: str | None = None) -> RequestValidationError:
    """parse_request must raise RequestValidationError whose first issue matches code/path."""
    with pytest.raises(RequestValidationError) as excinfo:
        parse_request(data)
    issues = excinfo.value.issues
    assert issues, "RequestValidationError carried no issues"
    first = issues[0]
    assert first.code == code, f"expected {code}, got {first.code} at {first.field_path}"
    if path is not None:
        assert first.field_path == path, f"expected path {path}, got {first.field_path}"
    return excinfo.value


# --------------------------------------------------------------------------
# CON-01: legal (execution_status, decision) pairs and result invariants
# --------------------------------------------------------------------------


@pytest.mark.parametrize(("status", "decision"), LEGAL_PAIRS)
def test_con01_legal_state_decision_pairs(status: ExecutionStatus, decision: Decision | None) -> None:
    error = None
    criteria: tuple[CriterionResult, ...] = (_criterion_result(),)
    if status == ExecutionStatus.INPUT_ERROR:
        criteria = ()
        error = ErrorInfo(code=InputErrorCode.INVALID_SCHEMA, safe_message="invalid request")
    elif status == ExecutionStatus.BACKEND_ERROR:
        error = ErrorInfo(code=BackendErrorCode.BACKEND_EXCEPTION, safe_message="backend failed")
    result = _result(execution_status=status, decision=decision, criteria=criteria, error=error)
    assert result.execution_status == status
    assert result.decision == decision


def test_con01_illegal_state_decision_pairs_rejected() -> None:
    illegal = [
        (s, d)
        for s in (ExecutionStatus.OK, ExecutionStatus.INPUT_ERROR, ExecutionStatus.BACKEND_ERROR)
        for d in (Decision.SUCCESS, Decision.FAILURE, Decision.ABSTAINED, None)
        if (s, d) not in LEGAL_PAIRS
    ]
    assert len(illegal) == 7
    for status, decision in illegal:
        with pytest.raises(ValidationError):
            _result(execution_status=status, decision=decision, error=None, criteria=())


def test_con01_error_null_iff_ok() -> None:
    safe_error = ErrorInfo(code=InputErrorCode.INVALID_SCHEMA, safe_message="invalid request")
    backend_error = ErrorInfo(code=BackendErrorCode.BACKEND_EXCEPTION, safe_message="backend failed")
    with pytest.raises(ValidationError):
        _result(error=safe_error)
    with pytest.raises(ValidationError):
        _result(execution_status=ExecutionStatus.INPUT_ERROR, decision=None, criteria=(), error=None)
    with pytest.raises(ValidationError):
        _result(
            execution_status=ExecutionStatus.BACKEND_ERROR,
            decision=None,
            criteria=(_criterion_result(),),
            error=None,
        )
    _result(execution_status=ExecutionStatus.BACKEND_ERROR, decision=None, error=backend_error)


def test_con01_input_error_requires_empty_criteria() -> None:
    error = ErrorInfo(code=InputErrorCode.INVALID_SCHEMA, safe_message="invalid request")
    with pytest.raises(ValidationError):
        _result(
            execution_status=ExecutionStatus.INPUT_ERROR,
            decision=None,
            criteria=(_criterion_result(),),
            error=error,
        )
    result = _result(execution_status=ExecutionStatus.INPUT_ERROR, decision=None, criteria=(), error=error)
    assert result.criteria == ()


def test_con01_backend_error_allows_partial_criteria() -> None:
    error = ErrorInfo(code=BackendErrorCode.BACKEND_EXCEPTION, safe_message="backend failed")
    result = _result(
        execution_status=ExecutionStatus.BACKEND_ERROR,
        decision=None,
        criteria=(_criterion_result(),),
        error=error,
    )
    assert len(result.criteria) == 1


def test_con01_reason_codes_deduplicated_in_order() -> None:
    result = _result(reason_codes=("AGG", "R2", "AGG", "R1", "R2"))
    assert result.reason_codes == ("AGG", "R2", "R1")
    cres = _criterion_result(reason_codes=("A", "B", "A"))
    assert cres.reason_codes == ("A", "B")


def test_con01_errorinfo_retryable_only_timeout_busy() -> None:
    for code in (BackendErrorCode.TIMEOUT, BackendErrorCode.BUSY):
        ErrorInfo(code=code, safe_message="m", retryable=True)
    for code in (BackendErrorCode.BACKEND_EXCEPTION, InputErrorCode.INVALID_SCHEMA):
        with pytest.raises(ValidationError):
            ErrorInfo(code=code, safe_message="m", retryable=True)
    ErrorInfo(code=BackendErrorCode.BACKEND_EXCEPTION, safe_message="m", retryable=False)
    info = ErrorInfo(code=InputErrorCode.LIMIT_EXCEEDED, safe_message="m", field_path="$.criteria")
    assert info.field_path == "$.criteria"
    assert info.retryable is False


# --------------------------------------------------------------------------
# CON-02: round trips, canonical JSON, snapshots, exports
# --------------------------------------------------------------------------


def _full_request() -> dict[str, Any]:
    criteria = [
        _criterion(id="c-eq-null", operator="equals", expected=None),
        _criterion(
            id="c-in",
            operator="in",
            expected=[1, "a", None, True, 1.5],
            scope="behavioral",
            evidence_ids=["act-1"],
        ),
        _visual_criterion(id="c-visual", evidence_ids=["shot-1"]),
    ]
    evidence = [
        _observation(
            id="obs-1",
            data={"validation_error": None, "nested": {"deep": [1, {"k": "végétal"}]}, "flag": False},
        ),
        _action(id="act-1", sequence=1, tool_result_id="tool-1"),
        _observation(id="tool-1", kind="observation", sequence=2, channel="tool", data={"ok": True}),
        _screenshot(sequence=3),
    ]
    return _request(criteria=criteria, evidence=evidence, metadata={"kü": "ü", "n": 1})


def test_con02_request_round_trip_preserves_order_and_nulls() -> None:
    original = parse_request(_full_request())
    dumped = original.model_dump(mode="json")
    assert [c["id"] for c in dumped["criteria"]] == ["c-eq-null", "c-in", "c-visual"]
    assert [e["id"] for e in dumped["evidence"]] == ["obs-1", "act-1", "tool-1", "shot-1"]
    # nulls preserved: equals-null stays an explicit null; nulls inside payloads stay
    assert dumped["criteria"][0]["expected"] is None
    assert dumped["evidence"][0]["data"]["validation_error"] is None
    assert "expected" not in dumped["criteria"][2]  # visual: field does not exist at all
    reparsed = parse_request(json.dumps(dumped, ensure_ascii=False))
    assert reparsed == original
    assert reparsed.model_dump(mode="json") == dumped


def test_con02_result_round_trip_preserves_nulls() -> None:
    result = _result(
        diagnostics=_diagnostics(
            request_hash=None,
            model_load_ms=None,
            measurements=Measurements(unavailable_reasons={"input_tokens": "not_counted"}),
            preprocessing=(
                PreprocessingRecord(
                    evidence_id="shot-1",
                    input_width=64,
                    input_height=32,
                    color_conversion=ColorConversion.RGBA_ON_WHITE,
                    processor_longest_edge=None,
                    output_width=None,
                    output_height=None,
                    patch_count=None,
                ),
            ),
            limitations=(LimitationCode.VISUAL_GROUNDING_UNVERIFIED,),
        ),
        criteria=(
            _criterion_result(
                reason_codes=(AbstentionReason.MISSING_EVIDENCE,),
                evaluations=(
                    CriterionEvaluation(
                        evidence_ref=EvidenceRef(evidence_id="obs-1", pointer="/x"),
                        state=CriterionState.UNKNOWN,
                        reason_codes=(AbstentionReason.MISSING_VALUE,),
                    ),
                ),
            ),
        ),
    )
    dumped = result.model_dump(mode="json")
    assert dumped["error"] is None
    assert dumped["diagnostics"]["request_hash"] is None
    assert dumped["diagnostics"]["measurements"]["cost_amount"] is None
    assert "cost_is_estimate" not in dumped["diagnostics"]["measurements"]
    reparsed = VerificationResult.model_validate(dumped)
    assert reparsed == result


def test_con02_parse_accepts_str_bytes_and_mapping() -> None:
    mapping = _request()
    from_str = parse_request(json.dumps(mapping))
    from_bytes = parse_request(json.dumps(mapping).encode("utf-8"))
    from_mapping = parse_request(mapping)
    assert from_str == from_bytes == from_mapping


def test_con02_canonical_json_known_value() -> None:
    value = {"b": 1, "a": [2, 1.5, "x", None, True], "é": "ü"}
    assert canonical_json(value) == '{"a":[2,1.5,"x",null,true],"b":1,"é":"ü"}'
    doc = _full_request()
    parsed = parse_request(doc)
    assert json.loads(canonical_json(parsed.metadata)) == {"kü": "ü", "n": 1}
    assert json.loads(canonical_json(parsed.evidence[0].data)) == doc["evidence"][0]["data"]  # type: ignore[union-attr]


def test_con02_canonical_json_rejects_nonfinite_and_unknown_types() -> None:
    with pytest.raises(ValueError, match="non-finite"):
        canonical_json({"x": float("nan")})
    with pytest.raises(ValueError, match="non-finite"):
        canonical_json([float("inf")])
    with pytest.raises(ValueError, match="not JSON"):
        canonical_json({"t": object()})


def test_con02_schema_snapshots_match_generated() -> None:
    regenerate = bool(os.environ.get("NITELOS_UPDATE_SNAPSHOTS"))
    for name, model in (("request.v1.json", VerificationRequest), ("result.v1.json", VerificationResult)):
        path = SCHEMA_DIR / name
        generated = model.model_json_schema()
        if regenerate:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(generated, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            continue
        assert path.exists(), f"missing snapshot {path}"
        current = json.loads(path.read_text(encoding="utf-8"))
        assert current == generated, (
            f"{name} drifted from the generated schema; if intentional, regenerate with "
            "NITELOS_UPDATE_SNAPSHOTS=1 uv run pytest tests/test_contract.py -k snapshot"
        )


def test_con02_exports_explicit_and_light() -> None:
    required = {
        "VerificationRequest",
        "AssertionCriterion",
        "VisualCriterion",
        "Evidence",
        "EvidenceRef",
        "VerificationResult",
        "CriterionResult",
        "Score",
        "parse_request",
        "RequestValidationError",
        "ConfigurationError",
        "canonical_json",
    }
    assert required <= set(nitelos.__all__)
    # Import lightness must be checked in a fresh interpreter: the shared pytest
    # process may legitimately have Pillow loaded (smoke-fixture tests), which
    # would make this assertion depend on test order.
    code = (
        "import sys\n"
        "import nitelos\n"
        "heavy = [m for m in ('PIL', 'PIL.Image', 'numpy', 'scipy') if m in sys.modules]\n"
        "assert not heavy, heavy\n"
    )
    proc = run([executable, "-c", code], check=False, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout == ""


# --------------------------------------------------------------------------
# CON-03: strict ingestion and safe errors
# --------------------------------------------------------------------------


def test_con03_duplicate_json_keys_rejected() -> None:
    text = json.dumps(_request())[:-1] + ', "request_id": "other"}'
    assert_parse_error(text, InputErrorCode.INVALID_SCHEMA, "$.request_id")
    plain = json.dumps(_request())
    duplicated = plain.replace(
        '"data": {"validation_error": true}', '"data": {"validation_error": true, "validation_error": false}'
    )
    assert duplicated != plain, "string surgery failed to build a duplicate key"
    assert_parse_error(duplicated, InputErrorCode.INVALID_SCHEMA, "$.evidence[0].data.validation_error")


def test_con03_duplicate_ids_and_sequence_rejected() -> None:
    assert_parse_error(
        _request(criteria=[_criterion(), _criterion()]),
        InputErrorCode.DUPLICATE_ID,
        "$.criteria[1].id",
    )
    assert_parse_error(
        _request(evidence=[_observation(), _observation()]),
        InputErrorCode.DUPLICATE_ID,
        "$.evidence[1].id",
    )
    # unique IDs but repeated sequence number: not strictly ascending
    assert_parse_error(
        _request(evidence=[_observation(), _observation(id="obs-2")]),
        InputErrorCode.INVALID_SEQUENCE,
        "$.evidence[1].sequence",
    )
    assert_parse_error(
        _request(evidence=[_observation(sequence=1), _observation(id="obs-2", sequence=0)]),
        InputErrorCode.INVALID_SEQUENCE,
        "$.evidence[1].sequence",
    )


@pytest.mark.parametrize(
    ("mutate", "path"),
    [
        (lambda d: d["evidence"][0].update(sequence=True), "$.evidence[0].sequence"),
        (lambda d: d["evidence"][0].update(sequence="0"), "$.evidence[0].sequence"),
        (lambda d: d["criteria"][0].update(max_age_seconds=True), "$.criteria[0].max_age_seconds"),
        (lambda d: d["criteria"][0].update(max_age_seconds="300"), "$.criteria[0].max_age_seconds"),
        (lambda d: d["criteria"][0].update(subject={"form": 5}), "$.criteria[0].subject"),
    ],
)
def test_con03_bool_and_string_numbers_rejected(mutate: Callable[[dict[str, Any]], None], path: str) -> None:
    doc = _request()
    mutate(doc)
    assert_parse_error(doc, InputErrorCode.INVALID_SCHEMA, path)


def test_con03_bool_for_screenshot_width_rejected() -> None:
    doc = _visual_request()
    doc["evidence"][0]["width"] = True
    assert_parse_error(doc, InputErrorCode.INVALID_SCHEMA, "$.evidence[0].width")


def test_con03_nonfinite_numbers_rejected() -> None:
    assert_parse_error('{"x": NaN}', InputErrorCode.INVALID_SCHEMA, "$.x")
    assert_parse_error('{"x": Infinity}', InputErrorCode.INVALID_SCHEMA, "$.x")
    assert_parse_error('{"x": -Infinity}', InputErrorCode.INVALID_SCHEMA, "$.x")
    assert_parse_error('{"x": 1e999}', InputErrorCode.INVALID_SCHEMA, "$.x")
    doc = _request()
    doc["metadata"] = {"x": float("inf")}
    assert_parse_error(doc, InputErrorCode.INVALID_SCHEMA, "$.metadata.x")
    doc2 = _request()
    doc2["criteria"][0]["expected"] = float("nan")
    assert_parse_error(doc2, InputErrorCode.INVALID_SCHEMA, "$.criteria[0].expected")


def test_con03_extra_fields_rejected() -> None:
    doc = _request()
    doc["priority"] = 1
    assert_parse_error(doc, InputErrorCode.INVALID_SCHEMA, "$.priority")
    doc = _request()
    doc["criteria"][0]["weight"] = 0.5
    assert_parse_error(doc, InputErrorCode.INVALID_SCHEMA, "$.criteria[0].weight")
    doc = _request()
    doc["evidence"][0]["trust"] = True
    assert_parse_error(doc, InputErrorCode.INVALID_SCHEMA, "$.evidence[0].trust")
    # free-form JSON payloads accept arbitrary keys and shapes
    parse_request(_request(evidence=[_observation(data={"anything": [1, 2, {"deep": None}]})]))


def test_con03_schema_version_rules() -> None:
    doc = _request()
    doc["schema_version"] = "2"
    assert_parse_error(doc, InputErrorCode.UNSUPPORTED_SCHEMA, "$.schema_version")
    doc = _request()
    doc["schema_version"] = 1
    assert_parse_error(doc, InputErrorCode.UNSUPPORTED_SCHEMA, "$.schema_version")
    doc = _request()
    del doc["schema_version"]
    assert_parse_error(doc, InputErrorCode.INVALID_SCHEMA, "$.schema_version")


def test_con03_malformed_json_and_root() -> None:
    assert_parse_error("{", InputErrorCode.INVALID_SCHEMA, "$")
    assert_parse_error("[]", InputErrorCode.INVALID_SCHEMA, "$")
    assert_parse_error("42", InputErrorCode.INVALID_SCHEMA, "$")
    assert_parse_error(b"\xff\xfe", InputErrorCode.INVALID_SCHEMA, "$")


def test_con03_unknown_references() -> None:
    assert_parse_error(
        _request(criteria=[_criterion(evidence_ids=["ghost"])]),
        InputErrorCode.UNKNOWN_REFERENCE,
        "$.criteria[0].evidence_ids[0]",
    )
    # tool_result_id targets an observation whose channel is not tool
    assert_parse_error(
        _request(
            criteria=[_criterion(scope="behavioral", evidence_ids=["act-1"], pointer="/reported_status")],
            evidence=[_action(sequence=0, tool_result_id="obs-1"), _observation(sequence=1)],
        ),
        InputErrorCode.UNKNOWN_REFERENCE,
        "$.evidence[0].tool_result_id",
    )
    # tool_result_id targets a nonexistent id
    assert_parse_error(
        _request(
            criteria=[_criterion(scope="behavioral", evidence_ids=["act-1"], pointer="/reported_status")],
            evidence=[_action(sequence=0, tool_result_id="ghost"), _observation(sequence=1)],
        ),
        InputErrorCode.UNKNOWN_REFERENCE,
        "$.evidence[0].tool_result_id",
    )
    # tool_result_id targets another action
    assert_parse_error(
        _request(
            criteria=[_criterion(scope="behavioral", evidence_ids=["act-1"], pointer="/reported_status")],
            evidence=[_action(sequence=0, tool_result_id="act-2"), _action(id="act-2", sequence=1)],
        ),
        InputErrorCode.UNKNOWN_REFERENCE,
        "$.evidence[0].tool_result_id",
    )
    # legal: channel tool and greater sequence number
    parse_request(
        _request(
            criteria=[_criterion(scope="behavioral", evidence_ids=["act-1"], pointer="/reported_status")],
            evidence=[
                _action(sequence=0, tool_result_id="tool-1"),
                _observation(id="tool-1", sequence=1, channel="tool"),
            ],
        )
    )


def test_con03_sentinel_never_leaks_into_errors() -> None:
    doc = _request(objective=SENTINEL + "x" * 5000, metadata={SENTINEL[:4]: SENTINEL})
    with pytest.raises(RequestValidationError) as excinfo:
        parse_request(doc)
    blob = str(excinfo.value) + repr(excinfo.value)
    for issue in excinfo.value.issues:
        blob += f"{issue.code}{issue.field_path}{issue.safe_message}"
    assert SENTINEL not in blob
    text = json.dumps(_request())[:-1] + f', "criterion": "{SENTINEL}"}}'
    with pytest.raises(RequestValidationError) as excinfo2:
        parse_request(text)
    assert SENTINEL not in str(excinfo2.value) + repr(excinfo2.value)
    with pytest.raises(RequestValidationError) as excinfo3:
        parse_request(_request(criteria=[_criterion(pointer=SENTINEL)]))
    assert SENTINEL not in str(excinfo3.value) + repr(excinfo3.value)


# --------------------------------------------------------------------------
# CON-04: boundary types, bounds, limits, immutability, error ordering
# --------------------------------------------------------------------------


def test_con04_wire_timestamps_z_offset_naive() -> None:
    req = parse_request(_request(as_of="2024-06-01T10:00:00.25Z"))
    assert req.as_of == datetime(2024, 6, 1, 10, 0, 0, 250000, tzinfo=UTC)
    assert req.model_dump(mode="json")["as_of"].endswith("Z")
    assert_parse_error(
        _request(as_of="2024-06-01T10:00:00+05:00"), InputErrorCode.INVALID_TIMESTAMP, "$.as_of"
    )
    assert_parse_error(_request(as_of="2024-06-01 10:00:00Z"), InputErrorCode.INVALID_TIMESTAMP, "$.as_of")
    assert_parse_error(_request(as_of="2024-13-01T10:00:00Z"), InputErrorCode.INVALID_TIMESTAMP, "$.as_of")
    assert_parse_error(
        _request(as_of="2024-06-01T10:00:00.1234567Z"), InputErrorCode.INVALID_TIMESTAMP, "$.as_of"
    )
    # Python constructors: aware only, normalized to UTC
    criteria = [AssertionCriterion.model_validate(_criterion())]
    evidence = [ObservationEvidence.model_validate(_observation())]
    aware = datetime(2024, 6, 1, 15, 0, 0, tzinfo=timezone(timedelta(hours=5)))
    direct = VerificationRequest(
        request_id="demo-1",
        objective="o",
        checkpoint_id="cp",
        as_of=aware,
        criteria=criteria,
        evidence=evidence,
    )
    assert direct.as_of == datetime(2024, 6, 1, 10, 0, 0, tzinfo=UTC)
    with pytest.raises(ValidationError):
        VerificationRequest(
            request_id="demo-1",
            objective="o",
            checkpoint_id="cp",
            as_of=datetime(2024, 6, 1, 10, 0, 0),
            criteria=criteria,
            evidence=evidence,
        )


def test_con04_evidence_timestamp_invariants() -> None:
    assert_parse_error(
        _request(evidence=[_observation(), _observation(id="obs-2", sequence=1, captured_at=TS_EARLIER)]),
        InputErrorCode.INVALID_TIMESTAMP,
        "$.evidence[1].captured_at",
    )
    assert_parse_error(
        _request(evidence=[_observation(captured_at="2024-06-01T10:00:01Z")]),
        InputErrorCode.INVALID_TIMESTAMP,
        "$.evidence[0].captured_at",
    )
    # ties are allowed; captured_at == as_of is allowed
    parse_request(_request(evidence=[_observation(), _observation(id="obs-2", sequence=1)]))


def test_con04_id_bounds() -> None:
    parse_request(_request(request_id="a" * 128))
    assert_parse_error(_request(request_id="a" * 129), InputErrorCode.INVALID_SCHEMA, "$.request_id")
    assert_parse_error(_request(request_id="-abc"), InputErrorCode.INVALID_SCHEMA, "$.request_id")
    assert_parse_error(_request(request_id=""), InputErrorCode.INVALID_SCHEMA, "$.request_id")
    assert_parse_error(_request(request_id=42), InputErrorCode.INVALID_SCHEMA, "$.request_id")


def test_con04_string_bounds() -> None:
    parse_request(_request(objective="x" * 4096))
    assert_parse_error(_request(objective="x" * 4097), InputErrorCode.INVALID_SCHEMA, "$.objective")
    assert_parse_error(_request(objective=""), InputErrorCode.INVALID_SCHEMA, "$.objective")
    assert_parse_error(_request(objective="   "), InputErrorCode.INVALID_SCHEMA, "$.objective")
    parse_request(_request(criteria=[_criterion(description="d" * 1024)]))
    assert_parse_error(
        _request(criteria=[_criterion(description="d" * 1025)]),
        InputErrorCode.INVALID_SCHEMA,
        "$.criteria[0].description",
    )
    parse_request(
        _request(
            criteria=[_criterion(scope="behavioral", evidence_ids=["act-1"], pointer="/reported_status")],
            evidence=[_action(name="n" * 128)],
        )
    )
    assert_parse_error(
        _request(
            criteria=[_criterion(scope="behavioral", evidence_ids=["act-1"], pointer="/reported_status")],
            evidence=[_action(name="n" * 129)],
        ),
        InputErrorCode.INVALID_SCHEMA,
        "$.evidence[0].name",
    )


def test_con04_subject_pair_bounds() -> None:
    parse_request(_request(criteria=[_criterion(subject={f"k{i}": f"v{i}" for i in range(16)})]))
    assert_parse_error(
        _request(criteria=[_criterion(subject={f"k{i}": "v" for i in range(17)})]),
        InputErrorCode.INVALID_SCHEMA,
        "$.criteria[0].subject",
    )
    assert_parse_error(
        _request(criteria=[_criterion(subject={})]), InputErrorCode.INVALID_SCHEMA, "$.criteria[0].subject"
    )


def test_con04_max_age_bounds_and_default() -> None:
    parse_request(_request(criteria=[_criterion(max_age_seconds=86400)]))
    assert_parse_error(
        _request(criteria=[_criterion(max_age_seconds=86401)]),
        InputErrorCode.INVALID_SCHEMA,
        "$.criteria[0].max_age_seconds",
    )
    assert_parse_error(
        _request(criteria=[_criterion(max_age_seconds=-1)]),
        InputErrorCode.INVALID_SCHEMA,
        "$.criteria[0].max_age_seconds",
    )
    req = parse_request(
        _request(criteria=[{k: v for k, v in _criterion().items() if k != "max_age_seconds"}])
    )
    assert req.criteria[0].max_age_seconds == 300


def test_con04_collection_counts() -> None:
    parse_request(_request(criteria=[_criterion(id=f"c{i}") for i in range(16)]))
    assert_parse_error(
        _request(criteria=[_criterion(id=f"c{i}") for i in range(17)]),
        InputErrorCode.LIMIT_EXCEEDED,
        "$.criteria",
    )
    observations = [_observation(id=f"o{i}", sequence=i) for i in range(128)]
    parse_request(_request(criteria=[_criterion(evidence_ids=["o0"])], evidence=observations))
    more = [_observation(id=f"o{i}", sequence=i) for i in range(129)]
    assert_parse_error(
        _request(criteria=[_criterion(evidence_ids=["o0"])], evidence=more),
        InputErrorCode.LIMIT_EXCEEDED,
        "$.evidence",
    )
    behavioral = _criterion(scope="behavioral", evidence_ids=["a0"], pointer="/reported_status")
    parse_request(
        _request(criteria=[behavioral], evidence=[_action(id=f"a{i}", sequence=i) for i in range(64)])
    )
    assert_parse_error(
        _request(criteria=[behavioral], evidence=[_action(id=f"a{i}", sequence=i) for i in range(65)]),
        InputErrorCode.LIMIT_EXCEEDED,
        "$.evidence",
    )
    shots16 = [_screenshot(id=f"s{i}", sequence=i, artifact_id=f"art-{i}") for i in range(16)]
    parse_request(_request(criteria=[_visual_criterion(evidence_ids=["s0"])], evidence=shots16))
    shots17 = [_screenshot(id=f"s{i}", sequence=i, artifact_id=f"art-{i}") for i in range(17)]
    assert_parse_error(
        _request(criteria=[_visual_criterion(evidence_ids=["s0"])], evidence=shots17),
        InputErrorCode.LIMIT_EXCEEDED,
        "$.evidence",
    )


def test_con04_evidence_ids_and_expected_bounds() -> None:
    many = [_observation(id=f"o{i}", sequence=i) for i in range(17)]
    doc = _request(criteria=[_criterion(evidence_ids=[f"o{i}" for i in range(17)])], evidence=many)
    assert_parse_error(doc, InputErrorCode.LIMIT_EXCEEDED, "$.criteria[0].evidence_ids")
    assert_parse_error(
        _request(criteria=[_criterion(operator="in", expected=list(range(65)))]),
        InputErrorCode.LIMIT_EXCEEDED,
        "$.criteria[0].expected",
    )
    parse_request(_request(criteria=[_criterion(operator="in", expected=list(range(64)))]))
    assert_parse_error(
        _request(criteria=[_criterion(operator="in", expected=[])]),
        InputErrorCode.INVALID_SCHEMA,
        "$.criteria[0].expected",
    )


def test_con04_metadata_size_limit() -> None:
    unit = len(canonical_json({"filler": ""}))
    for size, code in ((8192, None), (8193, InputErrorCode.LIMIT_EXCEEDED)):
        doc = _request(metadata={"filler": "x" * (size - unit)})
        assert len(canonical_json(doc["metadata"]).encode("utf-8")) == size
        if code is None:
            parse_request(doc)
        else:
            assert_parse_error(doc, code, "$.metadata")


def test_con04_payload_size_limit() -> None:
    unit = len(canonical_json({"filler": ""}))
    for size, code in ((65536, None), (65537, InputErrorCode.LIMIT_EXCEEDED)):
        doc = _request(evidence=[_observation(data={"filler": "x" * (size - unit)})])
        assert len(canonical_json(doc["evidence"][0]["data"]).encode("utf-8")) == size
        if code is None:
            parse_request(doc)
        else:
            assert_parse_error(doc, code, "$.evidence[0].data")


def test_con04_request_size_limit() -> None:
    def padded_request(fillers: list[int]) -> dict[str, Any]:
        evidence = [
            _observation(id=f"o{i}", sequence=i, data={"f": "x" * size}) for i, size in enumerate(fillers)
        ]
        return _request(criteria=[_criterion(evidence_ids=["o0"])], evidence=evidence)

    # distribute ~1 MiB across 17 observation payloads (each stays under 64 KiB)
    base = len(json.dumps(padded_request([0] * 17)).encode("utf-8"))
    per, extra = divmod(1048576 - base, 17)
    assert 0 < per < 65536
    fillers = [per + 1] * extra + [per] * (17 - extra)
    at_limit = json.dumps(padded_request(fillers))
    assert len(at_limit.encode("utf-8")) == 1048576
    parse_request(at_limit)
    over = json.dumps(padded_request([fillers[0] + 1, *fillers[1:]]))
    assert len(over.encode("utf-8")) == 1048577
    assert_parse_error(over, InputErrorCode.LIMIT_EXCEEDED, "$")


def _nested(depth: int) -> dict[str, Any]:
    """``depth`` wrapper objects around a leaf: depth+1 nested containers."""
    value: dict[str, Any] = {"leaf": True}
    for _ in range(depth):
        value = {"a": value}
    return value


def test_con04_json_depth_limit() -> None:
    nested = _nested
    # container depth: root object = 1; each nested container adds one level.
    # The reported path points at the first container beyond the limit.
    parse_request(_request(metadata=nested(14)))  # deepest container at depth 16
    assert_parse_error(
        _request(metadata=nested(15)),
        InputErrorCode.LIMIT_EXCEEDED,
        "$.metadata" + ".a" * 15,
    )
    # observation payloads: root(1) + evidence array(2) + item(3) + data levels
    parse_request(_request(evidence=[_observation(data=nested(12))]))  # depth 16
    assert_parse_error(
        _request(evidence=[_observation(data=nested(13))]),
        InputErrorCode.LIMIT_EXCEEDED,
        "$.evidence[0].data" + ".a" * 13,
    )


def test_con04_constructor_depth_bound() -> None:
    # Direct construction must raise its documented ValidationError for over-deep
    # payloads, never an unhandled RecursionError; the payload subtree itself is
    # bounded to 16 nested containers (the parse path keeps its absolute bound).
    criteria = [AssertionCriterion.model_validate(_criterion())]
    evidence = [ObservationEvidence.model_validate(_observation())]
    common: dict[str, Any] = {
        "request_id": "demo-1",
        "objective": "o",
        "checkpoint_id": "cp",
        "as_of": datetime(2024, 6, 1, 10, 0, tzinfo=UTC),
        "criteria": criteria,
        "evidence": evidence,
    }
    VerificationRequest(metadata=_nested(15), **common)  # 16 container levels: accepted
    for too_deep in (16, 5000):
        with pytest.raises(ValidationError):
            VerificationRequest(metadata=_nested(too_deep), **common)
    ObservationEvidence.model_validate(_observation(data=_nested(15)))
    for too_deep in (16, 5000):
        with pytest.raises(ValidationError):
            ObservationEvidence.model_validate(_observation(data=_nested(too_deep)))
    with pytest.raises(ValidationError):
        ActionEvidence.model_validate(_action(arguments=_nested(5000)))
    # parse path unchanged: absolute depth still LIMIT_EXCEEDED with a path
    assert_parse_error(
        _request(metadata=_nested(15)), InputErrorCode.LIMIT_EXCEEDED, "$.metadata" + ".a" * 15
    )


def test_con04_immutable_input_copies() -> None:
    doc = _full_request()
    req = parse_request(doc)
    doc["metadata"]["injected"] = "evil"
    doc["evidence"][0]["data"]["validation_error"] = "changed"
    doc["criteria"][0]["subject"]["form"] = "changed"
    assert dict(req.metadata) == {"kü": "ü", "n": 1}
    assert req.evidence[0].data["validation_error"] is None  # type: ignore[union-attr]
    assert req.evidence[0].data["nested"]["deep"][1]["k"] == "végétal"  # type: ignore[union-attr]
    assert dict(req.criteria[0].subject) == {"form": "registration-1"}
    obs = req.evidence[0]
    assert isinstance(obs, ObservationEvidence)
    with pytest.raises(TypeError):
        obs.data["validation_error"] = 1  # type: ignore[index]
    with pytest.raises(ValidationError):
        obs.data = {"x": 1}  # type: ignore[misc]
    with pytest.raises(ValidationError):
        req.metadata = {"x": 1}  # type: ignore[misc]
    with pytest.raises(TypeError):
        req.criteria[0].subject["form"] = "x"  # type: ignore[index]


def test_con04_first_error_ordering() -> None:
    # envelope field order: request_id before objective
    assert_parse_error(
        _request(request_id="!bad", objective=""), InputErrorCode.INVALID_SCHEMA, "$.request_id"
    )
    # criteria field validated before evidence field regardless of document position
    doc = _request()
    doc["criteria"][0]["description"] = ""
    doc["evidence"][0]["channel"] = "nope"
    assert_parse_error(doc, InputErrorCode.INVALID_SCHEMA, "$.criteria[0].description")
    # item order within a list
    doc = _request(criteria=[_criterion(id="-bad"), _criterion(id="c2", description="")])
    assert_parse_error(doc, InputErrorCode.INVALID_SCHEMA, "$.criteria[0].id")
    # field order within one criterion: id before description
    assert_parse_error(
        _request(criteria=[_criterion(id="-bad", description="")]),
        InputErrorCode.INVALID_SCHEMA,
        "$.criteria[0].id",
    )
    # unknown top-level keys reported before field errors
    doc = _request(objective="")
    doc["zz"] = 1
    assert_parse_error(doc, InputErrorCode.INVALID_SCHEMA, "$.zz")
    # structural invariants run after field validation; duplicates before references
    doc = _request(
        criteria=[_criterion(evidence_ids=["ghost"]), _criterion(id="c2")],
        evidence=[_observation(), _observation()],
    )
    assert_parse_error(doc, InputErrorCode.DUPLICATE_ID, "$.evidence[1].id")
    # within invariants: sequence before timestamp before reference
    doc = _request(
        criteria=[_criterion(evidence_ids=["ghost"])],
        evidence=[_observation(sequence=5), _observation(id="o2", sequence=5, captured_at=TS_EARLIER)],
    )
    assert_parse_error(doc, InputErrorCode.INVALID_SEQUENCE, "$.evidence[1].sequence")
    doc = _request(
        criteria=[_criterion(evidence_ids=["ghost"])],
        evidence=[_observation(), _observation(id="o2", sequence=1, captured_at=TS_EARLIER)],
    )
    assert_parse_error(doc, InputErrorCode.INVALID_TIMESTAMP, "$.evidence[1].captured_at")


# --------------------------------------------------------------------------
# Field/type/default/bound coverage for every doc-03 field
# --------------------------------------------------------------------------


def test_request_fields_defaults_and_types() -> None:
    req = parse_request(_request())
    assert req.schema_version == "1"
    assert req.request_id == "demo-1"
    assert req.objective == "Complete registration"
    assert req.checkpoint_id == "cp"
    assert req.as_of == datetime(2024, 6, 1, 10, 0, tzinfo=UTC)
    assert isinstance(req.criteria, tuple)
    assert isinstance(req.evidence, tuple)
    assert req.metadata == {}
    minimal = _request()
    del minimal["metadata"]
    assert parse_request(minimal).metadata == {}


def test_criterion_union_discrimination_and_scopes() -> None:
    req = parse_request(_full_request())
    assert isinstance(req.criteria[0], AssertionCriterion)
    assert isinstance(req.criteria[2], VisualCriterion)
    for bad_scope in ("visual", "noscope"):
        assert_parse_error(
            _request(criteria=[_criterion(scope=bad_scope)]),
            InputErrorCode.INVALID_SCHEMA,
            "$.criteria[0].scope",
        )
    assert_parse_error(
        _request(criteria=[_visual_criterion(scope="observed_state")]),
        InputErrorCode.INVALID_SCHEMA,
        "$.criteria[0].scope",
    )
    assert_parse_error(
        _request(criteria=[_criterion(kind="mystery")]), InputErrorCode.INVALID_SCHEMA, "$.criteria[0]"
    )
    visual = VisualCriterion.model_validate(_visual_criterion())
    assert visual.scope == Scope.VISUAL
    assert visual.max_age_seconds == 300
    # scope/channel compatibility is NIT-005 territory: only kind/scope values are checked here


def test_assertion_operator_expected_rules() -> None:
    parse_request(_request(criteria=[_criterion(operator="equals", expected=None)]))
    parse_request(_request(criteria=[_criterion(operator="equals", expected="s")]))
    parse_request(_request(criteria=[_criterion(operator="in", expected=[1, "a", None])]))
    exists = {k: v for k, v in _criterion().items() if k != "expected"} | {"operator": "exists"}
    parse_request(_request(criteria=[exists]))
    assert_parse_error(
        _request(criteria=[_criterion(operator="exists", expected=None)]),
        InputErrorCode.INVALID_SCHEMA,
        "$.criteria[0].expected",
    )
    assert_parse_error(
        _request(criteria=[_criterion(operator="equals", expected=[1, 2])]),
        InputErrorCode.INVALID_SCHEMA,
        "$.criteria[0].expected",
    )
    assert_parse_error(
        _request(criteria=[_criterion(operator="in", expected=False)]),
        InputErrorCode.INVALID_SCHEMA,
        "$.criteria[0].expected",
    )
    assert_parse_error(
        _request(criteria=[_criterion(operator="in", expected=[{"a": 1}])]),
        InputErrorCode.INVALID_SCHEMA,
        "$.criteria[0].expected",
    )
    assert_parse_error(
        _request(criteria=[_criterion(operator="equals", expected={"a": 1})]),
        InputErrorCode.INVALID_SCHEMA,
        "$.criteria[0].expected",
    )
    assert_parse_error(
        _request(criteria=[_criterion(operator="compare")]),
        InputErrorCode.INVALID_SCHEMA,
        "$.criteria[0].operator",
    )


def test_pointer_rfc6901() -> None:
    for good in ("", "/a", "/a/b", "/a~1b", "/~0", "/0/1", "/ké", "/x/", "//"):
        parse_request(_request(criteria=[_criterion(pointer=good)]))
    for bad in ("a", "/~2", "/a~", "~0", 5, True):
        assert_parse_error(
            _request(criteria=[_criterion(pointer=bad)]),
            InputErrorCode.INVALID_POINTER,
            "$.criteria[0].pointer",
        )


def test_evidence_kinds_and_payloads() -> None:
    shot = _screenshot()
    ScreenshotEvidence.model_validate(shot)
    for bad_media in ("image/gif", "png"):
        with pytest.raises(ValidationError):
            ScreenshotEvidence.model_validate(_screenshot(media_type=bad_media))
    with pytest.raises(ValidationError):
        ScreenshotEvidence.model_validate(_screenshot(width=0))
    with pytest.raises(ValidationError):
        ScreenshotEvidence.model_validate(_screenshot(width=-1))
    with pytest.raises(ValidationError):
        ScreenshotEvidence.model_validate(_screenshot(height=True))
    with pytest.raises(ValidationError):
        ScreenshotEvidence.model_validate(_screenshot(sha256="A" * 64))
    with pytest.raises(ValidationError):
        ScreenshotEvidence.model_validate({k: v for k, v in shot.items() if k != "phase"})
    ObservationEvidence.model_validate(_observation(channel="human", data={}))
    for bad_channel in ("dom2", ""):
        with pytest.raises(ValidationError):
            ObservationEvidence.model_validate(_observation(channel=bad_channel))
    with pytest.raises(ValidationError):
        ObservationEvidence.model_validate(_observation(data=[1, 2]))
    act = ActionEvidence.model_validate(_action(reported_status="unknown"))
    assert act.reported_status == ReportedStatus.UNKNOWN
    assert act.tool_result_id is None
    with pytest.raises(ValidationError):
        ActionEvidence.model_validate(_action(reported_status="cancelled"))
    with pytest.raises(ValidationError):
        ActionEvidence.model_validate(_action(arguments="not-an-object"))
    with pytest.raises(ValidationError):
        ActionEvidence.model_validate(_action(name=""))
    assert issubclass(ScreenshotEvidence, Evidence)
    assert issubclass(ObservationEvidence, Evidence)
    assert issubclass(ActionEvidence, Evidence)
    with pytest.raises(ValidationError):
        Evidence.model_validate(_observation())  # base carries no discriminant


def test_evidence_ref_rules() -> None:
    EvidenceRef(evidence_id="obs-1", pointer="/x")
    EvidenceRef(evidence_id="obs-1", bbox=(0, 0, 1, 1))
    EvidenceRef(evidence_id="obs-1", grounding=Grounding.MODEL_INFERRED, bbox=(0, 5, 10, 6))
    with pytest.raises(ValidationError):
        EvidenceRef(evidence_id="obs-1", pointer="/x", bbox=(0, 0, 1, 1))
    with pytest.raises(ValidationError):
        EvidenceRef(evidence_id="obs-1")
    with pytest.raises(ValidationError):
        EvidenceRef(evidence_id="obs-1", bbox=(1, 0, 1, 4))
    with pytest.raises(ValidationError):
        EvidenceRef(evidence_id="obs-1", bbox=(0, 2, 3, 2))
    with pytest.raises(ValidationError):
        EvidenceRef(evidence_id="obs-1", bbox=(-1, 0, 2, 4))
    with pytest.raises(ValidationError):
        EvidenceRef(evidence_id="obs-1", bbox=(0.0, 0, 1, 1))
    with pytest.raises(ValidationError):
        EvidenceRef(evidence_id="obs-1", bbox=(0, 0, 1, True))
    with pytest.raises(ValidationError):
        EvidenceRef(evidence_id="obs-1", pointer="nope")
    with pytest.raises(ValidationError):
        EvidenceRef(evidence_id="obs-1", pointer="/x", grounding="assertion_checked_by_backend")


def test_score_rules() -> None:
    Score(kind=ScoreKind.UNCALIBRATED_SCORE, value=4.5, target="criterion_satisfied", scale="0-5")
    Score(kind=ScoreKind.UNCALIBRATED_PROBABILITY, value=0.0, target="criterion_satisfied")
    Score(kind=ScoreKind.UNCALIBRATED_PROBABILITY, value=1.0, target="criterion_satisfied")
    Score(
        kind=ScoreKind.CALIBRATED_PROBABILITY, value=0.5, target="criterion_satisfied", calibration_id="cal-1"
    )
    with pytest.raises(ValidationError):
        Score(kind=ScoreKind.UNCALIBRATED_SCORE, value=4.5, target="criterion_satisfied")
    with pytest.raises(ValidationError):
        Score(kind=ScoreKind.UNCALIBRATED_PROBABILITY, value=1.5, target="criterion_satisfied")
    with pytest.raises(ValidationError):
        Score(kind=ScoreKind.UNCALIBRATED_PROBABILITY, value=-0.1, target="criterion_satisfied")
    with pytest.raises(ValidationError):
        Score(kind=ScoreKind.UNCALIBRATED_PROBABILITY, value=float("nan"), target="criterion_satisfied")
    with pytest.raises(ValidationError):
        Score(kind=ScoreKind.UNCALIBRATED_PROBABILITY, value=True, target="criterion_satisfied")
    with pytest.raises(ValidationError):
        Score(kind=ScoreKind.UNCALIBRATED_PROBABILITY, value=0.5, target="")
    with pytest.raises(ValidationError):
        Score(kind="confidence", value=0.5, target="criterion_satisfied")


def test_backend_finding_rules() -> None:
    BackendFinding(criterion_id="c", state=CriterionState.UNKNOWN)
    BackendFinding(
        criterion_id="c",
        state=CriterionState.SUPPORTED,
        evidence_refs=(EvidenceRef(evidence_id="s", bbox=(0, 0, 1, 1)),),
        score=Score(kind=ScoreKind.UNCALIBRATED_SCORE, value=1.0, target="criterion_satisfied", scale="0-1"),
        rationale="r" * 2048,
    )
    with pytest.raises(ValidationError):
        BackendFinding(criterion_id="c", state=CriterionState.UNKNOWN, rationale="r" * 2049)
    with pytest.raises(ValidationError):
        BackendFinding(criterion_id="c", state="maybe")
    with pytest.raises(ValidationError):
        BackendFinding(
            criterion_id="c",
            state=CriterionState.SUPPORTED,
            evidence_refs=tuple(EvidenceRef(evidence_id=f"e{i}") for i in range(17)),
        )


def test_diagnostics_shapes() -> None:
    d = _diagnostics()
    assert d.backend.model_id is None
    assert d.backend.version == "1"
    assert d.policy_id == "strict"
    m = Measurements()
    assert m.input_tokens is None
    assert m.cost_amount is None
    assert m.unavailable_reasons == {}
    with pytest.raises(ValidationError):
        Measurements(cost_amount=1.0)  # currency/source/as_of missing
    with pytest.raises(ValidationError):
        Measurements(cost_amount=1.0, cost_currency="EUR", cost_source="list")  # cost_as_of missing
    Measurements(
        cost_amount=1.0,
        cost_currency="EUR",
        cost_source="list",
        cost_as_of=datetime(2024, 6, 1, tzinfo=UTC),
    )
    with pytest.raises(ValidationError):
        Measurements(cost_currency="EUR")  # amount missing
    with pytest.raises(ValidationError):
        Measurements(input_tokens=-1)
    Measurements(input_tokens=0)
    with pytest.raises(ValidationError):
        Measurements(
            cost_amount=-0.5,
            cost_currency="EUR",
            cost_source="list",
            cost_as_of=datetime(2024, 6, 1, tzinfo=UTC),
        )
    with pytest.raises(ValidationError):
        Measurements(
            cost_amount=float("nan"),
            cost_currency="EUR",
            cost_source="list",
            cost_as_of=datetime(2024, 6, 1, tzinfo=UTC),
        )
    with pytest.raises(ValidationError):
        _diagnostics(elapsed_ms=-1.0)
    with pytest.raises(ValidationError):
        _diagnostics(elapsed_ms=float("inf"))
    _diagnostics(criterion_durations_ms={"c": 0.0}, model_load_ms=5.0)
    p = PreprocessingRecord(
        evidence_id="s",
        input_width=8,
        input_height=8,
        color_conversion=ColorConversion.NONE,
        processor_longest_edge=1024,
        output_width=None,
        output_height=None,
        patch_count=3,
    )
    assert p.patch_count == 3
    assert p.color_conversion == ColorConversion.NONE
    with pytest.raises(ValidationError):
        PreprocessingRecord(
            evidence_id="s",
            input_width=8,
            input_height=8,
            color_conversion="sepia",
            processor_longest_edge=None,
        )
    with pytest.raises(ValidationError):
        PreprocessingRecord(
            evidence_id="s",
            input_width=0,
            input_height=8,
            color_conversion=ColorConversion.NONE,
            processor_longest_edge=None,
        )


def test_criterion_result_and_evaluation() -> None:
    assert "rationale" not in CriterionResult.model_fields
    r = _criterion_result(
        state=CriterionState.UNKNOWN,
        basis=Basis.NONE,
        reason_codes=(AbstentionReason.MISSING_EVIDENCE, AbstentionReason.STALE_EVIDENCE),
        limitations=(LimitationCode.VISUAL_GROUNDING_UNVERIFIED,),
    )
    assert r.basis == Basis.NONE
    with pytest.raises(ValidationError):
        _criterion_result(basis="guessed")
    ev = CriterionEvaluation(
        evidence_ref=EvidenceRef(evidence_id="o", pointer=""),
        state=CriterionState.REFUTED,
        reason_codes=(AbstentionReason.CONTRADICTORY_EVIDENCE,),
    )
    assert ev.state == CriterionState.REFUTED


def test_safe_reprs_hide_values() -> None:
    req = parse_request(_full_request())
    r = repr(req)
    assert "demo-1" in r
    assert "Complete registration" not in r
    assert "végétal" not in r
    obs_repr = repr(req.evidence[0])
    assert "obs-1" in obs_repr
    assert "végétal" not in obs_repr
    assert "validation_error" not in obs_repr
    finding = BackendFinding(criterion_id="c", state=CriterionState.UNKNOWN, rationale=SENTINEL)
    assert SENTINEL not in repr(finding)
    assert "0f14d0ab" in repr(_result())
    assert "no-errors" in repr(_criterion_result())
    assert repr(_diagnostics())


def test_configuration_error_exists() -> None:
    assert issubclass(ConfigurationError, Exception)
    with pytest.raises(ConfigurationError):
        raise ConfigurationError("misconfigured verifier")


def test_error_module_issue_shape() -> None:
    with pytest.raises(RequestValidationError) as excinfo:
        parse_request("{")
    (issue,) = excinfo.value.issues
    assert issue.code == InputErrorCode.INVALID_SCHEMA
    assert issue.field_path == "$"
    assert issue.safe_message
    assert repr(excinfo.value)


def test_con01_request_id_null_only_on_input_error() -> None:
    # ADR-011: null is legal exactly when execution_status is input_error
    error = ErrorInfo(code=InputErrorCode.INVALID_SCHEMA, safe_message="invalid request")
    null_input_error = _result(
        execution_status=ExecutionStatus.INPUT_ERROR, decision=None, criteria=(), error=error, request_id=None
    )
    assert null_input_error.request_id is None
    with pytest.raises(ValidationError):
        _result(request_id=None)  # ok requires the caller's id
    backend_error = ErrorInfo(code=BackendErrorCode.BACKEND_EXCEPTION, safe_message="m")
    with pytest.raises(ValidationError):
        _result(
            execution_status=ExecutionStatus.BACKEND_ERROR,
            decision=None,
            error=backend_error,
            request_id=None,
        )
