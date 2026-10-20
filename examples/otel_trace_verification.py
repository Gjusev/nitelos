"""Trace a verification with OpenTelemetry (extra `otel`).

Runnable offline. It prints the result and one `nitelos.verify` span with the
allowlisted attributes, using the SDK console exporter. The
`opentelemetry-sdk` package is a separate install from the `otel` extra (it is
part of the development environment); nothing is sent anywhere.
"""

from __future__ import annotations

import hashlib
import json

from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import ConsoleSpanExporter, SimpleSpanProcessor

from nitelos import Verifier, canonical_json, parse_request
from nitelos.integrations.otel import verify_traced


def main() -> None:
    observation = {
        "id": "obs-form",
        "kind": "observation",
        "sequence": 0,
        "captured_at": "2026-10-20T10:00:00Z",
        "checkpoint_id": "cp-final",
        "source_id": "my-runner",
        "subject": {"form": "registration-1"},
        "phase": "final",
        "channel": "dom",
        "data": {"validation_error": True},
    }
    observation["sha256"] = hashlib.sha256(canonical_json(observation["data"]).encode("utf-8")).hexdigest()

    request = parse_request(
        json.dumps(
            {
                "schema_version": "1",
                "request_id": "otel-example-1",
                "objective": "Complete the registration form",
                "checkpoint_id": "cp-final",
                "as_of": "2026-10-20T10:01:00Z",
                "criteria": [
                    {
                        "id": "no-errors",
                        "description": "No validation error remains on the form",
                        "kind": "assertion",
                        "scope": "observed_state",
                        "evidence_ids": ["obs-form"],
                        "subject": {"form": "registration-1"},
                        "pointer": "/validation_error",
                        "operator": "equals",
                        "expected": False,
                    }
                ],
                "evidence": [observation],
            }
        )
    )

    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))
    tracer = provider.get_tracer("example")

    result = verify_traced(Verifier(), request, tracer=tracer, collector_ids=("my-collector",))
    print(f"execution_status: {result.execution_status}")
    print(f"decision: {result.decision}")
    provider.shutdown()


if __name__ == "__main__":
    main()
