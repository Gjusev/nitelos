"""Map a nitelos verification to a DeepEval score (extra `deepeval`).

Runnable offline. A fixed observation decides one criterion; the metric maps
the verification result to the deterministic 1/0 score with a safe reason.
Without the `deepeval` extra installed the example exits 0 after printing
the gate requirements (an honest skip, like the other gated examples).
"""

from __future__ import annotations

import hashlib
import json

try:
    from deepeval.metrics import BaseMetric  # noqa: F401
except ImportError:
    print("skip: install 'nitelos[deepeval]' to run this example")
    raise SystemExit(0) from None

from nitelos import Verifier, canonical_json, parse_request
from nitelos.integrations.deepeval_metric import NitelosOutcomeMetric


def _result():
    data = {"deployed": True}
    observation = {
        "id": "obs-deploy",
        "kind": "observation",
        "sequence": 0,
        "captured_at": "2099-01-01T00:00:00Z",
        "checkpoint_id": "cp-demo",
        "source_id": "my-runner",
        "subject": {"service": "billing"},
        "phase": "final",
        "channel": "dom",
        "data": data,
    }
    observation["sha256"] = hashlib.sha256(canonical_json(data).encode("utf-8")).hexdigest()
    document = {
        "schema_version": "1",
        "request_id": "deepeval-demo",
        "objective": "Deploy the billing service",
        "checkpoint_id": "cp-demo",
        "as_of": "2099-01-01T00:00:01Z",
        "criteria": [
            {
                "id": "deployed",
                "description": "The service reports deployed",
                "kind": "assertion",
                "scope": "observed_state",
                "evidence_ids": ["obs-deploy"],
                "subject": {"service": "billing"},
                "pointer": "/deployed",
                "operator": "equals",
                "expected": True,
            }
        ],
        "evidence": [observation],
        "metadata": {},
    }
    return Verifier().verify(parse_request(json.dumps(document)))


def main() -> int:
    metric = NitelosOutcomeMetric(_result)
    score = metric.measure(None)
    print(f"score: {score}")
    print(f"is_successful: {metric.is_successful()}")
    print(f"reason: {metric.reason}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
