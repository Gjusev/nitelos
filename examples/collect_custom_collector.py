"""EX: write a custom collector and verify its evidence (NIT-017, offline).

A minimal collector wraps one static JSON payload (no subprocess, no network):
``collect`` builds the observation, its provenance record, and returns a
``CollectionResult``. ``run_collector`` then applies the framework contract —
redaction before the digest, provenance validation, caps. The example verifies
the collected evidence with an external-scope assertion twice: with the host's
trust bindings the decision is a success; without them the same evidence can
only abstain (UNTRUSTED_EXTERNAL), because a collector can never grant trust
to its own output (ADR-015 finding 4).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from nitelos import Evidence, Verifier, canonical_json, parse_request
from nitelos.collect import (
    CollectionResult,
    CollectorCapabilities,
    CollectorConfig,
    ProvenanceRecord,
    host_trust_bindings,
    run_collector,
)


class DeploymentStatusCollector:
    """Read-only collector over an in-memory deployment record."""

    config_model = CollectorConfig  # kind-specific configs subclass CollectorConfig

    def __init__(self, record: dict[str, Any]) -> None:
        self.record = record

    @property
    def id(self) -> str:
        return "deployment-status"

    @property
    def version(self) -> str:
        return "1.0.0"

    @property
    def capabilities(self) -> CollectorCapabilities:
        return CollectorCapabilities(evidence_kinds=("observation",))

    def collect(self, config: CollectorConfig) -> CollectionResult:
        item = Evidence.observation(
            id=config.evidence_id,
            sequence=config.sequence_start,
            captured_at=datetime.now(UTC),
            checkpoint_id=config.checkpoint_id,
            source_id=self.id,
            subject=config.subject,
            phase="final",
            channel="external_api",
            data=self.record,
        )
        size = len(canonical_json(self.record).encode("utf-8"))
        return CollectionResult(
            collector_id=self.id,
            collector_version=self.version,
            evidence=(item,),
            provenance=(
                ProvenanceRecord(
                    evidence_id=item.id,
                    collector_id=self.id,
                    collector_version=self.version,
                    source="in-memory deployment record",
                    invocation="memory",
                    captured_at=item.captured_at,
                    subject=config.subject,
                    sha256=item.sha256,
                    raw_bytes=size,
                    normalized_bytes=size,
                ),
            ),
        )


def _request_document(result: CollectionResult) -> dict[str, Any]:
    (item,) = result.evidence
    return {
        "schema_version": "1",
        "request_id": "req-deploy-demo",
        "objective": "The deployment reports status=live",
        "checkpoint_id": "cp-deploy",
        "as_of": item.model_dump(mode="json")["captured_at"],
        "criteria": [
            {
                "id": "c-live",
                "description": "The deployment record reports status=live",
                "kind": "assertion",
                "scope": "external",
                "evidence_ids": [item.id],
                "subject": {"repo": "example/app"},
                "pointer": "/status",
                "operator": "equals",
                "expected": "live",
            }
        ],
        "evidence": [item.model_dump(mode="json") for item in result.evidence],
        "metadata": {},
    }


def run() -> tuple[Any, Any]:
    collector = DeploymentStatusCollector({"status": "live", "region": "eu-1"})
    config = CollectorConfig(
        evidence_id="obs-deploy-1",
        sequence_start=0,
        checkpoint_id="cp-deploy",
        subject={"repo": "example/app"},
    )
    result = run_collector(collector, config)
    if result.error is not None:
        raise SystemExit(f"collection failed: {result.error.code.value}")

    request = parse_request(_request_document(result))
    without_bindings = Verifier().verify(request)
    with_bindings = Verifier(trust_bindings=host_trust_bindings(result)).verify(request)

    for label, verified in (("without bindings", without_bindings), ("with host bindings", with_bindings)):
        decision = verified.decision.value if verified.decision else None
        print(f"{label}: execution_status={verified.execution_status.value} decision={decision}")
        print(f"{label}: reason_codes={list(verified.reason_codes)}")
    return without_bindings, with_bindings


if __name__ == "__main__":
    run()
