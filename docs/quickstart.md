# Quickstart

The shortest honest path: one assertion criterion over a normalized DOM
observation, verified deterministically and offline.

1. **Capture evidence yourself.** nitelos never drives a browser. Reduce what
   your agent saw into small JSON observations (see [traces.md](traces.md) for
   the caller recipe).
2. **Hash the payload** with `canonical_json`. The SDK re-checks every digest at
   verification time, so the evidence cannot change after it was captured.
3. **State the criterion** as a required final condition: pointer, operator,
   expected value, subject and evidence references.
4. **Verify** and read the structured result.

## The complete script

Install first (`pip install nitelos`, Python 3.12 or 3.13), then run:

```python
import hashlib
import json

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
print(f"execution_status: {result.execution_status.value}")
print(f"decision:         {result.decision.value if result.decision else None}")
for criterion in result.criteria:
    print(f"criterion {criterion.criterion_id}: {criterion.state.value} (basis: {criterion.basis.value})")
print(f"reason_codes:     {list(result.reason_codes)}")
```

Output:

```text
execution_status: ok
decision:         success
criterion no-errors: supported (basis: deterministic)
reason_codes:     ['ALL_CRITERIA_SUPPORTED']
```

The same script is [examples/quickstart.py](../examples/quickstart.py).

## Change one value, watch the decision move

Set `"validation_error": True` in the observation (and keep the digest line, which
recomputes the hash) and run again: the criterion is `refuted` and the decision
is `failure`. That is exactly the agent-summary demo,
[demo_incomplete_form.py](../examples/demo_incomplete_form.py), which also
prints the evidence reference that decided it.

Two more examples complete the set: the external criterion with no external
record, which abstains
([demo_external_pending.py](../examples/demo_external_pending.py)), and the gated
visual example ([demo_visual_optional.py](../examples/demo_visual_optional.py)).

## Next steps

- Screenshots ride along as `Evidence.screenshot(...)` items plus an
  `ArtifactStore` of raw bytes (`artifacts={"art-1": png_bytes}`). Visual
  criteria only decide when a backend is configured and the policy opts in.
- External criteria need a `TrustBinding` built by your host; see
  [evidence-limits.md](evidence-limits.md).
- Wiring nitelos into a real agent run: [traces.md](traces.md) and
  [recipes/caller-collection.md](recipes/caller-collection.md).
- Every decision and error code: [errors-and-abstention.md](errors-and-abstention.md).
