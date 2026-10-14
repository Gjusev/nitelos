"""Stable error taxonomy and safe validation errors for Nitelos.

Authority: docs/planning/03-domain-model-and-api.md ("Errors and abstention
reasons") and 07-security-and-privacy.md. Error messages never contain
offending input values: issues carry a stable code, a JSON-style field path
and a fixed safe message. Codes are part of the v1 contract.

Limitations: abstention reasons and decision codes are modeled here so the
taxonomy stays in one module, but only input/backend codes may appear in
:class:`ErrorInfo`; retryable is reserved for TIMEOUT/BUSY in v0.1.
"""

from __future__ import annotations

from collections.abc import Sequence
from enum import StrEnum


class InputErrorCode(StrEnum):
    """Input validation failures: no backend inference runs, retryable is always false."""

    INVALID_SCHEMA = "INVALID_SCHEMA"
    UNSUPPORTED_SCHEMA = "UNSUPPORTED_SCHEMA"
    LIMIT_EXCEEDED = "LIMIT_EXCEEDED"
    UNKNOWN_REFERENCE = "UNKNOWN_REFERENCE"
    DUPLICATE_ID = "DUPLICATE_ID"
    INVALID_SEQUENCE = "INVALID_SEQUENCE"
    INVALID_TIMESTAMP = "INVALID_TIMESTAMP"
    INVALID_POINTER = "INVALID_POINTER"
    INVALID_IMAGE = "INVALID_IMAGE"
    HASH_MISMATCH = "HASH_MISMATCH"
    MISSING_ARTIFACT = "MISSING_ARTIFACT"
    UNSUPPORTED_CAPABILITY = "UNSUPPORTED_CAPABILITY"
    INVALID_POLICY = "INVALID_POLICY"
    PATH_NOT_ALLOWED = "PATH_NOT_ALLOWED"


class BackendErrorCode(StrEnum):
    """Backend execution failures: decision is null, no fabricated findings."""

    DEPENDENCY_MISSING = "DEPENDENCY_MISSING"
    MODEL_UNAVAILABLE = "MODEL_UNAVAILABLE"
    MODEL_LOAD_FAILED = "MODEL_LOAD_FAILED"
    INVALID_OUTPUT = "INVALID_OUTPUT"
    INVALID_EVIDENCE_REFERENCE = "INVALID_EVIDENCE_REFERENCE"
    UNSUPPORTED_CALIBRATION = "UNSUPPORTED_CALIBRATION"
    RESOURCE_EXHAUSTED = "RESOURCE_EXHAUSTED"
    TIMEOUT = "TIMEOUT"
    BACKEND_EXCEPTION = "BACKEND_EXCEPTION"
    BUSY = "BUSY"
    CLOSED = "CLOSED"


class AbstentionReason(StrEnum):
    """Reasons an executed criterion remains unknown; execution stays ok."""

    MISSING_EVIDENCE = "MISSING_EVIDENCE"
    MISSING_VALUE = "MISSING_VALUE"
    STALE_EVIDENCE = "STALE_EVIDENCE"
    SUBJECT_MISMATCH = "SUBJECT_MISMATCH"
    CHECKPOINT_MISMATCH = "CHECKPOINT_MISMATCH"
    UNTRUSTED_EXTERNAL = "UNTRUSTED_EXTERNAL"
    PENDING_STATE = "PENDING_STATE"
    CONTRADICTORY_EVIDENCE = "CONTRADICTORY_EVIDENCE"
    MODEL_UNCERTAIN = "MODEL_UNCERTAIN"
    MODEL_INFERENCE_DISALLOWED = "MODEL_INFERENCE_DISALLOWED"


class DecisionCode(StrEnum):
    """Result-level aggregate codes accompanying a decision."""

    ALL_CRITERIA_SUPPORTED = "ALL_CRITERIA_SUPPORTED"
    CRITERION_REFUTED = "CRITERION_REFUTED"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


class LimitationCode(StrEnum):
    """Reported residual limitations of a criterion evaluation."""

    VISUAL_GROUNDING_UNVERIFIED = "VISUAL_GROUNDING_UNVERIFIED"


class Issue:
    """One safe validation finding: stable code, JSON-style path, fixed message."""

    __slots__ = ("code", "field_path", "safe_message")

    def __init__(self, code: InputErrorCode, field_path: str, safe_message: str) -> None:
        self.code = code
        self.field_path = field_path
        self.safe_message = safe_message

    def __repr__(self) -> str:
        return f"Issue(code={self.code!s}, field_path={self.field_path!r})"

    def __str__(self) -> str:
        return f"{self.code!s} at {self.field_path}: {self.safe_message}"


class RequestValidationError(ValueError):
    """Raised by :func:`nitelos.parse_request` for invalid request input.

    Carries an ordered tuple of :class:`Issue` values; the first issue is the
    deterministic first error (document-03 request field order, then criterion
    order, then evidence order). Never exposes offending input values.
    """

    def __init__(self, issues: Sequence[Issue]) -> None:
        self.issues: tuple[Issue, ...] = tuple(issues)
        summary = "; ".join(str(issue) for issue in self.issues) or "invalid request"
        super().__init__(f"invalid request: {summary}")

    def __repr__(self) -> str:
        return f"RequestValidationError(issues={self.issues!r})"


class ConfigurationError(Exception):
    """Raised when a Verifier is constructed with invalid trusted configuration."""
