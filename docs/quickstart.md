# Quickstart

The shortest honest path: one assertion criterion over a normalized DOM
observation, verified deterministically and offline.

1. **Capture evidence yourself.** Nitelos never drives a browser. Reduce what
   your agent saw into small JSON observations (see
   [traces.md](traces.md) for the caller recipe).
2. **Hash the payload** with `canonical_json` — the SDK verifies digests at
   verification time.
3. **State the criterion** as a required final condition: pointer, operator,
   expected value, subject and evidence references.
4. **Verify** and read the structured result.

```python
from nitelos import Verifier, parse_request

request = parse_request(request_json_text)
result = Verifier().verify(request)
print(result.execution_status)  # ok | input_error | backend_error
print(result.decision)  # success | failure | abstained (None on errors)
for criterion in result.criteria:
    print(criterion.criterion_id, criterion.state, criterion.basis, criterion.reason_codes)
```

The full script with the digest computation is
[examples/quickstart.py](../examples/quickstart.py). The demo trio lives in
`examples/`: the refuted agent summary
([demo_incomplete_form.py](../examples/demo_incomplete_form.py)), the pending
external abstention ([demo_external_pending.py](../examples/demo_external_pending.py)),
and the gated visual example
([demo_visual_optional.py](../examples/demo_visual_optional.py)).

Screenshots ride along as `Evidence.screenshot(...)` items plus an
`ArtifactStore` of raw bytes (`artifacts={"art-1": png_bytes}`); visual criteria
only decide when a backend is configured and the policy opts in.
