"""Demo case 2 (doc 11): tool success alone cannot satisfy an external criterion.

An upload action reports ``completed``, but the criterion requires the stored file
to appear in an external system. No external snapshot was captured, so the honest
outcome is ok/abstained — missing evidence, not failure and not success.
"""

from __future__ import annotations

import hashlib
import json

from nitelos import Verifier, canonical_json, parse_request

AS_OF = "2026-10-20T10:01:00Z"


def build_request_document() -> dict[str, object]:
    action_view = {
        "name": "upload-file",
        "arguments": {"bucket": "synthetic-bucket"},
        "reported_status": "completed",
        "tool_result_id": None,
    }
    action = {
        "id": "act-upload",
        "kind": "action",
        "sequence": 0,
        "captured_at": "2026-10-20T10:00:00Z",
        "checkpoint_id": "cp-final",
        "source_id": "my-agent-runner",
        "subject": {"upload": "report-export-7"},
        "phase": "final",
        "sha256": hashlib.sha256(canonical_json(action_view).encode("utf-8")).hexdigest(),
        **action_view,
    }
    return {
        "schema_version": "1",
        "request_id": "demo-upload-1",
        "objective": "Store the exported report in the external system",
        "checkpoint_id": "cp-final",
        "as_of": AS_OF,
        "criteria": [
            {
                "id": "stored",
                "description": "The exported report is stored in the external system",
                "kind": "assertion",
                "scope": "external",
                "evidence_ids": [],
                "subject": {"upload": "report-export-7"},
                "pointer": "/status",
                "operator": "equals",
                "expected": "stored",
            }
        ],
        "evidence": [action],
        "metadata": {},
    }


def run():
    request = parse_request(json.dumps(build_request_document()))
    result = Verifier().verify(request)
    print(f"execution_status: {result.execution_status.value}")
    print(f"decision:         {result.decision.value if result.decision else None}")
    for criterion in result.criteria:
        print(f"criterion {criterion.criterion_id}: {criterion.state.value}")
    print(f"reason_codes:     {list(result.reason_codes)}")
    return result


if __name__ == "__main__":
    raise SystemExit(run() and 0)
