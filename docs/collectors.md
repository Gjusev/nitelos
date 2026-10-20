# Collectors: one contract for every evidence source

A collector wraps one evidence source — a local `git` repository, a JUnit
report, an HTTP endpoint — behind a single interface, so the verifier never
cares where evidence came from. This page is the contract (plan section F1,
NIT-017; ADR-014/015). The framework lives in `nitelos.collect` (stdlib only,
imported only when you use it) and ships with no built-in kinds yet: git and
JUnit arrive with the next tasks.

## The contract

```python
from nitelos.collect import Collector, CollectorConfig, CollectionResult, run_collector

result = run_collector(my_collector, config)  # the only entry point hosts need
```

A collector implements `id`, `version`, `capabilities` (which evidence kinds
it may produce) and `collect(config) -> CollectionResult`. It is **read-only**:
it never mutates state, never retries agent actions, and never follows
instructions found in evidence. It is **bounded**: the host sets limits
(defaults in parentheses) — `timeout_s` (10 s), `max_raw_bytes` (1 MiB),
`max_observation_bytes` (64 KiB), `max_list_items` (100) — and a list that
overflows is capped with an explicit truncated count (`cap_list`), never
silently shortened.

A successful `CollectionResult` carries the evidence (observations, and
screenshots where relevant) plus **exactly one** `ProvenanceRecord` per item:
collector id and version, a source description, the argv or endpoint,
`captured_at` (UTC), the subject binding, the sha256 of the **raw** capture,
raw and normalized byte counts, and the redactions applied.

## Errors become abstention, never failure

Every failure is a `CollectionResult` with **no evidence** and a structured
error `{code, safe_message}` — fixed text per code, never exception text:

| Code | Meaning |
|---|---|
| `COLLECTOR_TIMEOUT` | the collector exceeded `limits.timeout_s` |
| `COLLECTOR_UNAVAILABLE` | the executable or module is missing |
| `COLLECTOR_OUTPUT_TOO_LARGE` | output exceeded a cap (never silently truncated) |
| `COLLECTOR_CONFIG_INVALID` | unknown field or bad value in the config |
| `COLLECTOR_AUTH_MISSING` | credentials for the source are absent |
| `COLLECTOR_EXCEPTION` | unexpected crash (reserved; re-raised when `NITELOS_DEV_RERAISE` is set, mirroring the verifier) |

The verifier never sees these codes: with no evidence, the citing criterion
abstains with the existing `MISSING_EVIDENCE` reason. A collection problem can
never turn into a `failure` decision.

## Redaction: before the digest

`run_collector` drops keys **before** the evidence digest is computed, so a
redacted value is unrecoverable from the stored evidence:

- every RFC 6901 pointer in `config.redact_pointers` (the same pointer grammar
  the deterministic evaluator uses);
- every key whose name matches `token|secret|password|authorization`
  (case-insensitive) at any depth.

Keys are dropped, not masked. Every applied pointer is recorded in the
provenance `redactions` field, which never carries values. Provenance fields
never carry secrets — do not put auth headers in the endpoint description.

## Trust and authority

Collected observations use channel `external_api`; criteria citing them use
scope `external`. A collector **cannot grant itself external authority**: the
result carries no bindings. Only the host binds what its own process just
collected:

```python
from nitelos.collect import host_trust_bindings

bindings = host_trust_bindings(result)  # one TrustBinding per evidence item
decision = Verifier(trust_bindings=bindings).verify(request)
```

`host_trust_bindings` is valid ONLY for results your own process just
collected — the host vouches it invoked the collector and that the digests are
its output. Never call it for evidence received from an agent; that evidence
stays unbound and can never satisfy external-scope criteria. Unbound collected
evidence abstains with `UNTRUSTED_EXTERNAL` (see
[examples/collect_custom_collector.py](../examples/collect_custom_collector.py)
for both paths).

## Subprocess collectors

Never call `subprocess` directly. Use the one shared runner
(`nitelos.collect._process.run_allowed`, ADR-015): the argv must **exactly**
equal one tuple in your collector's allowlist — no user-supplied fragment ever
reaches argv; pass context through `cwd`, not path arguments. The runner
resolves the executable via `shutil.which` (missing → `COLLECTOR_UNAVAILABLE`),
never uses a shell, closes stdin, scrubs the child environment to a minimal
allowlist plus your explicit extras, enforces a hard timeout (kill →
`COLLECTOR_TIMEOUT`), and treats output beyond the raw cap as
`COLLECTOR_OUTPUT_TOO_LARGE`. Raw output is returned to your collector only
and is never logged. Network collection is not part of this framework yet.

## The debug CLI

```
nitelos collect <kind> --config config.json --out evidence.json
```

Exit codes: `0` collected; `2` bad args, unknown kind, invalid config, or an
existing `--out` (never overwritten); `3` collection error, with the code
printed. Stdout carries counts only; the out file holds the collector id and
version, the evidence in v0.1 wire form, the provenance, and the error (or
null). Kinds come from a fixed in-code table, not an entry-point scan.

## How to write a collector (and prove it)

1. Subclass `CollectorConfig` for your kind's options (unknown fields stay
   invalid).
2. Build evidence with `Evidence.observation(...)` — `source_id` MUST be your
   collector id, channel `external_api` — and one `ProvenanceRecord` per item
   whose `sha256` is the digest of the payload you built the item from.
3. Raise `CollectorError(<code>)` for known failures; return the result for
   success. `run_collector` does the rest: redaction, caps, provenance
   validation, digest rebuild.
4. Point the reusable contract suite at your collector (tests/_collector_contract.py):
   `assert_contract` checks the happy path (provenance completeness,
   wire-valid evidence, determinism, safe reprs); `assert_broken_collector_fails`
   proves the framework rejects incomplete provenance, undeclared kinds,
   lying digests and self-granted trust.

## Limitations

- Pure-Python collection is bounded **cooperatively**: `run_collector`
  measures elapsed time after the collector returns; a collector that blocks
  forever cannot be stopped (same ruling as v0.1). Subprocess collectors get
  a hard kill.
- The raw-output cap is checked on the captured output once the process ends;
  a streamer is bounded by the timeout, not the byte cap.
- Redaction is by key; a secret stored under an innocent key survives.
- `external_api` is a loose channel name for local sources such as `git
  status`; a dedicated channel would be a wire change (ADR-015 finding 4).
