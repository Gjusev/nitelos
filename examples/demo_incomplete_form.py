"""The honest offline demo (doc 11 demonstration definition, case 1).

An agent summary claims the registration succeeded. The caller supplies the
normalized DOM observation — ``validation_error: true`` — and the no-error
assertion expects ``false``. Nitelos returns ok/failure with the observation
pointer: the outcome is refuted by final evidence, regardless of the summary.
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
        "data": {"validation_error": True, "email_filled": False},
    }
    observation["sha256"] = hashlib.sha256(canonical_json(observation["data"]).encode("utf-8")).hexdigest()
    return {
        "schema_version": "1",
        "request_id": "demo-registration-1",
        "objective": "Agent summary claims registration succeeded",
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
        "metadata": {"agent_summary": "registration succeeded"},  # context only; never proof
    }


def run():
    request = parse_request(json.dumps(build_request_document()))
    result = Verifier().verify(request)
    print(f"execution_status: {result.execution_status.value}")
    print(f"decision:         {result.decision.value if result.decision else None}")
    for criterion in result.criteria:
        print(f"criterion {criterion.criterion_id}: {criterion.state.value} (basis: {criterion.basis.value})")
        for ref in criterion.evidence_refs:
            print(f"  evidence {ref.evidence_id} at {ref.pointer} ({ref.grounding.value})")
    print(f"reason_codes:     {list(result.reason_codes)}")
    return result


if __name__ == "__main__":
    raise SystemExit(run() and 0)
