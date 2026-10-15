"""Quickstart: verify an outcome with a deterministic assertion, fully offline.

This is the shortest honest path: build a request with one assertion criterion
over a normalized DOM observation, verify it, and print the structured result.
No model, no network, no browser — the caller supplies the evidence.
"""

from __future__ import annotations

import hashlib
import json

from nitelos import Verifier, canonical_json, parse_request

AS_OF = "2026-10-20T10:01:00Z"


def build_request_document() -> dict[str, object]:
    observation = {
        "id": "obs-form",
        "kind": "observation",
        "sequence": 0,
        "captured_at": "2026-10-20T10:00:00Z",
        "checkpoint_id": "cp-final",
        "source_id": "my-agent-runner",
        "subject": {"form": "registration-1"},
        "phase": "final",
        "channel": "dom",
        "data": {"validation_error": False, "email_filled": True},
    }
    observation["sha256"] = hashlib.sha256(canonical_json(observation["data"]).encode("utf-8")).hexdigest()
    return {
        "schema_version": "1",
        "request_id": "quickstart-1",
        "objective": "Complete the registration form",
        "checkpoint_id": "cp-final",
        "as_of": AS_OF,
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
        "metadata": {},
    }


def main() -> int:
    request = parse_request(json.dumps(build_request_document()))
    result = Verifier().verify(request)
    print(f"execution_status: {result.execution_status.value}")
    print(f"decision:         {result.decision.value if result.decision else None}")
    for criterion in result.criteria:
        print(f"criterion {criterion.criterion_id}: {criterion.state.value} (basis: {criterion.basis.value})")
    print(f"reason_codes:     {list(result.reason_codes)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
