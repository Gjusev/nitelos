"""DET-01..05: deterministic assertion evaluator (NIT-004).

Authority: docs/planning/04-verification-backends.md ("Deterministic baseline"),
03-domain-model-and-api.md (operator semantics, null vs missing, action view),
05-evidence-and-policies.md (algorithm step 6). All expected values are
hand-written. The evaluator is pure: no eligibility, no combination rule
(NIT-005), and no evaluation/subprocess/network/SQL/regex path exists.
"""

from __future__ import annotations

from typing import Any

import pytest

from nitelos import __version__
from nitelos.backends import DeterministicBackend, evaluate_assertion, evaluate_reference
from nitelos.errors import EvidenceValidationError, InputErrorCode
from nitelos.schemas import (
    ActionEvidence,
    AssertionCriterion,
    CriterionEvaluation,
    CriterionState,
    ObservationEvidence,
    ScreenshotEvidence,
    VisualCriterion,
    parse_request,
)

SHA = "a" * 64
_UNSET: object = object()  # sentinel: distinguishes "no expected" from expected=None

DATA: dict[str, Any] = {
    "str": "hello",
    "num": 1,
    "float": 1.5,
    "bool": True,
    "null": None,
    "obj": {"a": 1, "a/b": 2, "~x": 3, "01": 4, "": 5},
    "arr": [10, 20, 30],
    "nested": {"deep": {"list": [1, {"k": "v"}]}},
    "cmd": "__import__('os')",
    "tmpl": "${injection}",
    "sql": "'; DROP TABLE users; --",
    "html": "<script>alert(1)</script>",
}


def _obs(data: dict[str, Any] | None = None, *, id: str = "obs-1") -> ObservationEvidence:
    return ObservationEvidence.model_validate(
        {
            "id": id,
            "kind": "observation",
            "sequence": 0,
            "captured_at": "2024-06-01T10:00:00Z",
            "checkpoint_id": "cp",
            "source_id": "collector",
            "subject": {"form": "registration-1"},
            "phase": "final",
            "sha256": SHA,
            "channel": "dom",
            "data": DATA if data is None else data,
        }
    )


def _act(**over: Any) -> ActionEvidence:
    values: dict[str, Any] = {
        "id": "act-1",
        "kind": "action",
        "sequence": 1,
        "captured_at": "2024-06-01T10:00:00Z",
        "checkpoint_id": "cp",
        "source_id": "agent",
        "subject": {"form": "registration-1"},
        "phase": "final",
        "sha256": SHA,
        "name": "submit-form",
        "arguments": {"email": "x@example.test"},
        "reported_status": "completed",
    }
    values.update(over)
    return ActionEvidence.model_validate(values)


def _shot() -> ScreenshotEvidence:
    return ScreenshotEvidence.model_validate(
        {
            "id": "shot-1",
            "kind": "screenshot",
            "sequence": 0,
            "captured_at": "2024-06-01T10:00:00Z",
            "checkpoint_id": "cp",
            "source_id": "screen",
            "subject": {"form": "registration-1"},
            "phase": "final",
            "sha256": SHA,
            "artifact_id": "art-1",
            "media_type": "image/png",
            "width": 2,
            "height": 3,
        }
    )


def _crit(pointer: str, operator: str, expected: Any = _UNSET, **over: Any) -> AssertionCriterion:
    values: dict[str, Any] = {
        "id": "c-1",
        "description": "d",
        "kind": "assertion",
        "scope": "observed_state",
        "evidence_ids": ["obs-1"],
        "subject": {"form": "registration-1"},
        "pointer": pointer,
        "operator": operator,
    }
    if expected is not _UNSET:
        values["expected"] = expected
    values.update(over)
    return AssertionCriterion.model_validate(values)


def _eval(pointer: str, operator: str, expected: Any = _UNSET, evidence: Any = None) -> CriterionEvaluation:
    return evaluate_reference(
        _crit(pointer, operator, expected), evidence if evidence is not None else _obs()
    )


def _state(pointer: str, operator: str, expected: Any = _UNSET, evidence: Any = None) -> CriterionState:
    return _eval(pointer, operator, expected, evidence).state


# --------------------------------------------------------------------------
# DET-01: equals / in / exists across scalar, null, object and array targets
# --------------------------------------------------------------------------


def test_det01_equals_over_scalars() -> None:
    assert _state("/str", "equals", "hello") == CriterionState.SUPPORTED
    assert _state("/str", "equals", "hell") == CriterionState.REFUTED
    assert _state("/num", "equals", 1) == CriterionState.SUPPORTED
    assert _state("/num", "equals", 2) == CriterionState.REFUTED
    assert _state("/float", "equals", 1.5) == CriterionState.SUPPORTED
    assert _state("/bool", "equals", True) == CriterionState.SUPPORTED
    assert _state("/bool", "equals", False) == CriterionState.REFUTED
    assert _state("/null", "equals", None) == CriterionState.SUPPORTED
    assert _state("/null", "equals", "x") == CriterionState.REFUTED
    assert _state("/str", "equals", None) == CriterionState.REFUTED  # present unequal, not missing


def test_det01_equals_and_in_on_containers_are_unknown() -> None:
    # the TARGET is a container; expected values must be scalars per schema
    assert _state("/obj", "equals", 1) == CriterionState.UNKNOWN
    assert _state("/arr", "equals", 10) == CriterionState.UNKNOWN
    assert _state("/obj", "in", [1, 2]) == CriterionState.UNKNOWN
    assert _state("/arr", "in", [10]) == CriterionState.UNKNOWN
    reason = _eval("/obj", "equals", 1).reason_codes
    assert reason == ("MISSING_VALUE",)


def test_det01_exists_accepts_null_and_containers() -> None:
    assert _state("/str", "exists") == CriterionState.SUPPORTED
    assert _state("/null", "exists") == CriterionState.SUPPORTED  # present null is a real value
    assert _state("/obj", "exists") == CriterionState.SUPPORTED
    assert _state("/arr/2", "exists") == CriterionState.SUPPORTED
    assert _state("/missing", "exists") == CriterionState.UNKNOWN
    assert _eval("/missing", "exists").reason_codes == ("MISSING_VALUE",)


def test_det01_in_membership() -> None:
    assert _state("/str", "in", ["hello", "x"]) == CriterionState.SUPPORTED
    assert _state("/str", "in", ["x", "y"]) == CriterionState.REFUTED
    assert _state("/num", "in", [2, 3, 1]) == CriterionState.SUPPORTED
    assert _state("/null", "in", [1, None]) == CriterionState.SUPPORTED
    assert _state("/obj/01", "in", [4, 5]) == CriterionState.SUPPORTED  # "01" as object key
    assert _state("/float", "in", [1.5]) == CriterionState.SUPPORTED


# --------------------------------------------------------------------------
# DET-02: missing keys, out-of-range indices, traversal into scalars
# --------------------------------------------------------------------------


def test_det02_missing_and_out_of_range_are_unknown() -> None:
    assert _state("/ghost", "equals", 1) == CriterionState.UNKNOWN
    assert _state("/obj/zzz", "exists") == CriterionState.UNKNOWN
    assert _state("/arr/3", "equals", 30) == CriterionState.UNKNOWN  # out of range
    assert _state("/arr/2", "equals", 30) == CriterionState.SUPPORTED
    assert _eval("/arr/3", "equals", 30).reason_codes == ("MISSING_VALUE",)


def test_det02_traversal_into_scalar_is_unknown() -> None:
    assert _state("/str/x", "equals", "x") == CriterionState.UNKNOWN
    assert _state("/num/0", "exists") == CriterionState.UNKNOWN
    assert _state("/nested/deep/list/1/k", "equals", "v") == CriterionState.SUPPORTED


# --------------------------------------------------------------------------
# DET-03: pointer escapes, empty pointer, array index notation
# --------------------------------------------------------------------------


def test_det03_escapes_and_special_keys() -> None:
    assert _state("/obj/a~1b", "equals", 2) == CriterionState.SUPPORTED  # key "a/b"
    assert _state("/obj/~0x", "equals", 3) == CriterionState.SUPPORTED  # key "~x"
    assert _state("", "exists") == CriterionState.SUPPORTED  # root selected by empty pointer
    assert _state("", "equals", 1) == CriterionState.UNKNOWN  # root is a container
    assert _state("/obj/", "equals", 5) == CriterionState.SUPPORTED  # empty-string key


def test_det03_array_index_notation() -> None:
    assert _state("/arr/0", "equals", 10) == CriterionState.SUPPORTED
    assert _state("/obj/01", "equals", 4) == CriterionState.SUPPORTED  # valid as object key
    for bad in ("01", "00", "-", "1e1", "", "+1", " 1"):
        with pytest.raises(EvidenceValidationError) as excinfo:
            _eval(f"/arr/{bad}", "equals", 10)
        assert excinfo.value.issue.code == InputErrorCode.INVALID_POINTER, bad


def test_det03_malformed_escapes_rejected_at_schema() -> None:
    # the shared RFC 6901 grammar in schemas.py rejects malformed escapes at
    # request ingestion; the evaluator reuses that grammar, not a second one
    with pytest.raises(Exception, match="pointer"):
        parse_request(
            {
                "schema_version": "1",
                "request_id": "r",
                "objective": "o",
                "checkpoint_id": "cp",
                "as_of": "2024-06-01T10:00:00Z",
                "criteria": [
                    {
                        "id": "c",
                        "description": "d",
                        "kind": "assertion",
                        "scope": "observed_state",
                        "evidence_ids": [],
                        "subject": {"f": "1"},
                        "pointer": "/~2bad",
                        "operator": "equals",
                        "expected": 1,
                    }
                ],
                "evidence": [],
            }
        )


# --------------------------------------------------------------------------
# DET-04: booleans are never numbers; numerics compare numerically
# --------------------------------------------------------------------------


def test_det04_bool_never_equals_number() -> None:
    assert _state("/bool", "equals", 1) == CriterionState.REFUTED  # true vs 1
    assert _state("/bool", "equals", 0) == CriterionState.REFUTED  # true vs 0
    assert _state("/num", "equals", True) == CriterionState.REFUTED  # 1 vs true
    assert _state("/num", "equals", False) == CriterionState.REFUTED  # 1 vs false
    false_obs = _obs({"f": False, "z": 0})
    assert _state("/f", "equals", 0, evidence=false_obs) == CriterionState.REFUTED
    assert _state("/f", "equals", False, evidence=false_obs) == CriterionState.SUPPORTED
    assert _state("/z", "equals", False, evidence=false_obs) == CriterionState.REFUTED


def test_det04_numeric_equality_and_mixed_membership() -> None:
    assert _state("/num", "equals", 1.0) == CriterionState.SUPPORTED  # 1 == 1.0
    assert _state("/float", "equals", 1.5) == CriterionState.SUPPORTED
    assert _state("/num", "in", [1.0, 2.0]) == CriterionState.SUPPORTED
    assert _state("/num", "in", [True, "1"]) == CriterionState.REFUTED  # no cross-type match
    assert _state("/bool", "in", [True]) == CriterionState.SUPPORTED
    assert _state("/bool", "in", [1]) == CriterionState.REFUTED


# --------------------------------------------------------------------------
# DET-05: injection-looking strings are literal data
# --------------------------------------------------------------------------


def test_det05_injection_strings_compared_literally() -> None:
    assert _state("/cmd", "equals", "__import__('os')") == CriterionState.SUPPORTED
    assert _state("/cmd", "equals", "os") == CriterionState.REFUTED
    assert _state("/tmpl", "equals", "${injection}") == CriterionState.SUPPORTED
    assert _state("/sql", "in", ["'; DROP TABLE users; --", "safe"]) == CriterionState.SUPPORTED
    assert _state("/html", "equals", "<script>alert(1)</script>") == CriterionState.SUPPORTED
    # payloads that LOOK like expressions are never evaluated
    ev = _obs({"__import__": "os.system"})
    assert _state("/__import__", "equals", "os.system", evidence=ev) == CriterionState.SUPPORTED


# --------------------------------------------------------------------------
# action view
# --------------------------------------------------------------------------


def test_action_view_is_exactly_the_documented_object() -> None:
    action = _act()
    assert _state("/reported_status", "equals", "completed", evidence=action) == CriterionState.SUPPORTED
    assert _state("/name", "equals", "submit-form", evidence=action) == CriterionState.SUPPORTED
    assert _state("/arguments/email", "equals", "x@example.test", evidence=action) == CriterionState.SUPPORTED
    assert _state("/tool_result_id", "equals", None, evidence=action) == CriterionState.SUPPORTED
    assert _state("/tool_result_id", "exists", evidence=action) == CriterionState.SUPPORTED
    # the view carries only the four documented fields
    assert _state("/id", "exists", evidence=action) == CriterionState.UNKNOWN
    assert _state("/kind", "exists", evidence=action) == CriterionState.UNKNOWN
    assert _state("/sha256", "exists", evidence=action) == CriterionState.UNKNOWN


# --------------------------------------------------------------------------
# per-reference output shape and backend surface
# --------------------------------------------------------------------------


def test_references_carry_assertion_checked_grounding_and_pointer() -> None:
    criterion = _crit("/str", "in", ["hello"])
    first, second = evaluate_assertion(criterion, [_obs(), _obs(id="obs-2")])
    for evaluation, evidence_id in ((first, "obs-1"), (second, "obs-2")):
        assert evaluation.evidence_ref.evidence_id == evidence_id
        assert evaluation.evidence_ref.pointer == "/str"
        assert evaluation.evidence_ref.grounding == "assertion_checked"
        assert evaluation.state == CriterionState.SUPPORTED
        assert evaluation.reason_codes == ()
    assert evaluate_assertion(criterion, [_obs(), _obs(id="obs-2")]) == (first, second)  # pure: stable output


def test_deterministic_backend_descriptor_and_evaluation() -> None:
    backend = DeterministicBackend()
    descriptor = backend.descriptor
    assert descriptor.id == "deterministic"
    assert descriptor.version == __version__
    assert descriptor.model_id is None
    assert descriptor.model_revision is None
    assert descriptor.prompt_hash is None
    assert descriptor.preprocessing_hash is None
    assert descriptor.runtime_lock_hash is None
    result = backend.evaluate_assertion(_crit("/num", "equals", 1), [_obs()])
    assert result[0].state == CriterionState.SUPPORTED


def test_unsupported_evidence_and_criteria_raise_coded_errors() -> None:
    with pytest.raises(EvidenceValidationError) as shot_error:
        evaluate_reference(_crit("/str", "equals", "x"), _shot())
    assert shot_error.value.issue.code == InputErrorCode.UNSUPPORTED_CAPABILITY
    visual = VisualCriterion.model_validate(
        {
            "id": "v",
            "description": "d",
            "kind": "visual",
            "scope": "visual",
            "evidence_ids": [],
            "subject": {"form": "registration-1"},
        }
    )
    with pytest.raises(EvidenceValidationError) as kind_error:
        evaluate_reference(visual, _obs())  # type: ignore[arg-type]
    assert kind_error.value.issue.code == InputErrorCode.UNSUPPORTED_CAPABILITY
