# Sync/async lifecycle

`Verifier.verify(request, artifacts=...)` is the canonical synchronous method.
`averify` is an async facade delegating the whole invocation to one bounded
worker thread per instance.

- **One in-flight call per instance.** A concurrent call returns
  `backend_error/BUSY` (retryable); a call after `close()` returns
  `backend_error/CLOSED`.
- **`close()` is idempotent, waits** for in-flight work, and closes the
  backend exactly once. The context manager (`with Verifier() as v:`) does
  this for you.
- **Cancellation is honest.** Cancelling the awaiting task propagates
  `CancelledError` immediately, but a running native kernel cannot be forcibly
  stopped: the instance stays BUSY until the work really ends. Hard isolation
  requires a caller-owned process — there is deliberately no fake async
  hard-timeout promise here.
- Configuration is immutable per instance: policy, backend and trust bindings
  are fixed at construction. Build a new `Verifier` per different external
  artifact set; never reuse a bound verifier across requests.

```python
from nitelos import TrustBinding, Verifier, VerificationPolicy

with Verifier(policy=VerificationPolicy(), trust_bindings=(binding,)) as verifier:
    result = verifier.verify(request, artifacts=raw_bytes)
```
