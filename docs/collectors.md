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
`captured_at` (UTC), the subject binding, the sha256 of the **raw** capture
(e.g. the exact subprocess stdout bytes — not canonical JSON; a raw digest of
low-entropy content can be brute-forced offline, so keep secrets out of the
capture), `evidence_sha256` (set by `run_collector` to the final post-redaction
evidence digest), raw and normalized byte counts (raw may be zero — a clean
tree's output is legitimately empty), and the redactions applied.
`run_collector` cross-checks every item and record against the collector and
the config — source id, `external_api` channel, subject, checkpoint, collector
id/version, `captured_at`, unique sequences at or after `sequence_start` —
and rejects any mismatch with `COLLECTOR_EXCEPTION`, so a collector cannot
vouch for another source, subject or moment.

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

`host_trust_bindings` is valid ONLY for results returned by `run_collector`
in this process — raw `collect()` output is unredacted and unchecked — the
host vouches that it invoked the collector and that the digests are that run's
output. Never call it for evidence received from an agent; that evidence
stays unbound and can never satisfy external-scope criteria. Unbound collected
evidence abstains with `UNTRUSTED_EXTERNAL` (see
[examples/collect_custom_collector.py](../examples/collect_custom_collector.py)
for both paths).

## Subprocess collectors

Never call `subprocess` directly. Use the one shared runner
(`nitelos.collect._process.run_allowed`, ADR-015). Guarantees: the argv must
**exactly** equal one tuple in your collector's allowlist — no user-supplied
fragment ever reaches argv; pass context through `cwd`, not path arguments.
`argv[0]` must be a bare name or an absolute path; bare names resolve only
against absolute `PATH` entries (never the current directory, never relative
entries), and `.bat`/`.cmd` targets are rejected (they are shell programs).
The runner never uses a shell, closes stdin, and scrubs the child environment
to a minimal allowlist plus your explicit extras. Output is read incrementally
with a running byte count: exceeding `max_raw_bytes` kills the process tree
immediately (`COLLECTOR_OUTPUT_TOO_LARGE` — never silent truncation, never
unbounded buffering). The timeout covers process exit AND both pipes reaching
EOF, and kills the whole tree — the child's own session (POSIX
`start_new_session` + `killpg`) or a Job Object with kill-on-close (Windows,
`taskkill /T` fallback) — so a grandchild holding inherited pipes (the
`Git\cmd\git.exe` shim's real git) cannot extend the wait; the post-kill reap
is bounded. The result carries stdout, stderr and the exit code (so "not a
repository" is distinguishable from empty output); raw output is never logged.
An `OSError` at process creation (bad cwd, exec format) maps to
`COLLECTOR_UNAVAILABLE`. Network collection is not part of this framework yet.

## The git collector (`nitelos[git]`, NIT-018)

`nitelos.collect.git.GitCollector` (kind `git`, config `GitCollectorConfig`
with `repo_path`) reports one observation under `/git/...`: `head_sha`,
`branch` (null when detached, with `detached: true`), `dirty_count`,
`dirty_paths[]` (tracked changes, capped at 200 and by
`limits.max_list_items`, with the dropped count in `dirty_paths_truncated`),
`untracked_count`, `ahead`/`behind`/`upstream` (null without an upstream),
and `last_commit.{subject_sha256,timestamp}` (null before the first commit).

It runs exactly four hardened argvs through the shared runner:
`git -c core.fsmonitor=false {rev-parse HEAD | status --porcelain=v2 --branch
| log -1 --format=%s%n%ct | rev-list --left-right --count @{upstream}...HEAD}`
with `GIT_OPTIONAL_LOCKS=0` and `GIT_CONFIG_NOSYSTEM=1`. There is deliberately
no `safe.directory` bypass: a repository git refuses as dubious ownership
fails the collection with `COLLECTOR_UNAVAILABLE`, as does a directory that is
not a repository or a missing git binary. A non-zero exit from `status` means
no state; the other commands' failures just null their fields (unborn head,
vanished upstream).

Limitation worth knowing: the scrubbed environment does not inherit the
user's `core.autocrlf`, so a CRLF working tree over LF-normalized blobs
reports as dirty — correct for a byte-level view, surprising if you rely on
your global line-ending config. The provenance `sha256` digests the
concatenated raw stdouts.

## The shared GET transport and the GitHub collector (`nitelos[github]`, NIT-020)

Network collection goes through one shared transport
(`nitelos.collect._http`, the ADR-015 collector exception): GET only,
`https://` only, TLS verification on, redirects followed only within the
original host (a cross-host redirect raises `COLLECTOR_UNAVAILABLE` and never
leaks the Authorization header to another origin), the body read incrementally
with a running byte count (`COLLECTOR_OUTPUT_TOO_LARGE` at the cap, never
silent truncation), socket timeouts → `COLLECTOR_TIMEOUT`. The transport is
an injectable seam: offline tests replay recorded fixtures and never open a
socket; the default transport is the framework's only network path.

`GithubCollector` (kind `github`, config with `owner`/`repo`/`pr_number` and
an optional `enterprise_host`) reports one observation under `/github/pr/`:
`state`, `merged`, `draft`, `head_sha`, `mergeable_state`, `review_decision`
(DERIVED from the latest APPROVED/CHANGES_REQUESTED review per reviewer — an
approximation of GraphQL's field, kept REST-only), `checks[]` (name/status/
conclusion from the head sha's check-runs), `required_checks` (branch
protection contexts; null when unreadable — e.g. no admin scope — rather
than guessed) and `checks_all_green` (computed from REQUIRED checks only; a
failing non-required check does not flip it; null when the required set is
unknown). Token from `GITHUB_TOKEN` or `GH_TOKEN` — a read-only fine-grained
token with Pull requests: read and Checks: read suffices (Contents: read for
protection contexts); the token never appears in evidence, provenance, logs
or stdout. Status mapping to abstention: 401 → `COLLECTOR_AUTH_MISSING`;
rate limit (429 or 403 with `X-RateLimit-Remaining: 0`) and 404 →
`COLLECTOR_UNAVAILABLE`; other 4xx → `COLLECTOR_CONFIG_INVALID`; 5xx →
`COLLECTOR_UNAVAILABLE`.

## The debug CLI

```
nitelos collect <kind> --config config.json --out evidence.json
```

(from a checkout, before the console script is installed:
`python -m nitelos.cli collect <kind> …`)

Exit codes: `0` collected; `2` bad args, unknown kind, invalid config, or an
existing `--out` (created with mode `x` — never overwritten, even under a
race); `3` collection error, with the code printed. Stdout carries counts
only; the out file holds the collector id and version, the evidence in v0.1
wire form, the provenance, and the error (or null). Kinds come from a fixed
in-code table, not an entry-point scan; configs validate through the
collector's own `config_model` in JSON mode, so kind-specific fields and JSON
shapes (arrays for `redact_pointers`) work from files.

## How to write a collector (and prove it)

1. Subclass `CollectorConfig` for your kind's options, declare it as the
   collector's `config_model` (mappings and JSON files both validate through
   it), and derive per-item evidence ids with `derive_evidence_id(base,
   index)` (deterministic; ID-pattern and length checked). A kind's own list
   caps (say, 200 dirty paths) are clipped by `limits.max_list_items` — the
   framework limit always wins; a kind may only ask for fewer items.
2. Build evidence with `Evidence.observation(...)` — `source_id` MUST be your
   collector id, channel `external_api` — and one `ProvenanceRecord` per item
   whose `sha256` is the digest of the raw capture.
3. Raise `CollectorError(<code>)` for known failures; return the result for
   success. `run_collector` does the rest: cross-checks, redaction, caps,
   provenance validation, digest rebuild.
4. Point the reusable contract suite at your collector
   (tests/_collector_contract.py): `assert_contract` checks the happy path
   (provenance completeness and cross-checks, wire-valid evidence, a decisive
   round trip under `host_trust_bindings`, determinism, safe reprs) plus
   generic probes (observation cap → `COLLECTOR_OUTPUT_TOO_LARGE`, unknown
   config field → `COLLECTOR_CONFIG_INVALID`, and — when you pass the `slow`
   hook — timeout → `COLLECTOR_TIMEOUT`); `assert_broken_collector_fails`
   proves the framework rejects a violating collector with the specific code.

## Limitations

- Pure-Python collection is bounded **cooperatively**: `run_collector`
  measures elapsed time after the collector returns; a collector that blocks
  forever cannot be stopped (same ruling as v0.1). Subprocess collectors get
  a hard kill.
- A corpse that survives even a tree kill cannot hang the runner, but may
  briefly outlive it; pipes whose readers never drained are leaked on purpose
  (closing them under a blocked reader would deadlock).
- Redaction is by key; a secret stored under an innocent key survives.
- `external_api` is a loose channel name for local sources such as `git
  status`; a dedicated channel would be a wire change (ADR-015 finding 4).

## The Playwright page-state helper (`nitelos[playwright]`, NIT-022)

`nitelos.integrations.playwright_capture.capture_page_state(page, selectors,
..., artifacts=...)` takes the caller's LIVE Playwright `Page` (sync API) and
captures — never drives: no navigation, clicks, fills, waits or evaluation;
it touches only `page.url`, `page.title()`, `page.screenshot(full_page=True)`
and the per-selector `text_content()/is_visible()/input_value()/count()` (a
non-input element yields `value: null`, never an error). The result is one
observation under `/page/` (url, title, per-selector text/visible/value/
count) plus one full-page screenshot evidence item, run through the NIT-017
framework — provenance, cross-checks, the observation cap and redaction all
apply (note: selector keys are dict keys, so a selector matching the secret
pattern is redacted — prefer neutral names). Screenshot bytes go to the
caller's `artifacts` dict, never to files; `captured_at` is the capture
moment, so criteria freshness governs like any other evidence. The module
imports playwright never — the `playwright` extra is the caller's
dependency; the async API is not supported in v0.2.
