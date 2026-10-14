"""Backend protocol, capabilities and output validation (NIT-007).

Authority: docs/planning/04-verification-backends.md ("Protocol and capability
negotiation", prepared interface details), 03 (finding/reference/score rules),
07 (backend output is untrusted; a custom backend is trusted executable code).
Custom backends are injected as instances — no registry, import strings or
entry-point discovery.

Everything a backend receives is immutable and minimal: a
``PreparedVisualCriterion`` (criterion id, description, decoded images in
declared reference order — no file paths) and an ``InferenceContext``
(objective, bounded action context, cooperative deadline — no metadata
dictionary, trust bindings, labels or credentials). Backend output is
untrusted: :func:`validate_backend_finding` enforces the doc-03 rules before
anything reaches a result, and violations raise :class:`BackendOutputError`
with a stable backend code and a value-free message. The helper is public so
custom backend authors can run the same conformance check the engine does.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from nitelos.errors import BackendErrorCode, EvidenceValidationError
from nitelos.evidence import PreparedImage, validate_evidence_ref
from nitelos.schemas import (
    BackendFinding,
    CriterionState,
    Grounding,
    ScoreKind,
    ScreenshotEvidence,
)

__all__ = [
    "Backend",
    "BackendCapabilities",
    "BackendOutputError",
    "InferenceContext",
    "PreparedVisualCriterion",
    "validate_backend_finding",
]


class BackendOutputError(Exception):
    """Invalid backend output; carries a stable backend code and a safe message.

    Raised by :func:`validate_backend_finding` (and by the verifier around
    ``infer``). The message never contains backend output or exception text.
    """

    def __init__(self, code: BackendErrorCode, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.safe_message = message


@dataclass(frozen=True)
class BackendCapabilities:
    """Truthful limits of one backend (doc 04); maxima are ints, never null.

    Non-image backends declare ``max_images_per_criterion = 0``;
    unlimited/null maxima are not representable by design.
    """

    evidence_kinds: tuple[str, ...] = ()
    criterion_kinds: tuple[str, ...] = ()
    supports_text: bool = False
    supports_images: bool = False
    supports_structured_decisions: bool = False
    supports_probabilities: bool = False
    supports_calibrated_probabilities: bool = False
    supports_native_abstention: bool = False
    supports_evidence_references: bool = False
    local_execution: bool = False
    supports_native_batch: bool = False
    max_images_per_criterion: int = 0
    max_text_tokens: int = 0


@dataclass(frozen=True)
class PreparedVisualCriterion:
    """What a visual backend infers on: id, description, decoded images."""

    criterion_id: str
    description: str
    images: tuple[PreparedImage, ...]


@dataclass(frozen=True)
class InferenceContext:
    """Model context: objective, bounded actions, cooperative deadline.

    ``actions`` holds NIT-009's ActionContextItem records (last-eight action
    name/status view); until that lands the verifier passes an empty tuple.
    ``deadline`` is an absolute monotonic timestamp or None when no deadline
    is configured; backends check it cooperatively between steps. There is no
    metadata dictionary, and trust bindings or labels never appear here.
    """

    objective: str
    actions: tuple[Any, ...] = ()
    deadline: float | None = None


@runtime_checkable
class Backend(Protocol):
    """The visual backend protocol; registration is instance injection."""

    @property
    def descriptor(self) -> Any: ...

    @property
    def capabilities(self) -> BackendCapabilities: ...

    def infer(self, prepared: PreparedVisualCriterion, context: InferenceContext) -> BackendFinding:
        """Return one finding for the prepared criterion (synchronous)."""

    def close(self) -> None:
        """Release resources; idempotent."""


def validate_backend_finding(
    finding: Any,
    *,
    criterion_id: str,
    images: Mapping[str, PreparedImage],
    already_emitted: frozenset[str] = frozenset(),
) -> BackendFinding:
    """Validate one backend finding against doc 03; returns it when valid.

    ``images`` are the prepared images actually supplied to that inference,
    keyed by evidence id — box bounds are checked against their real decoded
    dimensions. Raises :class:`BackendOutputError` with INVALID_OUTPUT for a
    missing/malformed finding, a foreign or duplicate criterion id or an
    illegal state; INVALID_EVIDENCE_REFERENCE for invented references,
    references outside the supplied images, decisive findings without at
    least one supplied-image reference, pointers on screenshots,
    out-of-bounds boxes and self-asserted ``assertion_checked`` grounding;
    and UNSUPPORTED_CALIBRATION for a ``calibrated_probability`` score (a
    capability flag alone cannot authorize it in v0.1).
    """
    if not isinstance(finding, BackendFinding):
        raise BackendOutputError(BackendErrorCode.INVALID_OUTPUT, "backend returned no valid finding")
    if finding.criterion_id != criterion_id or criterion_id in already_emitted:
        raise BackendOutputError(BackendErrorCode.INVALID_OUTPUT, "finding cites a foreign criterion id")
    if not isinstance(finding.state, CriterionState):
        raise BackendOutputError(BackendErrorCode.INVALID_OUTPUT, "finding state is not a legal state")
    if finding.score is not None and finding.score.kind == ScoreKind.CALIBRATED_PROBABILITY:
        raise BackendOutputError(
            BackendErrorCode.UNSUPPORTED_CALIBRATION, "calibrated probabilities are not supported in v0.1"
        )
    decisive = finding.state in (CriterionState.SUPPORTED, CriterionState.REFUTED)
    if decisive and not finding.evidence_refs:
        raise BackendOutputError(
            BackendErrorCode.INVALID_EVIDENCE_REFERENCE,
            "a decisive finding must reference at least one supplied image",
        )
    for reference in finding.evidence_refs:
        if reference.evidence_id not in images:
            raise BackendOutputError(
                BackendErrorCode.INVALID_EVIDENCE_REFERENCE, "finding references unprepared evidence"
            )
        if reference.grounding == Grounding.ASSERTION_CHECKED:
            raise BackendOutputError(
                BackendErrorCode.INVALID_EVIDENCE_REFERENCE,
                "backends cannot self-assert assertion_checked grounding",
            )
        try:
            validate_evidence_ref(
                reference,
                {evidence_id: _as_screenshot(evidence_id) for evidence_id in images},
                images,
            )
        except EvidenceValidationError:
            raise BackendOutputError(
                BackendErrorCode.INVALID_EVIDENCE_REFERENCE,
                "finding reference violates pointer/box kind or bounds rules",
            ) from None
    return finding


def _as_screenshot(evidence_id: str) -> ScreenshotEvidence:
    """Minimal valid screenshot model for the shared EvidenceRef kind rules."""
    return ScreenshotEvidence.model_validate(
        {
            "id": evidence_id,
            "kind": "screenshot",
            "sequence": 0,
            "captured_at": "2024-06-01T10:00:00Z",
            "checkpoint_id": "cp",
            "source_id": "backend-validation",
            "subject": {"form": "validation"},
            "phase": "final",
            "sha256": "0" * 64,
            "artifact_id": f"art-{evidence_id}",
            "media_type": "image/png",
            "width": 4,
            "height": 4,
        }
    )
