"""Deterministic assertion evaluator (NIT-004).

Authority: docs/planning/04-verification-backends.md ("Deterministic baseline"),
03-domain-model-and-api.md (operator semantics, null vs missing, the action
assertion view) and 05-evidence-and-policies.md (algorithm step 6). The
evaluator is pure: it takes one assertion criterion and already-selected
evidence, and returns one :class:`~nitelos.schemas.CriterionEvaluation` per
evidence item, in the order given. Eligibility (subject, checkpoint,
freshness, phase, trust) and the per-criterion combination/contradiction rule
are NIT-005 and are deliberately absent here.

Semantics (document 04): the empty pointer selects the payload root; ``~1``
decodes to ``/`` and ``~0`` to ``~`` (in that order). Array tokens must be
canonical nonnegative decimal numbers — decided at traversal time, because
``"01"`` is a legal object key — and anything else is INVALID_POINTER.
Out-of-range indices, missing keys and traversal into a scalar are UNKNOWN
with reason MISSING_VALUE. ``equals``/``in`` compare JSON scalars only: a
container target is UNKNOWN, a boolean never equals a number, ``1`` equals
``1.0``, null is a real value distinct from missing, strings compare exactly.
``exists`` supports any present target including null and containers; absence
is never refutation. Observation assertions view ``data``; action assertions
view exactly ``{name, arguments, reported_status, tool_result_id}``.

The pointer grammar is the one shared with :mod:`nitelos.schemas`
(decisions.md, NIT-004): schema validation already rejects malformed pointers
at ingestion, and this module re-checks through the same annotated type
instead of carrying a second grammar. Only the core assigns the
``assertion_checked`` grounding; every reference this evaluator returns
carries it.

Limitations: no expression language, no regex, no negation, no code
execution; input strings are always literal data. Screenshots and visual
criteria are UNSUPPORTED_CAPABILITY (kind checks belong to NIT-005/007, which
filter before calling this evaluator).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from pydantic import TypeAdapter, ValidationError

from nitelos import __version__
from nitelos.errors import EvidenceValidationError, InputErrorCode, Issue
from nitelos.schemas import (
    ActionEvidence,
    AssertionCriterion,
    BackendDescriptor,
    CriterionEvaluation,
    CriterionState,
    EvidenceRef,
    Grounding,
    JsonPointerType,
    ObservationEvidence,
    Operator,
)

__all__ = ["DeterministicBackend", "evaluate_assertion", "evaluate_reference"]

_TA_POINTER = TypeAdapter(JsonPointerType)
_DIGITS = "0123456789"
AnyEvidenceItem = ObservationEvidence | ActionEvidence


def _ev(code: InputErrorCode, path: str, message: str) -> EvidenceValidationError:
    return EvidenceValidationError(Issue(code, path, message))


# ---------------------------------------------------------------------------
# RFC 6901 traversal over frozen JSON payloads
# ---------------------------------------------------------------------------


def _unescape(token: str) -> str:
    # RFC 6901: ~1 first, then ~0 ("~01" decodes to "~1", not "/1")
    return token.replace("~1", "/").replace("~0", "~")


def _array_index(token: str) -> int:
    if not token or any(ch not in _DIGITS for ch in token) or (len(token) > 1 and token[0] == "0"):
        raise _ev(
            InputErrorCode.INVALID_POINTER,
            "$.pointer",
            "array indices must be canonical nonnegative decimal numbers",
        )
    return int(token)


def _resolve_pointer(root: object, pointer: str) -> tuple[bool, object]:
    """Traverse ``pointer`` from ``root``; returns (found, value)."""
    node = root
    if pointer == "":
        return True, node
    for raw_token in pointer.split("/")[1:]:
        token = _unescape(raw_token)
        if isinstance(node, Mapping):
            if token not in node:
                return False, None
            node = node[token]
        elif isinstance(node, (tuple, list)):
            index = _array_index(token)
            if index >= len(node):
                return False, None
            node = node[index]
        else:
            return False, None  # traversal into a scalar
    return True, node


# ---------------------------------------------------------------------------
# scalar semantics
# ---------------------------------------------------------------------------


def _scalar_equal(actual: object, expected: object) -> bool:
    """JSON-scalar equality: bool is never a number, 1 == 1.0, null only equals null."""
    if actual is None or expected is None:
        return actual is None and expected is None
    actual_is_bool = isinstance(actual, bool)
    expected_is_bool = isinstance(expected, bool)
    if actual_is_bool or expected_is_bool:
        return actual_is_bool and expected_is_bool and actual == expected
    if isinstance(actual, (int, float)) and isinstance(expected, (int, float)):
        return actual == expected
    return isinstance(actual, str) and isinstance(expected, str) and actual == expected


def _is_container(value: object) -> bool:
    return isinstance(value, (Mapping, tuple, list))


def _assertion_view(evidence_item: AnyEvidenceItem) -> object:
    """The JSON value an assertion criterion views for this evidence kind."""
    if isinstance(evidence_item, ObservationEvidence):
        return evidence_item.data
    if isinstance(evidence_item, ActionEvidence):
        return {
            "name": evidence_item.name,
            "arguments": evidence_item.arguments,
            "reported_status": evidence_item.reported_status,
            "tool_result_id": evidence_item.tool_result_id,
        }
    raise _ev(
        InputErrorCode.UNSUPPORTED_CAPABILITY,
        "$.evidence",
        "assertions view observation or action evidence only",
    )


# ---------------------------------------------------------------------------
# per-reference evaluation
# ---------------------------------------------------------------------------


def evaluate_reference(criterion: AssertionCriterion, evidence_item: AnyEvidenceItem) -> CriterionEvaluation:
    """Evaluate one assertion criterion against one evidence item (pure).

    Returns a :class:`~nitelos.schemas.CriterionEvaluation` whose reference
    carries the criterion pointer and the ``assertion_checked`` grounding.
    Raises :class:`EvidenceValidationError` (INVALID_POINTER for non-canonical
    array indices, UNSUPPORTED_CAPABILITY for non-assertion criteria or
    screenshot evidence) with a generic path; callers re-path to the criterion
    position.
    """
    if not isinstance(criterion, AssertionCriterion):
        raise _ev(
            InputErrorCode.UNSUPPORTED_CAPABILITY,
            "$.criteria",
            "the deterministic evaluator handles assertion criteria only",
        )
    try:
        _TA_POINTER.validate_python(criterion.pointer)
    except ValidationError:
        raise _ev(InputErrorCode.INVALID_POINTER, "$.pointer", "invalid JSON pointer") from None
    payload = _assertion_view(evidence_item)
    found, value = _resolve_pointer(payload, criterion.pointer)
    reference = EvidenceRef(
        evidence_id=evidence_item.id,
        pointer=criterion.pointer,
        grounding=Grounding.ASSERTION_CHECKED,
    )
    if not found:
        return CriterionEvaluation(
            evidence_ref=reference, state=CriterionState.UNKNOWN, reason_codes=("MISSING_VALUE",)
        )
    if criterion.operator == Operator.EXISTS:
        return CriterionEvaluation(evidence_ref=reference, state=CriterionState.SUPPORTED, reason_codes=())
    if _is_container(value):
        return CriterionEvaluation(
            evidence_ref=reference, state=CriterionState.UNKNOWN, reason_codes=("MISSING_VALUE",)
        )
    if criterion.operator == Operator.EQUALS:
        matched = _scalar_equal(value, criterion.expected)
    else:
        members = criterion.expected if isinstance(criterion.expected, tuple) else ()
        matched = any(_scalar_equal(value, member) for member in members)
    state = CriterionState.SUPPORTED if matched else CriterionState.REFUTED
    return CriterionEvaluation(evidence_ref=reference, state=state, reason_codes=())


def evaluate_assertion(
    criterion: AssertionCriterion, evidence: Sequence[AnyEvidenceItem]
) -> tuple[CriterionEvaluation, ...]:
    """Evaluate one criterion against each given evidence item, in the given order."""
    return tuple(evaluate_reference(criterion, item) for item in evidence)


class DeterministicBackend:
    """Built-in deterministic backend: fixed pointer operators, no model.

    Provides the default BackendDescriptor (id ``deterministic``, version =
    package version, all model identity fields null). The Backend protocol
    and capability negotiation arrive in NIT-007; this class intentionally
    exposes only the internal assertion method.
    """

    def __init__(self) -> None:
        self._descriptor = BackendDescriptor(id="deterministic", version=__version__)

    @property
    def descriptor(self) -> BackendDescriptor:
        return self._descriptor

    def evaluate_assertion(
        self, criterion: AssertionCriterion, evidence: Sequence[AnyEvidenceItem]
    ) -> tuple[CriterionEvaluation, ...]:
        return evaluate_assertion(criterion, evidence)

    def __repr__(self) -> str:
        return f"DeterministicBackend(version={self._descriptor.version!r})"
