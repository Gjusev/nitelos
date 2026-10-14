# JSON Schema snapshots

`request.v1.json` and `result.v1.json` are generated artifacts produced by
`VerificationRequest.model_json_schema()` and `VerificationResult.model_json_schema()`.
They are reviewed with code review and exist to make accidental schema drift visible.

They are a generated, **non-exhaustive subset of the runtime contract**, not a
standandalone validator. Passing these schemas does not mean a document is a valid
Nitelos request or result. Among other things, the JSON Schema vocabulary used here
cannot express:

- subject map pair bounds (1–16 string pairs) and other map-shape rules;
- the operator-conditioned `expected` field (scalar for `equals`, 1–64 scalars for
  `in`, absent for `exists`, with absence-vs-null distinguished);
- uniqueness of `evidence_ids` within a criterion and of IDs/sequences across the
  request;
- byte-size ceilings (request ≤ 1 MiB, payloads ≤ 64 KiB, metadata ≤ 8 KiB) and the
  JSON nesting ceiling (≤ 16 containers);
- defaults injected by `default_factory` (for example empty frozen collections) and
  cross-field invariants enforced by model validators.

The authoritative check is the runtime validation in `nitelos.schemas`
(`parse_request` and the model validators).

## Regenerating

After an intentional contract change, regenerate and review the diff:

```text
NITELOS_UPDATE_SNAPSHOTS=1 uv run pytest tests/test_contract.py -k snapshot
```

(PowerShell: `$env:NITELOS_UPDATE_SNAPSHOTS=1; uv run pytest tests/test_contract.py -k snapshot`)
