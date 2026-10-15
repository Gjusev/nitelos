"""Schema-v1 trace ingestion (NIT-009).

Authority: docs/planning/11-glm-implementation-handoff.md ("Trace schema-v1, exact
minimum" — normative), 03 (Evidence, the action.tool_result_id rules, limits, the
"Screenshots and traces" pseudocode), 07 (trace JSON is untrusted data). A trace is a
caller-captured, bounded record of what happened: an ordered evidence list plus bounded
metadata. Nothing else — no artifact bytes, no trust, no model configuration, no
policy, no executable actions, no oracle labels.

Discipline mirrors :func:`nitelos.parse_request` by reusing its helpers (never
duplicated): bounded JSON, duplicate-key rejection, depth limits, per-item first-error
ordering and the shared structural invariants (unique IDs, strictly ascending
sequences, nondecreasing timestamps, tool_result_id rules, action/screenshot counts).
Reference and ``as_of`` checks that need request context are deferred to
:meth:`Trace.to_request` and verification. Trace JSON is untrusted: issues never carry
values, and nothing in a trace can authorize external trust — bindings live on the
Verifier.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from types import MappingProxyType
from typing import Annotated, Any, Literal, NoReturn

from pydantic import BeforeValidator, Field, ValidationError

from nitelos._json import JsonError, JsonErrorKind, parse_json
from nitelos.errors import InputErrorCode, Issue, RequestValidationError
from nitelos.schemas import (
    MAX_EVIDENCE,
    MAX_JSON_DEPTH,
    MAX_REQUEST_JSON_BYTES,
    AssertionCriterion,
    EvidenceItem,
    FrozenJsonObject,
    VerificationRequest,
    VisualCriterion,
    _canonical_size,
    _check_json_shape,
    _check_timestamp,
    _first_structural_issue,
    _Model,
    _tup,
    _validate_criteria,
    _validate_evidence,
    _validate_metadata,
)
from nitelos.schemas import (
    _Reject as _SchemaReject,
)

__all__ = ["Trace", "parse_trace"]

_TRACE_FIELDS = ("schema_version", "evidence", "metadata")
_TRACE_FIELD_SET = frozenset(_TRACE_FIELDS)

# parse-time stand-in for as_of: structural order rules are checked now, the real
# captured_at <= as_of comparison happens at to_request/verification time.
_UNBOUNDED_AS_OF = datetime.max.replace(tzinfo=UTC)


class _Reject(Exception):
    """Internal control flow carrying one safe issue."""

    def __init__(self, issue: Issue) -> None:
        super().__init__(str(issue))
        self.issue = issue


def _reject(code: InputErrorCode, path: str, message: str) -> NoReturn:
    raise _Reject(Issue(code, path, message))


def _ingest_trace(data: Mapping[str, object] | str | bytes) -> dict[str, object]:
    if isinstance(data, (str, bytes, bytearray)):
        try:
            raw = data.encode("utf-8") if isinstance(data, str) else bytes(data)
        except UnicodeEncodeError:
            _reject(InputErrorCode.INVALID_SCHEMA, "$", "trace text is not valid UTF-8")
        if len(raw) > MAX_REQUEST_JSON_BYTES:
            _reject(InputErrorCode.LIMIT_EXCEEDED, "$", "trace exceeds the JSON size limit")
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            _reject(InputErrorCode.INVALID_SCHEMA, "$", "trace bytes are not valid UTF-8")
        try:
            value = parse_json(text, max_depth=MAX_JSON_DEPTH)
        except JsonError as error:
            code = (
                InputErrorCode.LIMIT_EXCEEDED
                if error.kind in (JsonErrorKind.TOO_DEEP, JsonErrorKind.TOO_LARGE)
                else InputErrorCode.INVALID_SCHEMA
            )
            raise _Reject(Issue(code, error.path, f"invalid JSON: {error.kind}")) from None
    elif isinstance(data, Mapping):
        _check_json_shape(data, "$", 1)
        if _canonical_size(data) > MAX_REQUEST_JSON_BYTES:
            _reject(InputErrorCode.LIMIT_EXCEEDED, "$", "trace exceeds the JSON size limit")
        value = data
    else:
        _reject(InputErrorCode.INVALID_SCHEMA, "$", "trace must be a mapping or JSON text")
    if not isinstance(value, Mapping):
        _reject(InputErrorCode.INVALID_SCHEMA, "$", "trace must be a JSON object")
    return dict(value)


def _build_trace(mapping: Mapping[str, object]) -> Trace:
    for key in mapping:
        if key not in _TRACE_FIELD_SET:
            _reject(InputErrorCode.INVALID_SCHEMA, f"$.{key}", "unknown field")
    if "schema_version" not in mapping:
        _reject(InputErrorCode.INVALID_SCHEMA, "$.schema_version", "missing required field")
    if mapping["schema_version"] != "1":
        _reject(InputErrorCode.UNSUPPORTED_SCHEMA, "$.schema_version", "unsupported schema version")
    raw_evidence = mapping.get("evidence")
    if not isinstance(raw_evidence, list):
        _reject(InputErrorCode.INVALID_SCHEMA, "$.evidence", "must be a list")
    if len(raw_evidence) > MAX_EVIDENCE:
        _reject(InputErrorCode.LIMIT_EXCEEDED, "$.evidence", "too many evidence items")
    evidence = _validate_evidence(raw_evidence)
    _validate_metadata(mapping.get("metadata", {}))
    issue = _first_structural_issue((), evidence, _UNBOUNDED_AS_OF)
    if issue is not None:
        raise _Reject(issue)
    return Trace.model_validate(dict(mapping))


class Trace(_Model):
    """Caller-captured trace: ordered evidence plus bounded metadata, nothing else."""

    schema_version: Literal["1"] = "1"
    evidence: Annotated[tuple[EvidenceItem, ...], BeforeValidator(_tup), Field(max_length=MAX_EVIDENCE)]
    metadata: FrozenJsonObject = Field(default_factory=lambda: MappingProxyType({}))

    def __repr__(self) -> str:
        return f"Trace(evidence={len(self.evidence)}, metadata={len(dict(self.metadata))})"

    def to_request(
        self,
        *,
        objective: str,
        criteria: Sequence[Any],
        request_id: str,
        checkpoint_id: str,
        as_of: datetime | str,
    ) -> VerificationRequest:
        """Build a VerificationRequest from this trace's evidence and metadata.

        The caller supplies the request context (objective, criteria, identifiers and
        the observation cutoff). Request-context rules are enforced here and again at
        verification: criterion references must resolve, and no ``captured_at`` may be
        later than ``as_of`` (a future-dated item is an input error, not ineligible).
        No trust is implied: bindings stay on the Verifier, and no action is ever
        executed or replayed. Raises a safe :class:`RequestValidationError`.
        """
        validated_criteria = _validate_criteria(_coerce_criteria(criteria))
        if isinstance(as_of, datetime):
            # review F1: naive datetimes are coded input errors (never a raw
            # TypeError from aware-vs-naive comparison); aware values normalize to UTC
            if as_of.tzinfo is None or as_of.tzinfo.utcoffset(as_of) is None:
                raise RequestValidationError(
                    [Issue(InputErrorCode.INVALID_TIMESTAMP, "$.as_of", "as_of must be timezone-aware")]
                )
            cutoff = as_of.astimezone(UTC)
        else:
            cutoff = _check_timestamp(as_of, "$.as_of")
        issue = _first_structural_issue(validated_criteria, self.evidence, cutoff)
        if issue is not None:
            raise RequestValidationError([issue])
        try:
            return VerificationRequest(
                request_id=request_id,
                objective=objective,
                checkpoint_id=checkpoint_id,
                as_of=cutoff,
                criteria=validated_criteria,
                evidence=self.evidence,
                metadata=self.metadata,
            )
        except ValidationError:
            raise RequestValidationError(
                [Issue(InputErrorCode.INVALID_SCHEMA, "$", "request built from the trace failed validation")]
            ) from None


def _coerce_criteria(criteria: Sequence[Any]) -> list[object]:
    """Accept already-validated criterion models or plain mappings."""
    return [item if isinstance(item, dict) else _dump_criterion(item) for item in criteria]


def _dump_criterion(item: Any) -> object:
    return item.model_dump() if isinstance(item, (AssertionCriterion, VisualCriterion)) else item


def parse_trace(data: Mapping[str, object] | str | bytes) -> Trace:
    """Validate untrusted trace input and build a :class:`Trace`.

    Accepts a mapping, JSON text or UTF-8 bytes. Raises a safe
    :class:`RequestValidationError` whose first issue follows the same deterministic
    order as :func:`nitelos.parse_request` (wire discipline, unknown fields,
    schema_version, evidence items, metadata, then structural invariants). Issues
    never contain offending values.
    """
    try:
        return _build_trace(_ingest_trace(data))
    except (_Reject, _SchemaReject) as reject:
        raise RequestValidationError([reject.issue]) from None
