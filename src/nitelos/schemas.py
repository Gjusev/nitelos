"""Nitelos strict domain schemas and request parsing (contract v1).

Authority: docs/planning/03-domain-model-and-api.md (field tables, legal
states, limits, error taxonomy), 05-evidence-and-policies.md (validation
ordering), 07-security-and-privacy.md (safe errors and repr). Deviations and
interpretations are listed at the bottom of this docstring.

All models are Pydantic v2 ``strict`` (no string/number/bool coercion),
``extra="forbid"`` and ``frozen``. Free-form JSON payloads are deep-copied
into immutable values (mapping proxies and tuples) at validation time.
Timestamps accept RFC3339 ``Z`` strings (wire) and timezone-aware datetimes
(Python); naive datetimes and offset strings are rejected. Serialization in
JSON mode returns plain JSON with RFC3339 ``Z`` timestamps.

``parse_request`` reports the deterministic first error in this order:

1. wire size (UTF-8 bytes for text input, canonical JSON size for mappings),
   JSON syntax, duplicate keys, non-finite numbers, oversized integer
   literals, nesting depth (containers count one level each, root = 1);
2. the root value must be a JSON object;
3. unknown top-level fields (in input order);
4. fields in document-03 order: ``schema_version`` (missing → INVALID_SCHEMA,
   any other value → UNSUPPORTED_SCHEMA), ``request_id``, ``objective``,
   ``checkpoint_id``, ``as_of``, ``criteria`` (list bounds, then items in
   order), ``evidence`` (list bounds, then items in order, each item's
   payload size checked right after its shape), ``metadata`` (shape, then
   size). Within a list item the first failing field follows document-03
   field order; unknown fields inside an item are reported before known ones;
5. structural invariants: duplicate criterion ids, duplicate evidence ids,
   strictly ascending sequences, nondecreasing ``captured_at``,
   ``captured_at <= as_of``, criterion ``evidence_ids`` resolution,
   ``action.tool_result_id`` resolution, then aggregate action/screenshot
   counts.

Interpretations of underspecified contract text (conservative readings):

- over-limit *collection* sizes (criteria > 16, evidence > 128,
  ``evidence_ids`` > 16, ``in``-scalars > 64, request bytes/depth) yield
  LIMIT_EXCEEDED; scalar value bounds (string lengths, ``max_age_seconds``,
  subject map size) yield INVALID_SCHEMA;
- a zero-length ``criteria`` list is INVALID_SCHEMA (a lower bound, not a
  ceiling);
- byte-size ceilings (request, payload, metadata) are enforced at ingestion
  (``parse_request``); direct model construction enforces only count
  constraints;
- mapping input must contain only JSON values (tuples, datetimes and other
  Python types are rejected); JSON-object keys must be strings;
- ``expected`` for ``exists`` must be absent in wire input (explicit null is
  rejected); for ``equals`` an explicit null is a legal scalar;
- ``subject`` maps larger than 16 pairs are INVALID_SCHEMA (structural bound);
- Measurement cost fields are all-or-nothing with ``cost_amount``;
- wire timestamps accept at most 6 fractional digits (fromisoformat would
  otherwise silently truncate longer fractions);
- ``schema_version`` compared before any other field, so an unknown version
  is reported even when other fields are also invalid.
"""

from __future__ import annotations

import json
import math
import re
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from enum import StrEnum
from types import MappingProxyType
from typing import Annotated, Any, Literal, NoReturn, Self, cast

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    PlainSerializer,
    StringConstraints,
    TypeAdapter,
    ValidationError,
    ValidatorFunctionWrapHandler,
    WrapValidator,
    model_validator,
)
from pydantic_core import ErrorDetails

from nitelos._json import JsonError, JsonErrorKind, parse_json
from nitelos.errors import BackendErrorCode, InputErrorCode, Issue, RequestValidationError

# ---------------------------------------------------------------------------
# limits (document 03 "Limits"; hard ceilings, never truncation)
# ---------------------------------------------------------------------------

MAX_REQUEST_JSON_BYTES = 1_048_576
MAX_JSON_DEPTH = 16
MAX_PAYLOAD_BYTES = 65_536
MAX_METADATA_BYTES = 8_192
MAX_ACTIONS = 64
MAX_SCREENSHOTS = 16
MAX_CRITERIA = 16
MAX_EVIDENCE = 128


# ---------------------------------------------------------------------------
# enums whose values are part of the wire contract
# ---------------------------------------------------------------------------


class Scope(StrEnum):
    OBSERVED_STATE = "observed_state"
    BEHAVIORAL = "behavioral"
    EXTERNAL = "external"
    VISUAL = "visual"


class Phase(StrEnum):
    FINAL = "final"
    PENDING = "pending"


class Channel(StrEnum):
    DOM = "dom"
    ACCESSIBILITY = "accessibility"
    TOOL = "tool"
    EXTERNAL_API = "external_api"
    DATABASE = "database"
    HUMAN = "human"


class MediaType(StrEnum):
    PNG = "image/png"
    JPEG = "image/jpeg"


class Operator(StrEnum):
    EQUALS = "equals"
    IN = "in"
    EXISTS = "exists"


class ReportedStatus(StrEnum):
    COMPLETED = "completed"
    FAILED = "failed"
    UNKNOWN = "unknown"


class Grounding(StrEnum):
    REFERENCE_VALIDATED = "reference_validated"
    ASSERTION_CHECKED = "assertion_checked"
    MODEL_INFERRED = "model_inferred"


class ScoreKind(StrEnum):
    UNCALIBRATED_SCORE = "uncalibrated_score"
    UNCALIBRATED_PROBABILITY = "uncalibrated_probability"
    CALIBRATED_PROBABILITY = "calibrated_probability"


class ColorConversion(StrEnum):
    NONE = "none"
    GRAYSCALE_TO_RGB = "grayscale_to_rgb"
    RGBA_ON_WHITE = "rgba_on_white"


class CriterionState(StrEnum):
    SUPPORTED = "supported"
    REFUTED = "refuted"
    UNKNOWN = "unknown"


class Basis(StrEnum):
    DETERMINISTIC = "deterministic"
    MODEL_INFERRED = "model_inferred"
    NONE = "none"


class ExecutionStatus(StrEnum):
    OK = "ok"
    INPUT_ERROR = "input_error"
    BACKEND_ERROR = "backend_error"


class Decision(StrEnum):
    SUCCESS = "success"
    FAILURE = "failure"
    ABSTAINED = "abstained"


def _from_wire[EnumT: StrEnum](enum_cls: type[EnumT]) -> Callable[[object], object]:
    """Strict-mode enums reject raw strings; map valid wire strings to members."""

    def convert(value: object) -> object:
        if isinstance(value, enum_cls):
            return value
        if isinstance(value, str):
            try:
                return enum_cls(value)
            except ValueError:
                return value  # let strict core reject with a type error
        return value

    return convert


def _error_code_from_wire(value: object) -> object:
    if isinstance(value, (InputErrorCode, BackendErrorCode)):
        return value
    if isinstance(value, str):
        return InputErrorCode(value) if value in InputErrorCode.__members__ else BackendErrorCode(value)
    return value


WireScope = Annotated[Scope, BeforeValidator(_from_wire(Scope))]
WirePhase = Annotated[Phase, BeforeValidator(_from_wire(Phase))]
WireChannel = Annotated[Channel, BeforeValidator(_from_wire(Channel))]
WireMediaType = Annotated[MediaType, BeforeValidator(_from_wire(MediaType))]
WireReportedStatus = Annotated[ReportedStatus, BeforeValidator(_from_wire(ReportedStatus))]
WireOperator = Annotated[Operator, BeforeValidator(_from_wire(Operator))]
WireGrounding = Annotated[Grounding, BeforeValidator(_from_wire(Grounding))]
WireScoreKind = Annotated[ScoreKind, BeforeValidator(_from_wire(ScoreKind))]
WireColorConversion = Annotated[ColorConversion, BeforeValidator(_from_wire(ColorConversion))]
WireCriterionState = Annotated[CriterionState, BeforeValidator(_from_wire(CriterionState))]
WireBasis = Annotated[Basis, BeforeValidator(_from_wire(Basis))]
WireExecutionStatus = Annotated[ExecutionStatus, BeforeValidator(_from_wire(ExecutionStatus))]
WireDecision = Annotated[Decision, BeforeValidator(_from_wire(Decision))]
WireErrorCode = Annotated[InputErrorCode | BackendErrorCode, BeforeValidator(_error_code_from_wire)]

_ASSERTION_SCOPES = (Scope.OBSERVED_STATE, Scope.BEHAVIORAL, Scope.EXTERNAL)


def _wrap_assertion_scope(value: object, handler: ValidatorFunctionWrapHandler) -> Scope:
    converted = _from_wire(Scope)(value)
    if isinstance(converted, Scope):
        if converted not in _ASSERTION_SCOPES:
            raise ValueError("scope is not allowed for an assertion criterion")
        return converted
    return cast(Scope, handler(value))  # non-enum garbage: strict core reports the type error


def _wrap_visual_scope(value: object, handler: ValidatorFunctionWrapHandler) -> Scope:
    converted = _from_wire(Scope)(value)
    if isinstance(converted, Scope):
        if converted != Scope.VISUAL:
            raise ValueError("visual criteria allow only the visual scope")
        return converted
    return cast(Scope, handler(value))  # non-enum garbage: strict core reports the type error


AssertionScope = Annotated[Scope, WrapValidator(_wrap_assertion_scope)]
VisualScope = Annotated[Scope, WrapValidator(_wrap_visual_scope)]


# ---------------------------------------------------------------------------
# scalar annotated types
# ---------------------------------------------------------------------------

IDType = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")]
Sha256Type = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
JsonPointerType = Annotated[str, StringConstraints(pattern=r"^(/([^~/]|~[01])*)*$")]

_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}")
_RFC3339_Z = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d{1,6})?Z")


def _parse_utc_timestamp(value: object) -> object:
    if isinstance(value, datetime):
        if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
            raise ValueError("timestamp must be timezone-aware")
        return value.astimezone(UTC)
    if isinstance(value, str):
        if _RFC3339_Z.fullmatch(value) is None:
            raise ValueError("timestamp must be an RFC3339 UTC string ending in Z")
        return datetime.fromisoformat(value)
    return value  # strict core rejects other types


def _dump_utc_timestamp(value: datetime) -> str:
    text = value.isoformat()
    return text[:-6] + "Z" if text.endswith("+00:00") else text


UTCDateTime = Annotated[
    datetime,
    BeforeValidator(_parse_utc_timestamp),
    PlainSerializer(_dump_utc_timestamp, return_type=str, when_used="json"),
]


def _tup(value: object) -> object:
    """Strict tuples reject lists; wire JSON only produces lists."""
    return tuple(value) if isinstance(value, list) else value


# ---------------------------------------------------------------------------
# frozen JSON values (deep-copied immutable containers)
# ---------------------------------------------------------------------------


def _freeze_json(value: object, depth: int = 1) -> object:
    if value is None or isinstance(value, (bool, str, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("non-finite numbers are not allowed")
        return value
    if isinstance(value, Mapping):
        if depth > MAX_JSON_DEPTH:
            raise ValueError("nesting exceeds the allowed depth")
        out: dict[str, object] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError("object keys must be strings")
            out[key] = _freeze_json(item, depth + 1)
        return MappingProxyType(out)
    if isinstance(value, (list, tuple)):
        if depth > MAX_JSON_DEPTH:
            raise ValueError("nesting exceeds the allowed depth")
        return tuple(_freeze_json(item, depth + 1) for item in value)
    raise ValueError("value is not JSON")


def _thaw_json(value: object) -> object:
    if isinstance(value, Mapping):
        return {key: _thaw_json(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw_json(item) for item in value]
    return value


def _wrap_json_object(value: object, handler: ValidatorFunctionWrapHandler) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError("value must be a JSON object")
    frozen = _freeze_json(value)
    if not isinstance(frozen, Mapping):
        raise ValueError("value must be a JSON object")
    return cast(Mapping[str, object], frozen)


def _wrap_subject_map(value: object, handler: ValidatorFunctionWrapHandler) -> Mapping[str, str]:
    if not isinstance(value, Mapping):
        raise ValueError("value must be a JSON object")
    if not 1 <= len(value) <= 16:
        raise ValueError("map must contain between 1 and 16 pairs")
    out: dict[str, str] = {}
    for key, item in value.items():
        if not isinstance(key, str) or not isinstance(item, str):
            raise ValueError("map keys and values must be strings")
        out[key] = item
    return MappingProxyType(out)


def _wrap_str_map(value: object, handler: ValidatorFunctionWrapHandler) -> Mapping[str, str]:
    if not isinstance(value, Mapping):
        raise ValueError("value must be a JSON object")
    out: dict[str, str] = {}
    for key, item in value.items():
        if not isinstance(key, str) or not isinstance(item, str):
            raise ValueError("map keys and values must be strings")
        out[key] = item
    return MappingProxyType(out)


def _wrap_float_map(value: object, handler: ValidatorFunctionWrapHandler) -> Mapping[str, float]:
    if not isinstance(value, Mapping):
        raise ValueError("value must be a JSON object")
    out: dict[str, float] = {}
    for key, item in value.items():
        if not isinstance(key, str):
            raise ValueError("map keys must be strings")
        if isinstance(item, bool) or not isinstance(item, (int, float)):
            raise ValueError("map values must be numbers")
        if not math.isfinite(item):
            raise ValueError("map values must be finite")
        if item < 0:
            raise ValueError("map values must be nonnegative")
        out[key] = float(item)
    return MappingProxyType(out)


_Thawed = PlainSerializer(_thaw_json, when_used="always")
FrozenJsonObject = Annotated[Mapping[str, object], WrapValidator(_wrap_json_object), _Thawed]
SubjectMap = Annotated[Mapping[str, str], WrapValidator(_wrap_subject_map), _Thawed]
FloatMap = Annotated[Mapping[str, float], WrapValidator(_wrap_float_map), _Thawed]
StrMap = Annotated[Mapping[str, str], WrapValidator(_wrap_str_map), _Thawed]

# ---------------------------------------------------------------------------
# canonical JSON v1
# ---------------------------------------------------------------------------


def _canonicalize(value: object) -> object:
    if value is None or isinstance(value, (bool, str, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("non-finite numbers cannot be canonicalized")
        return value
    if isinstance(value, Mapping):
        out: dict[str, object] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError("object keys must be strings to canonicalize")
            out[key] = _canonicalize(item)
        return out
    if isinstance(value, (list, tuple)):
        return [_canonicalize(item) for item in value]
    raise ValueError("value is not JSON")


def canonical_json(value: object) -> str:
    """Nitelos canonical JSON v1: UTF-8, sorted keys, compact separators,
    original array order, no non-finite numbers.

    Not an RFC 8785 (JCS) implementation; it is the stable form used for
    fingerprints and size accounting. Raises ValueError for non-JSON input.
    """
    return json.dumps(_canonicalize(value), ensure_ascii=False, separators=(",", ":"), sort_keys=True)


# ---------------------------------------------------------------------------
# base model
# ---------------------------------------------------------------------------


class _Model(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)


# ---------------------------------------------------------------------------
# criteria
# ---------------------------------------------------------------------------


class _CriterionBase(_Model):
    """Fields shared by every criterion (document 03 "Criteria")."""

    id: IDType
    description: str = Field(min_length=1, max_length=1024)
    evidence_ids: Annotated[tuple[IDType, ...], BeforeValidator(_tup), Field(max_length=16)]
    subject: SubjectMap
    max_age_seconds: int = Field(default=300, ge=0, le=86400)

    @model_validator(mode="after")
    def _check_unique_evidence_ids(self) -> Self:
        if len(set(self.evidence_ids)) != len(self.evidence_ids):
            raise ValueError("evidence_ids must be unique within a criterion")
        return self


def _check_scalar_finite(value: object) -> None:
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("expected values must be finite")


_ExpectedList = Annotated[
    tuple[bool | int | float | str | None, ...],
    BeforeValidator(_tup),
    Field(min_length=1, max_length=64),
]


class AssertionCriterion(_CriterionBase):
    """Deterministic JSON-pointer assertion; semantics are evaluated in NIT-004."""

    kind: Literal["assertion"]
    scope: AssertionScope
    pointer: JsonPointerType
    operator: WireOperator
    expected: bool | int | float | str | _ExpectedList | None = None

    @model_validator(mode="after")
    def _check_expected_shape(self) -> Self:
        if self.operator == Operator.EQUALS:
            if "expected" not in self.model_fields_set or isinstance(self.expected, tuple):
                raise ValueError("equals requires expected to be exactly one JSON scalar")
            _check_scalar_finite(self.expected)
        elif self.operator == Operator.IN:
            if "expected" not in self.model_fields_set or not isinstance(self.expected, tuple):
                raise ValueError("in requires expected to be a list of 1 to 64 JSON scalars")
            for value in self.expected:
                _check_scalar_finite(value)
        elif self.operator == Operator.EXISTS and "expected" in self.model_fields_set:
            raise ValueError("expected must be absent for the exists operator")
        return self

    def model_dump(self, **kwargs: Any) -> dict[str, Any]:
        dumped = super().model_dump(**kwargs)
        if self.operator == Operator.EXISTS:
            dumped.pop("expected", None)  # absent in wire form, never an explicit null
        return dumped

    def __repr__(self) -> str:
        return (
            f"{type(self).__name__}(id={self.id!r}, scope={self.scope!s}, "
            f"evidence_ids={len(self.evidence_ids)})"
        )


class VisualCriterion(_CriterionBase):
    """Visually assessable criterion; decided by model inference when policy allows."""

    kind: Literal["visual"]
    scope: VisualScope

    def __repr__(self) -> str:
        return (
            f"{type(self).__name__}(id={self.id!r}, scope={self.scope!s}, "
            f"evidence_ids={len(self.evidence_ids)})"
        )


Criterion = Annotated[AssertionCriterion | VisualCriterion, Field(discriminator="kind")]


# ---------------------------------------------------------------------------
# evidence
# ---------------------------------------------------------------------------


class Evidence(_Model):
    """Common evidence fields (document 03 "Evidence"); use the kind subclasses.

    The hashing factory classmethods delegate to ``nitelos.evidence`` (imported
    lazily so this contract module stays light): screenshots digest the exact
    artifact bytes; observations and actions digest canonical JSON v1 payloads.
    Factories never accept a ``trusted`` flag.
    """

    id: IDType
    sequence: int = Field(ge=0)
    captured_at: UTCDateTime
    checkpoint_id: IDType
    source_id: IDType
    subject: SubjectMap
    phase: WirePhase
    sha256: Sha256Type

    def __repr__(self) -> str:
        return f"{type(self).__name__}(id={self.id!r}, sequence={self.sequence}, phase={self.phase!s})"

    @classmethod
    def screenshot(
        cls,
        *,
        id: str,
        artifact_id: str,
        data: bytes | bytearray | memoryview,
        sequence: int,
        captured_at: datetime | str,
        checkpoint_id: str,
        source_id: str,
        subject: Mapping[str, str],
        phase: Phase | str,
    ) -> ScreenshotEvidence:
        """Inspect artifact bytes (signature, dimensions, digest) and build the event."""
        from nitelos.evidence import build_screenshot  # noqa: PLC0415 - lazy import keeps this module light

        return build_screenshot(
            id=id,
            artifact_id=artifact_id,
            data=data,
            sequence=sequence,
            captured_at=captured_at,
            checkpoint_id=checkpoint_id,
            source_id=source_id,
            subject=subject,
            phase=phase,
        )

    @classmethod
    def observation(
        cls,
        *,
        id: str,
        sequence: int,
        captured_at: datetime | str,
        checkpoint_id: str,
        source_id: str,
        subject: Mapping[str, str],
        phase: Phase | str,
        channel: Channel | str,
        data: Mapping[str, object],
    ) -> ObservationEvidence:
        """Build an observation whose sha256 is the canonical JSON v1 digest of ``data``."""
        from nitelos.evidence import build_observation  # noqa: PLC0415 - lazy import keeps this module light

        return build_observation(
            id=id,
            sequence=sequence,
            captured_at=captured_at,
            checkpoint_id=checkpoint_id,
            source_id=source_id,
            subject=subject,
            phase=phase,
            channel=channel,
            data=data,
        )

    @classmethod
    def action(
        cls,
        *,
        id: str,
        sequence: int,
        captured_at: datetime | str,
        checkpoint_id: str,
        source_id: str,
        subject: Mapping[str, str],
        phase: Phase | str,
        name: str,
        arguments: Mapping[str, object],
        reported_status: ReportedStatus | str,
        tool_result_id: str | None = None,
    ) -> ActionEvidence:
        """Build an action; the digest covers {name, arguments, reported_status, tool_result_id}."""
        from nitelos.evidence import build_action  # noqa: PLC0415 - lazy import keeps this module light

        return build_action(
            id=id,
            sequence=sequence,
            captured_at=captured_at,
            checkpoint_id=checkpoint_id,
            source_id=source_id,
            subject=subject,
            phase=phase,
            name=name,
            arguments=arguments,
            reported_status=reported_status,
            tool_result_id=tool_result_id,
        )


class ScreenshotEvidence(Evidence):
    """Image artifact capture; bytes live in the ArtifactStore (NIT-003)."""

    kind: Literal["screenshot"]
    artifact_id: IDType
    media_type: WireMediaType
    width: int = Field(ge=1)
    height: int = Field(ge=1)


class ObservationEvidence(Evidence):
    """Normalized JSON observation on a named channel; content is untrusted."""

    kind: Literal["observation"]
    channel: WireChannel
    data: FrozenJsonObject


class ActionEvidence(Evidence):
    """Agent action record; may reference a later tool-channel observation."""

    kind: Literal["action"]
    name: str = Field(min_length=1, max_length=128)
    arguments: FrozenJsonObject
    reported_status: WireReportedStatus
    tool_result_id: IDType | None = None


EvidenceItem = Annotated[
    ScreenshotEvidence | ObservationEvidence | ActionEvidence, Field(discriminator="kind")
]


# ---------------------------------------------------------------------------
# evidence references and scores
# ---------------------------------------------------------------------------


class EvidenceRef(_Model):
    """Citation of one evidence item: a pointer for structured data or a box
    for screenshots, never both. Box bounds against decoded dimensions are
    checked in NIT-003."""

    evidence_id: IDType
    pointer: JsonPointerType | None = None
    bbox: Annotated[tuple[int, int, int, int], BeforeValidator(_tup)] | None = None
    grounding: WireGrounding = Grounding.REFERENCE_VALIDATED

    @model_validator(mode="after")
    def _check_exactly_one_selector(self) -> Self:
        if (self.pointer is None) == (self.bbox is None):
            raise ValueError("exactly one of pointer or bbox must be set")
        if self.bbox is not None:
            x0, y0, x1, y1 = self.bbox
            if not (0 <= x0 < x1 and 0 <= y0 < y1):
                raise ValueError("bbox must satisfy 0 <= x0 < x1 and 0 <= y0 < y1")
        return self


class Score(_Model):
    """Backend-reported score. ``calibrated_probability`` is representable but
    rejected at runtime in v0.1 (UNSUPPORTED_CALIBRATION, NIT-007)."""

    kind: WireScoreKind
    value: float = Field(allow_inf_nan=False)
    target: str = Field(min_length=1)
    scale: str | None = None
    calibration_id: IDType | None = None

    @model_validator(mode="after")
    def _check_kind_value(self) -> Self:
        probabilities = (ScoreKind.UNCALIBRATED_PROBABILITY, ScoreKind.CALIBRATED_PROBABILITY)
        if self.kind in probabilities and not 0.0 <= self.value <= 1.0:
            raise ValueError("probability values must be within [0, 1]")
        if self.kind == ScoreKind.UNCALIBRATED_SCORE and not self.scale:
            raise ValueError("scale is required for uncalibrated_score")
        return self


class BackendFinding(_Model):
    """A backend's claim about one criterion; untrusted, validated in NIT-007."""

    criterion_id: IDType
    state: WireCriterionState
    evidence_refs: Annotated[tuple[EvidenceRef, ...], BeforeValidator(_tup), Field(max_length=16)] = ()
    score: Score | None = None
    rationale: str | None = Field(default=None, max_length=2048)

    def __repr__(self) -> str:
        return (
            f"BackendFinding(criterion_id={self.criterion_id!r}, state={self.state!s}, "
            f"evidence_refs={len(self.evidence_refs)})"
        )


# ---------------------------------------------------------------------------
# diagnostics
# ---------------------------------------------------------------------------


class BackendDescriptor(_Model):
    """Identity of the backend that produced findings; hashes pin behavior."""

    id: str = Field(min_length=1)
    version: str = Field(min_length=1)
    model_id: str | None = None
    model_revision: str | None = None
    prompt_hash: Sha256Type | None = None
    preprocessing_hash: Sha256Type | None = None
    runtime_lock_hash: Sha256Type | None = None


class Measurements(_Model):
    """Nullable resource measurements; cost fields are all-or-nothing."""

    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    peak_rss_bytes: int | None = Field(default=None, ge=0)
    peak_device_bytes: int | None = Field(default=None, ge=0)
    cost_amount: float | None = Field(default=None, allow_inf_nan=False, ge=0)
    cost_currency: str | None = None
    cost_source: str | None = None
    cost_as_of: UTCDateTime | None = None
    unavailable_reasons: StrMap = Field(default_factory=lambda: MappingProxyType({}))

    @model_validator(mode="after")
    def _check_cost_fields(self) -> Self:
        trio = (self.cost_currency, self.cost_source, self.cost_as_of)
        if self.cost_amount is not None and any(part is None for part in trio):
            raise ValueError("cost currency/source/as_of are required when cost_amount is present")
        if self.cost_amount is None and any(part is not None for part in trio):
            raise ValueError("cost currency/source/as_of require cost_amount")
        return self


class PreprocessingRecord(_Model):
    """Image preprocessing actually applied; never invents dimensions."""

    evidence_id: IDType
    input_width: int = Field(ge=1)
    input_height: int = Field(ge=1)
    color_conversion: WireColorConversion
    processor_longest_edge: int | None = Field(default=None, ge=1)
    output_width: int | None = Field(default=None, ge=1)
    output_height: int | None = Field(default=None, ge=1)
    patch_count: int | None = Field(default=None, ge=0)


class Diagnostics(_Model):
    """Execution diagnostics; serializes without request text or payload values."""

    package_version: str = Field(min_length=1)
    schema_version: str = Field(min_length=1)
    request_hash: Sha256Type | None = None
    evidence_manifest_hash: Sha256Type | None = None
    policy_id: str = Field(min_length=1)
    policy_version: str = Field(min_length=1)
    policy_hash: Sha256Type
    backend: BackendDescriptor
    elapsed_ms: float = Field(allow_inf_nan=False, ge=0)
    model_load_ms: float | None = Field(default=None, allow_inf_nan=False, ge=0)
    criterion_durations_ms: FloatMap = Field(default_factory=lambda: MappingProxyType({}))
    omitted_context_ids: Annotated[tuple[IDType, ...], BeforeValidator(_tup)] = ()
    preprocessing: Annotated[tuple[PreprocessingRecord, ...], BeforeValidator(_tup)] = ()
    measurements: Measurements
    limitations: Annotated[tuple[str, ...], BeforeValidator(_tup)] = ()


# ---------------------------------------------------------------------------
# results
# ---------------------------------------------------------------------------


class ErrorInfo(_Model):
    """Safe error payload: code, fixed message, optional field path."""

    code: WireErrorCode
    safe_message: str = Field(min_length=1)
    field_path: str | None = None
    retryable: bool = False

    @model_validator(mode="after")
    def _check_retryable(self) -> Self:
        if self.retryable and self.code not in (BackendErrorCode.TIMEOUT, BackendErrorCode.BUSY):
            raise ValueError("only TIMEOUT and BUSY are retryable in v0.1")
        return self


class CriterionEvaluation(_Model):
    """One per-reference deterministic comparison inside a criterion result."""

    evidence_ref: EvidenceRef
    state: WireCriterionState
    reason_codes: Annotated[tuple[str, ...], BeforeValidator(_tup)] = ()


class CriterionResult(_Model):
    """Final outcome for one criterion. Model rationale is never a field here;
    default serialization therefore omits it entirely."""

    criterion_id: IDType
    state: WireCriterionState
    basis: WireBasis
    scope: WireScope
    evidence_refs: Annotated[tuple[EvidenceRef, ...], BeforeValidator(_tup)] = ()
    reason_codes: Annotated[tuple[str, ...], BeforeValidator(_tup)] = ()
    score: Score | None = None
    limitations: Annotated[tuple[str, ...], BeforeValidator(_tup)] = ()
    evaluations: Annotated[tuple[CriterionEvaluation, ...], BeforeValidator(_tup)] = ()

    @model_validator(mode="before")
    @classmethod
    def _dedup_reason_codes(cls, data: object) -> object:
        if isinstance(data, dict):
            codes = data.get("reason_codes")
            if isinstance(codes, (list, tuple)):
                return {**data, "reason_codes": tuple(dict.fromkeys(codes))}
        return data

    def __repr__(self) -> str:
        return (
            f"CriterionResult(criterion_id={self.criterion_id!r}, state={self.state!s}, "
            f"basis={self.basis!s}, evaluations={len(self.evaluations)})"
        )


class VerificationResult(_Model):
    """Final verification outcome enforcing the five legal (status, decision) pairs."""

    schema_version: Literal["1"] = "1"
    request_id: IDType
    verification_id: IDType
    execution_status: WireExecutionStatus
    decision: WireDecision | None = None
    criteria: Annotated[tuple[CriterionResult, ...], BeforeValidator(_tup)] = ()
    reason_codes: Annotated[tuple[str, ...], BeforeValidator(_tup)] = ()
    error: ErrorInfo | None = None
    diagnostics: Diagnostics

    @model_validator(mode="before")
    @classmethod
    def _dedup_reason_codes(cls, data: object) -> object:
        if isinstance(data, dict):
            codes = data.get("reason_codes")
            if isinstance(codes, (list, tuple)):
                return {**data, "reason_codes": tuple(dict.fromkeys(codes))}
        return data

    @model_validator(mode="after")
    def _check_legal_states(self) -> Self:
        if self.execution_status == ExecutionStatus.OK:
            if self.error is not None:
                raise ValueError("error must be null when execution_status is ok")
            if self.decision is None:
                raise ValueError("decision is required when execution_status is ok")
        else:
            if self.error is None:
                raise ValueError("error is required when execution_status is not ok")
            if self.decision is not None:
                raise ValueError("decision must be null when execution_status is not ok")
            if self.execution_status == ExecutionStatus.INPUT_ERROR and self.criteria:
                raise ValueError("criteria must be empty on input errors")
        return self

    def __repr__(self) -> str:
        return (
            f"VerificationResult(verification_id={self.verification_id!r}, "
            f"execution_status={self.execution_status!s}, decision={self.decision!s}, "
            f"criteria={len(self.criteria)}, reason_codes={len(self.reason_codes)})"
        )


# ---------------------------------------------------------------------------
# request
# ---------------------------------------------------------------------------


class VerificationRequest(_Model):
    """Immutable verification request (document 03 "Request").

    Structural invariants (unique ids, ascending sequences, timestamp and
    reference rules, action/screenshot counts) hold for direct construction
    too; ``parse_request`` maps violations to safe coded issues.
    """

    schema_version: Literal["1"] = "1"
    request_id: IDType
    objective: str = Field(min_length=1, max_length=4096)
    checkpoint_id: IDType
    as_of: UTCDateTime
    criteria: Annotated[
        tuple[Criterion, ...], BeforeValidator(_tup), Field(min_length=1, max_length=MAX_CRITERIA)
    ]
    evidence: Annotated[tuple[EvidenceItem, ...], BeforeValidator(_tup), Field(max_length=MAX_EVIDENCE)]
    metadata: FrozenJsonObject = Field(default_factory=lambda: MappingProxyType({}))

    @model_validator(mode="after")
    def _check_request_invariants(self) -> Self:
        if not self.objective.strip():
            raise ValueError("objective must not be blank")
        issue = _first_structural_issue(self.criteria, self.evidence, self.as_of)
        if issue is not None:
            raise ValueError(str(issue))
        return self

    def __repr__(self) -> str:
        return (
            f"VerificationRequest(request_id={self.request_id!r}, checkpoint_id={self.checkpoint_id!r}, "
            f"criteria={len(self.criteria)}, evidence={len(self.evidence)})"
        )


# ---------------------------------------------------------------------------
# structural invariants (shared by parse_request and direct construction)
# ---------------------------------------------------------------------------

AnyCriterion = AssertionCriterion | VisualCriterion
AnyEvidence = ScreenshotEvidence | ObservationEvidence | ActionEvidence


def _first_structural_issue(
    criteria: Sequence[AnyCriterion], evidence: Sequence[AnyEvidence], as_of: datetime
) -> Issue | None:
    """First invariant violation in the documented order, or None."""
    seen: set[str] = set()
    for index, criterion in enumerate(criteria):
        if criterion.id in seen:
            return Issue(InputErrorCode.DUPLICATE_ID, f"$.criteria[{index}].id", "duplicate criterion id")
        seen.add(criterion.id)
    seen.clear()
    for index, item in enumerate(evidence):
        if item.id in seen:
            return Issue(InputErrorCode.DUPLICATE_ID, f"$.evidence[{index}].id", "duplicate evidence id")
        seen.add(item.id)
    previous_sequence: int | None = None
    for index, item in enumerate(evidence):
        if previous_sequence is not None and item.sequence <= previous_sequence:
            return Issue(
                InputErrorCode.INVALID_SEQUENCE,
                f"$.evidence[{index}].sequence",
                "sequence numbers must be strictly ascending",
            )
        previous_sequence = item.sequence
    previous_time: datetime | None = None
    for index, item in enumerate(evidence):
        if previous_time is not None and item.captured_at < previous_time:
            return Issue(
                InputErrorCode.INVALID_TIMESTAMP,
                f"$.evidence[{index}].captured_at",
                "captured_at timestamps must be nondecreasing",
            )
        previous_time = item.captured_at
    for index, item in enumerate(evidence):
        if item.captured_at > as_of:
            return Issue(
                InputErrorCode.INVALID_TIMESTAMP,
                f"$.evidence[{index}].captured_at",
                "captured_at must not be later than as_of",
            )
    known = {item.id for item in evidence}
    for index, criterion in enumerate(criteria):
        for position, evidence_id in enumerate(criterion.evidence_ids):
            if evidence_id not in known:
                return Issue(
                    InputErrorCode.UNKNOWN_REFERENCE,
                    f"$.criteria[{index}].evidence_ids[{position}]",
                    "referenced evidence id is not declared",
                )
    by_id: dict[str, AnyEvidence] = {item.id: item for item in evidence}
    for index, item in enumerate(evidence):
        if isinstance(item, ActionEvidence) and item.tool_result_id is not None:
            target = by_id.get(item.tool_result_id)
            if (
                not isinstance(target, ObservationEvidence)
                or target.channel != Channel.TOOL
                or target.sequence <= item.sequence
            ):
                return Issue(
                    InputErrorCode.UNKNOWN_REFERENCE,
                    f"$.evidence[{index}].tool_result_id",
                    "tool_result_id must reference a later tool-channel observation",
                )
    actions = sum(isinstance(item, ActionEvidence) for item in evidence)
    if actions > MAX_ACTIONS:
        return Issue(InputErrorCode.LIMIT_EXCEEDED, "$.evidence", "too many action evidence items")
    screenshots = sum(isinstance(item, ScreenshotEvidence) for item in evidence)
    if screenshots > MAX_SCREENSHOTS:
        return Issue(InputErrorCode.LIMIT_EXCEEDED, "$.evidence", "too many screenshot evidence items")
    return None


# ---------------------------------------------------------------------------
# parse_request: deterministic fail-first validation
# ---------------------------------------------------------------------------

_ENVELOPE_FIELDS = (
    "schema_version",
    "request_id",
    "objective",
    "checkpoint_id",
    "as_of",
    "criteria",
    "evidence",
    "metadata",
)
_ENVELOPE_SET = frozenset(_ENVELOPE_FIELDS)

_CRITERION_COMMON_ORDER = ("id", "description", "scope", "evidence_ids", "subject", "max_age_seconds")
_ASSERTION_ORDER = (*_CRITERION_COMMON_ORDER, "pointer", "operator", "expected")
_EVIDENCE_COMMON_ORDER = (
    "id",
    "kind",
    "sequence",
    "captured_at",
    "checkpoint_id",
    "source_id",
    "subject",
    "phase",
    "sha256",
)
_SCREENSHOT_ORDER = (*_EVIDENCE_COMMON_ORDER, "artifact_id", "media_type", "width", "height")
_OBSERVATION_ORDER = (*_EVIDENCE_COMMON_ORDER, "channel", "data")
_ACTION_ORDER = (*_EVIDENCE_COMMON_ORDER, "name", "arguments", "reported_status", "tool_result_id")

_TA_CRITERION = TypeAdapter(Criterion)
_TA_EVIDENCE = TypeAdapter(EvidenceItem)

_TIMESTAMP_FIELDS = frozenset({"captured_at", "as_of", "cost_as_of"})
_COUNTED_COLLECTIONS = frozenset({"evidence_ids", "expected"})


class _Reject(Exception):
    """Internal control flow carrying one safe issue."""

    def __init__(self, issue: Issue) -> None:
        super().__init__(str(issue))
        self.issue = issue


def _reject(code: InputErrorCode, path: str, message: str) -> NoReturn:
    raise _Reject(Issue(code, path, message))


def _loc_tail(loc: Sequence[int | str]) -> str:
    parts: list[str] = []
    for part in loc:
        if isinstance(part, int):
            parts.append(f"[{part}]")
        elif not parts:
            parts.append(f".{part}")
    return "".join(parts)


def _issue_from_validation_error(
    error: ValidationError, base: str, tag: str, order: tuple[str, ...], blame: str
) -> Issue:
    """Derive the first issue from pydantic errors using our own field order."""

    def rank(details: ErrorDetails) -> tuple[int, int]:
        loc = tuple(details["loc"])
        if tag and loc and loc[0] == tag:
            loc = loc[1:]
        if not loc:
            return len(order) + 1, 0  # model-level errors after field errors
        first = loc[0]
        name = first if isinstance(first, str) else ""
        if name in order:
            return order.index(name), 0
        return -1, 0  # unknown/extra fields before known-field errors

    def normalized_loc(details: ErrorDetails) -> tuple[int | str, ...]:
        loc = tuple(details["loc"])
        if tag and loc and loc[0] == tag:
            loc = loc[1:]
        return loc

    details = min(error.errors(), key=rank)
    loc = normalized_loc(details)
    if not loc:
        suffix = f".{blame}" if blame else ""
        return Issue(InputErrorCode.INVALID_SCHEMA, f"{base}{suffix}", "value failed model validation")
    first = loc[0]
    name = first if isinstance(first, str) else ""
    if name in _TIMESTAMP_FIELDS:
        return Issue(InputErrorCode.INVALID_TIMESTAMP, base + _loc_tail(loc), "invalid timestamp")
    if name == "pointer":
        return Issue(InputErrorCode.INVALID_POINTER, base + _loc_tail(loc), "invalid JSON pointer")
    if details["type"] == "too_long" and name in _COUNTED_COLLECTIONS:
        return Issue(InputErrorCode.LIMIT_EXCEEDED, base + _loc_tail(loc), "too many values")
    return Issue(InputErrorCode.INVALID_SCHEMA, base + _loc_tail(loc), "value failed model validation")


def _check_json_shape(value: object, path: str, depth: int) -> None:
    if value is None or isinstance(value, (bool, str, int)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            _reject(InputErrorCode.INVALID_SCHEMA, path, "non-finite numbers are not allowed")
        return
    if isinstance(value, Mapping):
        if depth > MAX_JSON_DEPTH:
            _reject(InputErrorCode.LIMIT_EXCEEDED, path, "nesting exceeds the allowed depth")
        for key, item in value.items():
            if not isinstance(key, str):
                _reject(InputErrorCode.INVALID_SCHEMA, path, "object keys must be strings")
            _check_json_shape(item, f"{path}.{key}", depth + 1)
        return
    if isinstance(value, list):
        if depth > MAX_JSON_DEPTH:
            _reject(InputErrorCode.LIMIT_EXCEEDED, path, "nesting exceeds the allowed depth")
        for index, item in enumerate(value):
            _check_json_shape(item, f"{path}[{index}]", depth + 1)
        return
    _reject(InputErrorCode.INVALID_SCHEMA, path, "value is not JSON")


def _check_id(value: object, path: str) -> str:
    if not isinstance(value, str) or _ID_RE.fullmatch(value) is None:
        _reject(InputErrorCode.INVALID_SCHEMA, path, "must be an ID string")
    return value


def _check_bounded_string(value: object, path: str, maximum: int, *, nonblank: bool = False) -> str:
    if not isinstance(value, str):
        _reject(InputErrorCode.INVALID_SCHEMA, path, "must be a string")
    if not 1 <= len(value) <= maximum:
        _reject(InputErrorCode.INVALID_SCHEMA, path, "string length is out of range")
    if nonblank and not value.strip():
        _reject(InputErrorCode.INVALID_SCHEMA, path, "must not be blank")
    return value


def _check_timestamp(value: object, path: str) -> datetime:
    try:
        parsed = _parse_utc_timestamp(value)
    except ValueError:
        _reject(InputErrorCode.INVALID_TIMESTAMP, path, "must be an RFC3339 UTC string ending in Z")
    if not isinstance(parsed, datetime):
        _reject(InputErrorCode.INVALID_TIMESTAMP, path, "must be an RFC3339 UTC string")
    return parsed


def _validate_criterion(item: object, path: str) -> AnyCriterion:
    if not isinstance(item, Mapping):
        _reject(InputErrorCode.INVALID_SCHEMA, path, "criterion must be a JSON object")
    kind = item.get("kind")
    order: tuple[str, ...]
    if kind == "assertion":
        order, blame = _ASSERTION_ORDER, "expected"
    elif kind == "visual":
        order, blame = _CRITERION_COMMON_ORDER, ""
    else:
        _reject(InputErrorCode.INVALID_SCHEMA, path, "unknown criterion kind")
    evidence_ids = item.get("evidence_ids")
    if isinstance(evidence_ids, list):
        seen: set[str] = set()
        for position, evidence_id in enumerate(evidence_ids):
            if isinstance(evidence_id, str):
                if evidence_id in seen:
                    _reject(
                        InputErrorCode.INVALID_SCHEMA,
                        f"{path}.evidence_ids[{position}]",
                        "duplicate evidence id in criterion",
                    )
                seen.add(evidence_id)
    expected = item.get("expected")
    if isinstance(expected, list) and len(expected) > 64:
        _reject(InputErrorCode.LIMIT_EXCEEDED, f"{path}.expected", "too many expected values")
    try:
        validated = _TA_CRITERION.validate_python(dict(item))
    except ValidationError as error:
        raise _Reject(_issue_from_validation_error(error, path, str(kind), order, blame)) from None
    return validated


def _validate_criteria(raw: object) -> tuple[AnyCriterion, ...]:
    path = "$.criteria"
    if not isinstance(raw, list):
        _reject(InputErrorCode.INVALID_SCHEMA, path, "must be a list")
    if not raw:
        _reject(InputErrorCode.INVALID_SCHEMA, path, "at least one criterion is required")
    if len(raw) > MAX_CRITERIA:
        _reject(InputErrorCode.LIMIT_EXCEEDED, path, "too many criteria")
    return tuple(_validate_criterion(item, f"{path}[{index}]") for index, item in enumerate(raw))


def _canonical_size(value: object) -> int:
    return len(canonical_json(value).encode("utf-8"))


def _validate_evidence_item(item: object, path: str) -> AnyEvidence:
    if not isinstance(item, Mapping):
        _reject(InputErrorCode.INVALID_SCHEMA, path, "evidence must be a JSON object")
    kind = item.get("kind")
    order: tuple[str, ...]
    if kind == "screenshot":
        order = _SCREENSHOT_ORDER
    elif kind == "observation":
        order = _OBSERVATION_ORDER
    elif kind == "action":
        order = _ACTION_ORDER
    else:
        _reject(InputErrorCode.INVALID_SCHEMA, path, "unknown evidence kind")
    try:
        validated = _TA_EVIDENCE.validate_python(dict(item))
    except ValidationError as error:
        raise _Reject(_issue_from_validation_error(error, path, str(kind), order, "")) from None
    if isinstance(validated, ObservationEvidence):
        payload, field = validated.data, "data"
    elif isinstance(validated, ActionEvidence):
        payload, field = validated.arguments, "arguments"
    else:
        return validated
    if _canonical_size(payload) > MAX_PAYLOAD_BYTES:
        _reject(InputErrorCode.LIMIT_EXCEEDED, f"{path}.{field}", "payload exceeds its size limit")
    return validated


def _validate_evidence(raw: object) -> tuple[AnyEvidence, ...]:
    path = "$.evidence"
    if not isinstance(raw, list):
        _reject(InputErrorCode.INVALID_SCHEMA, path, "must be a list")
    if len(raw) > MAX_EVIDENCE:
        _reject(InputErrorCode.LIMIT_EXCEEDED, path, "too many evidence items")
    return tuple(_validate_evidence_item(item, f"{path}[{index}]") for index, item in enumerate(raw))


def _validate_metadata(raw: object) -> None:
    if not isinstance(raw, Mapping):
        _reject(InputErrorCode.INVALID_SCHEMA, "$.metadata", "must be a JSON object")
    try:
        _freeze_json(dict(raw))
    except ValueError:
        _reject(InputErrorCode.INVALID_SCHEMA, "$.metadata", "must contain only JSON values")
    if _canonical_size(dict(raw)) > MAX_METADATA_BYTES:
        _reject(InputErrorCode.LIMIT_EXCEEDED, "$.metadata", "metadata exceeds its size limit")


def _build_request(mapping: Mapping[str, object]) -> VerificationRequest:
    for key in mapping:
        if key not in _ENVELOPE_SET:
            _reject(InputErrorCode.INVALID_SCHEMA, f"$.{key}", "unknown field")
    if "schema_version" not in mapping:
        _reject(InputErrorCode.INVALID_SCHEMA, "$.schema_version", "missing required field")
    if mapping["schema_version"] != "1":
        _reject(InputErrorCode.UNSUPPORTED_SCHEMA, "$.schema_version", "unsupported schema version")
    for field in ("request_id", "objective", "checkpoint_id", "as_of", "criteria", "evidence"):
        if field not in mapping:
            _reject(InputErrorCode.INVALID_SCHEMA, f"$.{field}", "missing required field")
    _check_id(mapping["request_id"], "$.request_id")
    _check_bounded_string(mapping["objective"], "$.objective", 4096, nonblank=True)
    _check_id(mapping["checkpoint_id"], "$.checkpoint_id")
    as_of = _check_timestamp(mapping["as_of"], "$.as_of")
    criteria = _validate_criteria(mapping["criteria"])
    evidence = _validate_evidence(mapping["evidence"])
    _validate_metadata(mapping.get("metadata", {}))
    issue = _first_structural_issue(criteria, evidence, as_of)
    if issue is not None:
        raise _Reject(issue)
    try:
        return VerificationRequest.model_validate(dict(mapping))
    except ValidationError:
        raise RequestValidationError(
            [Issue(InputErrorCode.INVALID_SCHEMA, "$", "request failed schema validation")]
        ) from None


def parse_request(data: Mapping[str, object] | str | bytes | bytearray) -> VerificationRequest:
    """Validate untrusted request input and build a :class:`VerificationRequest`.

    Accepts a mapping, JSON text, or UTF-8 bytes (bytearray included). Raises
    :class:`~nitelos.errors.RequestValidationError` whose first issue is the
    deterministic first error (see module docstring for the exact order);
    issues never contain offending values. Structural invariants and byte
    ceilings are enforced here; direct model construction enforces the same
    structural invariants via Pydantic ValidationError.
    """
    try:
        value = _ingest(data)
        if not isinstance(value, Mapping):
            _reject(InputErrorCode.INVALID_SCHEMA, "$", "request must be a JSON object")
        if not isinstance(value, dict):
            value = dict(value)
        return _build_request(value)
    except _Reject as reject:
        raise RequestValidationError([reject.issue]) from None


def _ingest(data: Mapping[str, object] | str | bytes | bytearray) -> object:
    if isinstance(data, (str, bytes, bytearray)):
        try:
            raw = data.encode("utf-8") if isinstance(data, str) else bytes(data)
        except UnicodeEncodeError:
            _reject(InputErrorCode.INVALID_SCHEMA, "$", "request text is not valid UTF-8")
        if len(raw) > MAX_REQUEST_JSON_BYTES:
            _reject(InputErrorCode.LIMIT_EXCEEDED, "$", "request exceeds the JSON size limit")
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            _reject(InputErrorCode.INVALID_SCHEMA, "$", "request bytes are not valid UTF-8")
        try:
            return parse_json(text, max_depth=MAX_JSON_DEPTH)
        except JsonError as error:
            code = (
                InputErrorCode.LIMIT_EXCEEDED
                if error.kind in (JsonErrorKind.TOO_DEEP, JsonErrorKind.TOO_LARGE)
                else InputErrorCode.INVALID_SCHEMA
            )
            raise _Reject(Issue(code, error.path, f"invalid JSON: {error.kind}")) from None
    if isinstance(data, Mapping):
        _check_json_shape(data, "$", 1)
        if _canonical_size(data) > MAX_REQUEST_JSON_BYTES:
            _reject(InputErrorCode.LIMIT_EXCEEDED, "$", "request exceeds the JSON size limit")
        return data
    _reject(InputErrorCode.INVALID_SCHEMA, "$", "request must be a mapping or JSON text")
