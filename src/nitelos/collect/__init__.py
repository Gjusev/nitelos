"""Nitelos collector framework (plan section F1, NIT-017; ADR-014/015).

One contract every evidence source follows, so the verifier never cares where
evidence came from. A collector is read-only and bounded: it never mutates
state, retries agent actions or follows instructions found in evidence, and it
runs under the host's limits (timeout, raw-output cap, normalized-observation
cap, list caps with an explicit truncated count). Errors become structured
results — and, downstream, abstentions — never failures: a failed collection
is a :class:`CollectionResult` with no evidence and a ``COLLECTOR_*`` error
code with fixed safe text (exception text is never surfaced), and the verifier
then abstains with the existing MISSING_EVIDENCE reason.

Trust (ADR-015 finding 4): collected observations use channel ``external_api``
and criteria citing them use scope ``external``. A collector cannot grant
itself external authority: :class:`CollectionResult` carries no bindings, and
only the host — via :func:`host_trust_bindings`, for results its own process
just collected — can bind the evidence. Evidence a collector builds must set
``source_id`` to the collector id so host bindings match.

Timeouts: subprocess collectors get a hard kill through the shared runner in
``nitelos.collect._process``; pure-Python collection is bounded cooperatively —
:func:`run_collector` measures elapsed time against ``limits.timeout_s`` after
the collector returns, so a collector that blocks forever cannot be stopped by
the framework (same ruling as v0.1; no hard-stop claim is made).

This package is stdlib-only and is never imported by ``nitelos`` itself.
"""

from __future__ import annotations

import re
import time
from collections.abc import Mapping, Sequence
from enum import StrEnum
from typing import Annotated, Literal, Protocol, cast

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from nitelos.backends.deterministic import _resolve_pointer, _unescape
from nitelos.errors import EvidenceValidationError
from nitelos.policy import TrustBinding
from nitelos.schemas import (
    Evidence as _EvidenceFactory,
)
from nitelos.schemas import (
    IDType,
    JsonPointerType,
    ObservationEvidence,
    ScreenshotEvidence,
    Sha256Type,
    SubjectMap,
    UTCDateTime,
    canonical_json,
)
from nitelos.verifier import _parse_dev_reraise_env

__all__ = [
    "CollectionResult",
    "Collector",
    "CollectorCapabilities",
    "CollectorConfig",
    "CollectorError",
    "CollectorErrorCode",
    "CollectorErrorInfo",
    "CollectorLimits",
    "ProvenanceRecord",
    "cap_list",
    "host_trust_bindings",
    "run_collector",
]

_MAX_VERSION = 32
_MAX_SOURCE = 256
_MAX_INVOCATION = 512


class _Model(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)


class CollectorErrorCode(StrEnum):
    """Collector-layer failure codes (ADR-015 finding 2); not wire codes.

    A failed collection makes the verifier abstain (MISSING_EVIDENCE); these
    codes never appear in a VerificationResult.
    """

    TIMEOUT = "COLLECTOR_TIMEOUT"
    UNAVAILABLE = "COLLECTOR_UNAVAILABLE"
    OUTPUT_TOO_LARGE = "COLLECTOR_OUTPUT_TOO_LARGE"
    CONFIG_INVALID = "COLLECTOR_CONFIG_INVALID"
    AUTH_MISSING = "COLLECTOR_AUTH_MISSING"
    EXCEPTION = "COLLECTOR_EXCEPTION"  # framework-reserved: unexpected collector crashes


_MESSAGES: dict[CollectorErrorCode, str] = {
    CollectorErrorCode.TIMEOUT: "the collector did not finish within its timeout",
    CollectorErrorCode.UNAVAILABLE: "the collector's executable or module is unavailable",
    CollectorErrorCode.OUTPUT_TOO_LARGE: "the collector output exceeded its configured cap",
    CollectorErrorCode.CONFIG_INVALID: "the collector configuration is invalid",
    CollectorErrorCode.AUTH_MISSING: "the collector is missing credentials for its source",
    CollectorErrorCode.EXCEPTION: "the collector failed unexpectedly",
}


class CollectorError(Exception):
    """A collector-side failure carrying a safe code; text is never surfaced."""

    def __init__(self, code: CollectorErrorCode) -> None:
        self.code = code
        super().__init__(code.value)


class CollectorErrorInfo(_Model):
    """The structured error of a failed collection (fixed text per code)."""

    code: CollectorErrorCode
    safe_message: str = Field(default="", max_length=200)

    @model_validator(mode="after")
    def _fixed_message(self) -> CollectorErrorInfo:
        """Default to the fixed text for the code; callers never pass their own."""
        if self.safe_message == "":
            object.__setattr__(self, "safe_message", _MESSAGES[self.code])
        return self


class CollectorCapabilities(_Model):
    """What a collector may produce; run_collector rejects undeclared kinds."""

    evidence_kinds: tuple[Literal["observation", "screenshot"], ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _unique_kinds(self) -> CollectorCapabilities:
        if len(set(self.evidence_kinds)) != len(self.evidence_kinds):
            raise ValueError("evidence_kinds must be unique")
        return self


class CollectorLimits(_Model):
    """Bounded collection: defaults per plan F1; configurable downward."""

    timeout_s: float = Field(default=10.0, gt=0.0, le=3600.0)
    max_raw_bytes: int = Field(default=1_048_576, ge=1)
    max_observation_bytes: int = Field(default=65_536, ge=1)
    max_list_items: int = Field(default=100, ge=1)


class CollectorConfig(_Model):
    """Frozen base config supplied by the host for one collection.

    ``evidence_id`` is the base evidence id; multi-item collectors derive
    unique ids from it deterministically. ``redact_pointers`` are RFC 6901
    pointers to drop before the evidence digest is computed. Kind-specific
    configs (NIT-018/019) subclass this base; unknown fields and bad values
    make the collection fail with COLLECTOR_CONFIG_INVALID.
    """

    evidence_id: IDType
    sequence_start: int = Field(default=0, ge=0, le=1_000_000)
    checkpoint_id: IDType
    subject: SubjectMap
    limits: CollectorLimits = Field(default_factory=CollectorLimits)
    redact_pointers: tuple[JsonPointerType, ...] = ()


class ProvenanceRecord(_Model):
    """Where one evidence item came from; fields never carry secrets."""

    evidence_id: IDType
    collector_id: IDType
    collector_version: str = Field(min_length=1, max_length=_MAX_VERSION)
    source: str = Field(min_length=1, max_length=_MAX_SOURCE)
    invocation: str = Field(min_length=1, max_length=_MAX_INVOCATION)
    captured_at: UTCDateTime
    subject: SubjectMap
    sha256: Sha256Type  # digest of the RAW capture (pre-redaction)
    raw_bytes: int = Field(ge=1)
    normalized_bytes: int = Field(ge=0)
    redactions: tuple[str, ...] = ()

    def __repr__(self) -> str:
        return (
            f"{type(self).__name__}(evidence_id={self.evidence_id!r}, "
            f"collector_id={self.collector_id!r}, raw_bytes={self.raw_bytes}, "
            f"redactions={len(self.redactions)})"
        )


_CollectedEvidence = Annotated[ObservationEvidence | ScreenshotEvidence, Field(discriminator="kind")]


class CollectionResult(_Model):
    """One collection's outcome: evidence plus one provenance record per item,
    or a structured error and nothing else. Never both."""

    collector_id: IDType
    collector_version: str = Field(min_length=1, max_length=_MAX_VERSION)
    evidence: tuple[_CollectedEvidence, ...] = ()
    provenance: tuple[ProvenanceRecord, ...] = ()
    error: CollectorErrorInfo | None = None

    @model_validator(mode="after")
    def _exactly_one_provenance_per_item(self) -> CollectionResult:
        if self.error is not None and (self.evidence or self.provenance):
            raise ValueError("a failed collection carries no evidence or provenance")
        ids = [item.id for item in self.evidence]
        provenance_ids = [record.evidence_id for record in self.provenance]
        if len(set(ids)) != len(ids) or sorted(ids) != sorted(provenance_ids):
            raise ValueError("exactly one provenance record per evidence item is required")
        return self

    def __repr__(self) -> str:
        return (
            f"{type(self).__name__}(collector_id={self.collector_id!r}, "
            f"evidence={len(self.evidence)}, error={self.error.code.value if self.error else None})"
        )


class Collector(Protocol):
    """The contract every evidence source follows (plan F1).

    Implementations are read-only and bounded; ``collect`` either returns a
    complete :class:`CollectionResult` or raises :class:`CollectorError` for a
    known failure (anything else becomes COLLECTOR_EXCEPTION). Evidence items
    must set ``source_id`` to the collector id.
    """

    id: str
    version: str
    capabilities: CollectorCapabilities

    def collect(self, config: CollectorConfig) -> CollectionResult: ...


def cap_list[T](items: Sequence[T], limit: int) -> tuple[tuple[T, ...], int]:
    """Cap a list, reporting how many items were dropped (never silently)."""
    if limit < 1:
        raise ValueError("limit must be at least 1")
    return tuple(items[:limit]), max(0, len(items) - limit)


# ---------------------------------------------------------------------------
# redaction (RFC 6901 pointers reuse the deterministic evaluator's grammar, AR-1)
# ---------------------------------------------------------------------------

_SECRET_KEY_RE = re.compile(r"token|secret|password|authorization", re.IGNORECASE)


def _plain_copy(value: object) -> object:
    if isinstance(value, Mapping):
        return {key: _plain_copy(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain_copy(item) for item in value]
    return value


def _pointer_text(path: tuple[object, ...]) -> str:
    tokens = (str(token).replace("~", "~0").replace("/", "~1") for token in path)
    return "".join(f"/{token}" for token in tokens)


def _secret_pointers(node: object, path: tuple[object, ...] = ()) -> list[str]:
    found: list[str] = []
    if isinstance(node, Mapping):
        for key, item in node.items():
            if _SECRET_KEY_RE.search(str(key)):
                found.append(_pointer_text((*path, key)))
            else:
                found.extend(_secret_pointers(item, (*path, key)))
    elif isinstance(node, list):
        for index, item in enumerate(node):
            found.extend(_secret_pointers(item, (*path, index)))
    return found


def _drop_pointer(document: object, pointer: str) -> bool:
    if pointer == "":
        return False  # the root cannot be dropped
    parent_pointer, _, last = pointer.rpartition("/")
    try:
        found, node = _resolve_pointer(document, parent_pointer) if parent_pointer else (True, document)
    except EvidenceValidationError:
        return False  # pointer addresses an invalid array token
    if not found:
        return False
    token = _unescape(last)
    if isinstance(node, dict) and token in node:
        del node[token]
        return True
    if isinstance(node, list) and token.isdigit() and int(token) < len(node):
        del node[int(token)]
        return True
    return False


def _redact_document(data: object, pointers: Sequence[str]) -> tuple[object, list[str]]:
    document = _plain_copy(data)
    applied: list[str] = []
    for pointer in (*pointers, *_secret_pointers(document)):
        if _drop_pointer(document, pointer):
            applied.append(pointer)
    return document, applied


# ---------------------------------------------------------------------------
# the framework entry point
# ---------------------------------------------------------------------------


def _failure(collector: Collector, code: CollectorErrorCode) -> CollectionResult:
    return CollectionResult(
        collector_id=collector.id,
        collector_version=collector.version,
        evidence=(),
        provenance=(),
        error=CollectorErrorInfo(code=code),
    )


def run_collector(collector: Collector, config: CollectorConfig | Mapping[str, object]) -> CollectionResult:
    """Run one collector under the framework contract and return its result.

    Maps every failure to a structured error (known :class:`CollectorError`
    codes as raised; invalid config to COLLECTOR_CONFIG_INVALID; unexpected
    exceptions to COLLECTOR_EXCEPTION with fixed text — re-raised instead when
    ``NITELOS_DEV_RERAISE`` is enabled, mirroring the verifier). On success it
    validates provenance completeness (one record per item; the record digest
    must equal the collector's evidence digest; kinds must be declared),
    applies redaction BEFORE the evidence digest, and enforces the
    normalized-observation cap (exceeding is an error, never truncation).
    KeyboardInterrupt and SystemExit always propagate. A pure-Python collector
    that never returns cannot be stopped here; see the module docstring.
    """
    try:
        if isinstance(config, CollectorConfig):
            parsed = config
        elif isinstance(config, Mapping):
            parsed = CollectorConfig.model_validate(dict(config))
        else:
            raise CollectorError(CollectorErrorCode.CONFIG_INVALID)
    except ValidationError:
        return _failure(collector, CollectorErrorCode.CONFIG_INVALID)
    except CollectorError as error:
        return _failure(collector, error.code)
    started = time.monotonic()
    try:
        raw = collector.collect(parsed)
    except CollectorError as error:
        return _failure(collector, error.code)
    except (KeyboardInterrupt, SystemExit):
        raise
    except Exception:
        if _parse_dev_reraise_env():
            raise
        return _failure(collector, CollectorErrorCode.EXCEPTION)
    try:
        if time.monotonic() - started > parsed.limits.timeout_s:
            return _failure(collector, CollectorErrorCode.TIMEOUT)
        return _finish(collector, parsed, raw)
    except CollectorError as error:
        return _failure(collector, error.code)
    except (KeyboardInterrupt, SystemExit):
        raise
    except Exception:
        if _parse_dev_reraise_env():
            raise
        return _failure(collector, CollectorErrorCode.EXCEPTION)


def _finish(collector: Collector, config: CollectorConfig, raw: CollectionResult) -> CollectionResult:
    if raw.error is not None:
        return raw
    declared = collector.capabilities.evidence_kinds
    records = {record.evidence_id: record for record in raw.provenance}
    evidence_out: list[ObservationEvidence | ScreenshotEvidence] = []
    provenance_out: list[ProvenanceRecord] = []
    for item in raw.evidence:
        record = records[item.id]
        if item.kind not in declared:
            raise ValueError(f"collector produced an undeclared evidence kind: {item.kind}")
        if item.kind == "observation" and record.sha256 != item.sha256:
            raise ValueError("provenance sha256 must match the collector's evidence digest")
        if item.kind == "observation":
            redacted, applied = _redact_document(item.data, config.redact_pointers)
            size = len(canonical_json(redacted).encode("utf-8"))
            if size > config.limits.max_observation_bytes:
                raise CollectorError(CollectorErrorCode.OUTPUT_TOO_LARGE)
            rebuilt = _EvidenceFactory.observation(
                id=item.id,
                sequence=item.sequence,
                captured_at=item.captured_at,
                checkpoint_id=item.checkpoint_id,
                source_id=item.source_id,
                subject=item.subject,
                phase=item.phase,
                channel=item.channel,
                data=cast(Mapping[str, object], redacted),
            )
            evidence_out.append(rebuilt)
            provenance_out.append(
                record.model_copy(
                    update={
                        "redactions": tuple(sorted({*record.redactions, *applied})),
                        "normalized_bytes": size,
                    }
                )
            )
        else:
            evidence_out.append(item)
            provenance_out.append(record)
    return CollectionResult(
        collector_id=collector.id,
        collector_version=collector.version,
        evidence=tuple(evidence_out),
        provenance=tuple(provenance_out),
    )


def host_trust_bindings(result: CollectionResult) -> tuple[TrustBinding, ...]:
    """Bind collected evidence to the host's authority (ADR-015 finding 4).

    Authority: use ONLY for results your own process just collected — the host
    vouches that it invoked the collector and that the digests are its output.
    NEVER call this for evidence received from an agent or any other process;
    such evidence stays unbound and can never satisfy external-scope criteria.
    """
    return tuple(
        TrustBinding(
            evidence_id=item.id,
            sha256=item.sha256,
            source_id=result.collector_id,
            subject=item.subject,
            checkpoint_id=item.checkpoint_id,
        )
        for item in result.evidence
    )
