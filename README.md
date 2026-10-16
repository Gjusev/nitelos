# Nitelos

[![PyPI version](https://img.shields.io/pypi/v/nitelos.svg)](https://pypi.org/project/nitelos/) ![Python](https://img.shields.io/pypi/pyversions/nitelos.svg)

**Verify the outcome, not the attempt.**

Nitelos is a Python SDK that checks whether an agent's success criteria are supported
by evidence you supply — normalized observations, screenshots, actions and
host-authorized external reads. It never acts on the agent's behalf: no clicks, no
network fetches, no retries. A result is a time-scoped judgment over explicit
criteria, not a transaction guarantee.

## What "verified" means here

Verification is scope-relative. A criterion says exactly what final condition must
hold, for which subject, at which checkpoint — and Nitelos reports
`success`/`failure`/`abstained` **for those criteria against that evidence**:

- A **deterministic assertion** (JSON pointer + equals/in/exists over a normalized
  observation) is fully checked by the SDK: `supported`, `refuted` or `unknown`,
  with the exact evidence references that decided it.
- An **external** criterion additionally requires a host-constructed
  `TrustBinding` — imported JSON can never authorize its own external claims.
- A **visual** criterion (optional, experimental) is decided by a local
  image model only when you explicitly opt in; every such result is labeled
  `model_inferred` and carries the `VISUAL_GROUNDING_UNVERIFIED` limitation.

Missing evidence abstains. Contradictions become unknown. A tool reporting
"completed" never proves an outcome.

## Quickstart (deterministic, offline)

```python
import hashlib, json
from nitelos import Verifier, canonical_json, parse_request

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

request = parse_request(
    json.dumps(
        {
            "schema_version": "1",
            "request_id": "quickstart-1",
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

result = Verifier().verify(request)
print(result.decision)  # success | failure | abstained (or None on execution errors)
```

The default is a plain `Verifier()` with the strict `VerificationPolicy`
(model inference disallowed); screenshots arrive via `Evidence.screenshot(...)`
plus a raw-bytes mapping, and `ArtifactStore`/`TrustBinding` cover the
image-store and external-trust cases in the guides below. Field names follow
the schema-1 `VerificationRequest` contract.

See [examples/quickstart.py](examples/quickstart.py) for the runnable script and
[docs/quickstart.md](docs/quickstart.md) for the walkthrough. The agent-summary
demo — a claim of success refuted by a `validation_error` observation — is
[examples/demo_incomplete_form.py](examples/demo_incomplete_form.py); the
pending-external abstention is
[examples/demo_external_pending.py](examples/demo_external_pending.py).

## Deterministic vs experimental

Everything in the quickstart is deterministic and offline: assertions, eligibility
(subject/checkpoint/freshness/phase), trust bindings, aggregation and every error
code. The optional local visual backend (SmolVLM) is **experimental**; its
executability gate is under review, and it is disallowed by the default policy.
No benchmark numbers are published yet — evaluation runs have not been executed.

## Documentation

- [Installation](docs/installation.md) — core / `eval` / `local` extras
- [Quickstart](docs/quickstart.md)
- [What verified success means](docs/success-criteria.md)
- [Evidence and provenance limits](docs/evidence-limits.md)
- [Sync/async lifecycle](docs/lifecycle.md)
- [Errors and abstention](docs/errors-and-abstention.md)
- [Backends and compatibility](docs/backends.md)
- [Custom adapter conformance](docs/custom-adapters.md)
- [Traces and caller collection](docs/traces.md)
- [Evaluation and calibration limitations](docs/evaluation.md)
- [Security and privacy](docs/security-privacy.md)
- [Performance measurement](docs/performance.md)
- [Contributing](CONTRIBUTING.md) · [Security policy](SECURITY.md)

Apache-2.0. Python 3.12/3.13.
