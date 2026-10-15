# Custom adapter conformance

A custom backend is trusted executable code injected as an instance —
`Verifier(backend=my_backend)`; there is no registry, import string or entry
point.

Your backend must implement the `Backend` protocol:

- `descriptor` → `BackendDescriptor` (ids, versions, hashes)
- `capabilities` → `BackendCapabilities` — **truthful limits**: integer maxima,
  never null; `max_images_per_criterion = 0` when you take no images
- `infer(prepared, context) -> BackendFinding` — synchronous, one criterion
- `close()` — idempotent

What you receive is immutable and minimal: a `PreparedVisualCriterion`
(criterion id, description, decoded `PreparedImage`s in declared order — no
file paths) and an `InferenceContext` (objective, bounded action context,
cooperative deadline). No trust bindings, labels or metadata ever reach a
model.

What you return is untrusted and validated before anything reaches a result.
Run the same conformance check the engine does:

```python
from nitelos.backends import validate_backend_finding

validate_backend_finding(finding, criterion_id=cid, images=prepared_images)
```

The rules (each violation is a `backend_error`, never an invented unknown):
exactly one finding per requested criterion with a legal state; decisive
findings need at least one reference to an image you were actually given;
references stay inside the prepared evidence (no foreign ids, no pointers on
screenshots, boxes within decoded bounds); `assertion_checked` grounding
cannot be self-asserted; `calibrated_probability` scores are rejected in
v0.1. Null and uncalibrated scores pass through and never affect decisions.
The BAK test suite (`tests/test_backend_contract.py`) documents every rule
with a fake backend — treat it as the executable spec.
