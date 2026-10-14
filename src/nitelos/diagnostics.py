"""Diagnostics assembly for verification results (NIT-006).

Authority: docs/planning/03-domain-model-and-api.md (exact Diagnostics shape),
02-system-architecture.md ("Diagnostics and observability"). Fingerprints are
SHA-256 over Nitelos canonical JSON v1: the request hash covers the full
serialized request, the evidence manifest hash covers the ordered
[{evidence_id, sha256}] list. Both are null when no valid request exists.
Timing values are the caller's real measurements; nothing here guesses.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping

from nitelos import __version__
from nitelos.errors import LimitationCode
from nitelos.policy import VerificationPolicy, policy_hash
from nitelos.schemas import BackendDescriptor, Diagnostics, Measurements, VerificationRequest, canonical_json

__all__ = ["build_diagnostics", "evidence_manifest_hash", "request_fingerprint"]

_UNAVAILABLE_REASONS = {
    "input_tokens": "not_counted",
    "output_tokens": "not_counted",
    "peak_rss_bytes": "not_measured",
    "peak_device_bytes": "not_measured",
}


def request_fingerprint(request: VerificationRequest) -> str:
    """SHA-256 over canonical JSON v1 of the serialized request."""
    return hashlib.sha256(canonical_json(request.model_dump(mode="json")).encode("utf-8")).hexdigest()


def evidence_manifest_hash(request: VerificationRequest) -> str:
    """SHA-256 over canonical JSON v1 of the ordered evidence manifest."""
    manifest = [{"evidence_id": item.id, "sha256": item.sha256} for item in request.evidence]
    return hashlib.sha256(canonical_json(manifest).encode("utf-8")).hexdigest()


def build_diagnostics(
    *,
    policy: VerificationPolicy,
    backend_descriptor: BackendDescriptor,
    elapsed_ms: float,
    criterion_durations: Mapping[str, float],
    request: VerificationRequest | None = None,
    partial_results: bool = False,
) -> Diagnostics:
    """Assemble the exact doc-03 diagnostics record.

    ``request`` may be None on failures where no valid request exists; the
    fingerprints are then null. ``partial_results`` marks a backend-error
    result whose completed criteria are explicitly non-authoritative.
    """
    limitations: tuple[str, ...] = (
        (LimitationCode.PARTIAL_RESULTS_NONAUTHORITATIVE,) if partial_results else ()
    )
    return Diagnostics(
        package_version=__version__,
        schema_version="1",
        request_hash=request_fingerprint(request) if request is not None else None,
        evidence_manifest_hash=evidence_manifest_hash(request) if request is not None else None,
        policy_id=policy.id,
        policy_version=policy.version,
        policy_hash=policy_hash(policy),
        backend=backend_descriptor,
        elapsed_ms=elapsed_ms,
        model_load_ms=None,
        criterion_durations_ms=dict(criterion_durations),
        omitted_context_ids=(),
        preprocessing=(),
        measurements=Measurements(unavailable_reasons=_UNAVAILABLE_REASONS),
        limitations=limitations,
    )
