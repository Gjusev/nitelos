# Implementation decisions and carried-forward requirements

Binding records from architectural reviews. Briefs for later tasks must include the items addressed to them.

## AR-1 (NIT-002 contracts) — 2026-10-14

Reviewer: nitelos-0f (independent of implementer nitelos-69). Verdict: APPROVE-WITH-CHANGES, no blockers.

Accepted interpretations (doc 03 ambiguity resolutions, not contract changes):
- Collection counts and byte/depth ceilings → `LIMIT_EXCEEDED`; scalar/string bounds and empty criteria list → `INVALID_SCHEMA`.
- `parse_request` reports only the first issue (deterministic doc-05 ordering); issue tuple shape leaves room for more.
- `action.tool_result_id` must reference a `tool`-channel observation with a strictly greater sequence.
- `exists` must omit `expected`; explicit `expected: null` is rejected; `equals` accepts `null`.
- Wire timestamps: RFC3339 with `Z`, at most 6 fractional digits.

Public names beyond the doc-11 inventory, accepted as deliberate v1 public API (additive; NIT-014 documents them):
- `canonical_json` (Nitelos canonical JSON v1, named in doc 03), the schema enums (Scope, Phase, Channel, …, LimitationCode) and `Issue`.
- Note for NIT-003: canonical JSON keeps `1` and `1.0` textually distinct, so their payload digests differ; document this.

JSON Schema snapshots (`tests/schemas/`) are a generated, non-exhaustive subset of the runtime contract, not a standalone validator.

Carried forward:
- **NIT-006 (binding):** `Verifier.verify` must re-check the request byte ceiling (1 MiB canonical), the metadata (8 KiB) and per-payload (64 KiB) ceilings, and nesting depth for typed requests that bypass `parse_request`, returning `input_error/LIMIT_EXCEEDED`. This needs acceptance tests on the typed-request path. It must also guarantee that `(ok, *)` results always carry one CriterionResult per request criterion (the schema permits an empty list).
- **NIT-003:** evidence factories return the concrete variants (the `Evidence` base is instantiable but cannot enter a request).
- **NIT-004:** reuse the RFC 6901 pointer grammar from `schemas.py` rather than a second implementation.
