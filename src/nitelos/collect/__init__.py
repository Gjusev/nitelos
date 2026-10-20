"""Nitelos collector framework (plan section F1, NIT-017; ADR-014/015).

One contract every evidence source follows, so the verifier never cares where
evidence came from. A collector is read-only and bounded: it never mutates
state, retries agent actions or follows instructions found in evidence, and it
runs under the host's limits (timeout, raw-output cap, normalized-observation
cap, list caps with an explicit truncated count). Errors become structured
results — and, downstream, abstentions — never failures: a failed collection
is a :class:`CollectionResult` with no evidence and a ``COLLECTOR_*`` error
code with fixed safe text (exception text, and any message a collector tries
to attach, is never surfaced), and the verifier then abstains with the
existing MISSING_EVIDENCE reason.

Trust (ADR-015 finding 4): collected observations use channel ``external_api``
and criteria citing them use scope ``external``. A collector cannot grant
itself external authority: :class:`CollectionResult` carries no bindings, and
only the host — via :func:`host_trust_bindings`, for results returned by
:func:`run_collector` in this process (raw ``collect()`` output is unredacted
and unchecked) — can bind the evidence. Evidence a collector builds must set
``source_id`` to the collector id so host bindings match.

Timeouts: subprocess collectors get a hard, whole-process-tree kill through
the shared runner in ``nitelos.collect._process``; pure-Python collection is
bounded cooperatively — :func:`run_collector` measures elapsed time against
``limits.timeout_s`` after the collector returns, so a collector that blocks
forever cannot be stopped by the framework (same ruling as v0.1; no hard-stop
claim is made).

This package is stdlib-only and is never imported by ``nitelos`` itself.
"""

from __future__ import annotations

import json
import logging
import re
import time
from collections.abc import Mapping, Sequence
from enum import StrEnum
from typing import Annotated, Literal, Protocol, cast

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from nitelos.backends.deterministic import _array_index, _unescape
from nitelos.errors import EvidenceValidationError
from nitelos.policy import TrustBinding
from nitelos.schemas import (
    _ID_RE,
    IDType,
    JsonPointerType,
    ObservationEvidence,
    ScreenshotEvidence,
    Sha256Type,
    SubjectMap,
    UTCDateTime,
    canonical_json,
)
from nitelos.schemas import Channel as _Channel
from nitelos.schemas import (
    Evidence as _EvidenceFactory,
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
    "derive_evidence_id",
    "host_trust_bindings",
    "run_collector",
]

logger = logging.getLogger(__name__)  # no handlers; safe fields only

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
    """The structured error of a failed collection.

    ``safe_message`` is ALWAYS the fixed per-code text: any other value a
    caller or collector supplies is overwritten (review finding 5), so no
    collector-controlled text can reach a result, a report or stdout.
    """

    code: CollectorErrorCode

    @property
    def safe_message(self) -> str:
        return _MESSAGES[self.code]


class CollectorCapabilities(_Model):
    """What a collector may produce; run_collector rejects undeclared kinds."""

    evidence_kinds: tuple[Literal["observation", "screenshot"], ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _unique_kinds(self) -> CollectorCapabilities:
        if len(set(self.evidence_kinds)) != len(self.evidence_kinds):
            raise ValueError("evidence_kinds must be unique")
        return self


class CollectorLimits(_Model):
    """Bounded collection: defaults per plan F1; configurable downward.

    A kind's own list caps (for example F2's 200 dirty paths) are clipped by
    ``max_list_items`` — the framework limit always wins, a kind may only ask
    for fewer items.
    """

    timeout_s: float = Field(default=10.0, gt=0.0, le=3600.0)
    max_raw_bytes: int = Field(default=1_048_576, ge=1)
    max_observation_bytes: int = Field(default=65_536, ge=1)
    max_list_items: int = Field(default=100, ge=1)


class CollectorConfig(_Model):
    """Frozen base config supplied by the host for one collection.

    ``evidence_id`` is the base evidence id; multi-item collectors derive
    unique ids from it deterministically (:func:`derive_evidence_id`).
    ``redact_pointers`` are RFC 6901 pointers to drop before the evidence
    digest is computed. Kind-specific configs (NIT-018/019) subclass this base
    and are declared as the collector's ``config_model``; unknown fields and
    bad values make the collection fail with COLLECTOR_CONFIG_INVALID.
    """

    evidence_id: IDType
    sequence_start: int = Field(default=0, ge=0, le=1_000_000)
    checkpoint_id: IDType
    subject: SubjectMap
    limits: CollectorLimits = Field(default_factory=CollectorLimits)
    redact_pointers: tuple[JsonPointerType, ...] = ()


class ProvenanceRecord(_Model):
    """Where one evidence item came from; fields never carry secrets.

    ``sha256`` is the digest of the RAW capture (for subprocess collectors the
    exact stdout bytes — not canonical JSON). A raw-capture digest over a
    low-entropy secret can be brute-forced offline: keep secrets out of the
    capture, not just out of this record. ``evidence_sha256`` is set by
    :func:`run_collector` to the final, post-redaction evidence digest; a raw
    ``collect()`` result carries it as None.
    """

    evidence_id: IDType
    collector_id: IDType
    collector_version: str = Field(min_length=1, max_length=_MAX_VERSION)
    source: str = Field(min_length=1, max_length=_MAX_SOURCE)
    invocation: str = Field(min_length=1, max_length=_MAX_INVOCATION)
    captured_at: UTCDateTime
    subject: SubjectMap
    sha256: Sha256Type  # digest of the RAW capture (pre-redaction)
    evidence_sha256: Sha256Type | None = None  # filled in by run_collector
    raw_bytes: int = Field(ge=0)  # zero is legitimate: a clean tree's output
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
    must set ``source_id`` to the collector id, and observations use channel
    ``external_api``. ``config_model`` is the model mapping and JSON configs
    are validated through (the base class unless a kind subclasses it).

    The four descriptor members are read-only by intent (NIT-022 refinement:
    declared as properties so both @property implementations and plain class
    attributes satisfy the protocol, and config_model's type[...] variance is
    covariant — the first in-package call site passing a live collector
    exposed the settable-variable declaration as unimplementable).
    """

    @property
    def id(self) -> str: ...

    @property
    def version(self) -> str: ...

    @property
    def capabilities(self) -> CollectorCapabilities: ...

    @property
    def config_model(self) -> type[CollectorConfig]: ...

    def collect(self, config: CollectorConfig) -> CollectionResult: ...


def cap_list[T](items: Sequence[T], limit: int) -> tuple[tuple[T, ...], int]:
    """Cap a list, reporting how many items were dropped (never silently)."""
    if limit < 1:
        raise ValueError("limit must be at least 1")
    return tuple(items[:limit]), max(0, len(items) - limit)


def derive_evidence_id(base: str, index: int) -> str:
    """Derive a deterministic evidence id from a base id (index 0 keeps the base).

    Raises ValueError when the result would violate the v0.1 ID pattern or its
    128-character ceiling.
    """
    if index < 0:
        raise ValueError("index must be at least 0")
    derived = base if index == 0 else f"{base}-{index}"
    if len(derived) > 128 or _ID_RE.fullmatch(derived) is None:
        raise ValueError("the derived id violates the ID pattern or its length ceiling")
    return derived


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


def _resolve_pointer_path(root: object, pointer: str) -> tuple[object, ...] | None:
    """Resolve an RFC 6901 pointer to a concrete path (dict keys, list indices).

    Array tokens use the evaluator's canonical grammar (_array_index); invalid
    or non-addressing pointers resolve to None (never an error).
    """
    if pointer == "":
        return None  # the root cannot be dropped
    path: list[object] = []
    node = root
    for raw_token in pointer.split("/")[1:]:
        token = _unescape(raw_token)
        if isinstance(node, dict):
            if token not in node:
                return None
            path.append(token)
            node = node[token]
        elif isinstance(node, list):
            try:
                index = _array_index(token)
            except EvidenceValidationError:
                return None
            if index >= len(node):
                return None
            path.append(index)
            node = node[index]
        else:
            return None
    return tuple(path)


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


def _walk(document: object, path: tuple[object, ...]) -> tuple[bool, object]:
    node = document
    for token in path:
        if isinstance(node, dict) and token in node:  # noqa: SIM114 - narrowing needs the split
            node = node[token]
        elif isinstance(node, list) and isinstance(token, int) and token < len(node):
            node = node[token]
        else:
            return False, None
    return True, node


def _redact_document(data: object, pointers: Sequence[str]) -> tuple[object, list[str]]:
    """Resolve every pointer (user + secret-key) against the ORIGINAL document,
    then delete: dict keys in any order, array indices per parent in DESCENDING
    order, so user deletions can never shift a later target (review finding 1).
    """
    document = _plain_copy(data)
    resolved: list[tuple[object, ...]] = []
    applied: list[str] = []
    for pointer in (*pointers, *_secret_pointers(document)):
        path = _resolve_pointer_path(document, pointer)
        if path is not None:
            resolved.append(path)
            applied.append(_pointer_text(path))
    resolved.sort(key=lambda p: (-len(p), -(p[-1] if isinstance(p[-1], int) else 0)))
    for path in resolved:
        found, parent = _walk(document, path[:-1])
        if not found:
            continue  # the subtree was already removed by a deeper target
        last = path[-1]
        if isinstance(parent, dict) and last in parent:
            del cast(dict[str, object], parent)[cast(str, last)]
        elif isinstance(parent, list) and isinstance(last, int) and last < len(parent):
            del cast(list[object], parent)[last]
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


def _parse_config(collector: Collector, config: CollectorConfig | Mapping[str, object]) -> CollectorConfig:
    """Validate through the collector's own config_model, in JSON mode so
    JSON shapes (arrays for redact_pointers, subclass fields) work from files
    and mappings alike (review finding 4)."""
    model = getattr(collector, "config_model", CollectorConfig)
    if isinstance(config, model):
        return cast(CollectorConfig, config)
    if isinstance(config, Mapping):
        return cast(CollectorConfig, model.model_validate_json(json.dumps(dict(config))))
    raise CollectorError(CollectorErrorCode.CONFIG_INVALID)


def run_collector(collector: Collector, config: CollectorConfig | Mapping[str, object]) -> CollectionResult:
    """Run one collector under the framework contract and return its result.

    Maps every failure to a structured error (known :class:`CollectorError`
    codes as raised; invalid configs to COLLECTOR_CONFIG_INVALID; unexpected
    exceptions to COLLECTOR_EXCEPTION with fixed text — re-raised instead when
    ``NITELOS_DEV_RERAISE`` is enabled, mirroring the verifier; a
    collector-returned error result is rebuilt with the fixed text for its
    code, review finding 5). On success it cross-checks evidence and provenance
    against the collector and the config (source id, external_api channel,
    subject, checkpoint, collector id/version, captured_at, unique sequences at
    or after ``sequence_start`` — review findings 6 and 14), validates declared
    kinds, applies redaction BEFORE the evidence digest, fills the provenance
    ``evidence_sha256`` with the final digest, and enforces the
    normalized-observation cap (exceeding is an error, never truncation).
    KeyboardInterrupt and SystemExit always propagate. A pure-Python collector
    that never returns cannot be stopped here; see the module docstring.
    """
    try:
        parsed = _parse_config(collector, config)
    except (ValidationError, CollectorError, TypeError, ValueError):
        return _failure(collector, CollectorErrorCode.CONFIG_INVALID)
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
        finished = _finish(collector, parsed, raw)
    except CollectorError as error:
        return _failure(collector, error.code)
    except (KeyboardInterrupt, SystemExit):
        raise
    except Exception:
        if _parse_dev_reraise_env():
            raise
        return _failure(collector, CollectorErrorCode.EXCEPTION)
    logger.debug(
        "collector %s version %s finished: %d evidence item(s), error=%s",
        collector.id,
        collector.version,
        len(finished.evidence),
        finished.error.code.value if finished.error else None,
    )
    return finished


def _cross_check(
    collector: Collector,
    config: CollectorConfig,
    item: ObservationEvidence | ScreenshotEvidence,
    record: ProvenanceRecord,
) -> None:
    """Evidence/provenance must describe exactly this collector's run (finding 6)."""
    if item.source_id != collector.id:
        raise ValueError("collected evidence must carry the collector id as source_id")
    if item.checkpoint_id != config.checkpoint_id:
        raise ValueError("collected evidence must carry the config checkpoint id")
    if item.subject != config.subject:
        raise ValueError("collected evidence must carry the config subject")
    if item.kind == "observation" and item.channel != _Channel.EXTERNAL_API:
        raise ValueError("collected observations must use the external_api channel")
    if record.collector_id != collector.id:
        raise ValueError("provenance must name this collector")
    if record.collector_version != collector.version:
        raise ValueError("provenance must name this collector version")
    if record.subject != item.subject:
        raise ValueError("provenance subject must match its evidence item")
    if record.captured_at != item.captured_at:
        raise ValueError("provenance captured_at must match its evidence item")


def _finish(collector: Collector, config: CollectorConfig, raw: CollectionResult) -> CollectionResult:
    if raw.error is not None:
        # review finding 5: rebuild with the fixed text; collector text never passes
        return _failure(collector, raw.error.code)
    smuggled = set(raw.model_fields_set) - set(CollectionResult.model_fields)
    if smuggled:
        # model_construct smuggled fields (self-granted trust &c.) are rejected
        raise ValueError("a collector result carries unexpected extra fields")
    declared = collector.capabilities.evidence_kinds
    records = {record.evidence_id: record for record in raw.provenance}
    sequences = [item.sequence for item in raw.evidence]
    if len(set(sequences)) != len(sequences) or any(
        sequence < config.sequence_start for sequence in sequences
    ):
        raise ValueError("evidence sequences must be unique and at or after sequence_start")
    evidence_out: list[ObservationEvidence | ScreenshotEvidence] = []
    provenance_out: list[ProvenanceRecord] = []
    for item in raw.evidence:
        record = records[item.id]
        _cross_check(collector, config, item, record)
        if item.kind not in declared:
            raise ValueError(f"collector produced an undeclared evidence kind: {item.kind}")
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
                        "evidence_sha256": rebuilt.sha256,
                    }
                )
            )
        else:
            evidence_out.append(item)
            provenance_out.append(record.model_copy(update={"evidence_sha256": item.sha256}))
    return CollectionResult(
        collector_id=collector.id,
        collector_version=collector.version,
        evidence=tuple(evidence_out),
        provenance=tuple(provenance_out),
    )


def host_trust_bindings(result: CollectionResult) -> tuple[TrustBinding, ...]:
    """Bind collected evidence to the host's authority (ADR-015 finding 4).

    Authority: use ONLY for results returned by ``run_collector`` in this
    process — the host vouches that it invoked the collector and that the
    digests are that run's output (redacted and cross-checked). NEVER call it
    for raw ``collect()`` output (unredacted, unchecked) or for evidence
    received from an agent or any other process; such evidence stays unbound
    and can never satisfy external-scope criteria.
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
