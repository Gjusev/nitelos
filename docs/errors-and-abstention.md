# Errors and abstention

Execution status and decision are independent. `input_error`/`backend_error`
always carry a null decision and a safe `ErrorInfo` (code, fixed message,
optional field path, retryable — only TIMEOUT/BUSY in v0.1).

## Errors (nothing was decided)

- `input_error`: malformed requests, bad digests, oversized/deep payloads,
  unsupported criterion kinds, path violations. No backend inference runs;
  criteria are empty.
- `backend_error`: a backend failed (invalid output, timeout, resource
  exhaustion...). Partial criterion results may be present and are explicitly
  flagged `PARTIAL_RESULTS_NONAUTHORITATIVE`.

## Abstention (execution ok, decision abstained)

Missing evidence is not failure, and pending is not failure:

| You supplied | Result |
|---|---|
| Nothing cited for a criterion | `unknown` / `MISSING_EVIDENCE` → abstained |
| A tool/action reporting completed | Behavioral context only → external criterion abstains |
| Pending-phase evidence | `PENDING_STATE` → abstained, never failure |
| Contradictory final snapshots | `CONTRADICTORY_EVIDENCE` → unknown |
| Unbound external claim | `UNTRUSTED_EXTERNAL` → ineligible → abstained |
| A criterion the backend cannot judge | `input_error/UNSUPPORTED_CAPABILITY` |
| Model output that is garbage | `backend_error/INVALID_OUTPUT` — never a guessed label |

The demo: an agent summary in metadata claims success while the observation
says `validation_error: true` → the no-error assertion is **refuted** →
`failure`. The same criterion with the observation simply absent →
**abstained**. Truth can be false while evidence cannot establish it.
