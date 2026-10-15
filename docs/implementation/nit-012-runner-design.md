# NIT-012 design specification — reproducible sequential evaluation runner

Status: **design only, no code**. NIT-012 waits for NIT-006, NIT-010 and NIT-011; this
spec fixes the runner's shape now. Normative sources: doc 06 ("Manifest and runner
contract", metrics, "Reporting and negative results"), doc 03 (limits, PATH_NOT_ALLOWED,
Diagnostics/Measurements), doc 07 (SEC-07 path defenses; "Evaluation writes results only
to a user-selected new directory"), doc 12 (commands, EVAL family, exit codes), doc 10
(NIT-012/NIT-013, RUN-01/02), doc 11 (public names `load_evaluation_manifest`,
`evaluate`, `compare_reports`), decisions.md carry-forwards (oracle-triple validation;
run-level cost/RAM/throughput), the NIT-010 benchmark design (layout, fixture collector,
views) and NIT-011 `metrics.py` (`CaseRecord`). The merged schemas/evidence/policy
modules and the planned `Verifier.verify(request_or_mapping, *, artifacts=None)` API are
assumed.

## 0. Flagged ambiguities and chosen readings (veto points)

- **A1 — per-case oracle files.** Doc 06 gives each case an "oracle relative path"; the
  NIT-010 design currently writes one `oracle/<split>.json`. Reading adopted: **one
  oracle file per case** (`oracle/<case_id>.json`, strict schema, one object each) so the
  manifest path is a plain relative path with no fragment syntax. NIT-010's layout
  section is amended accordingly (it is not yet implemented; no migration cost). The
  oracle loader validates the conformance triples on load (decisions.md): an `expected`
  entry with error status must carry a null decision; `ok` requires a decision.
- **A2 — output directory must not exist at all.** "Refuse overwrite" and "user-selected
  new directory" are enforced as: `output_dir` raises/exit-2 if the path exists in any
  form (even an empty directory). Reruns always target a new directory; there is no
  resume.
- **A3 — completeness ground truth is a marker file.** `run.json` is written first with
  `status: "running"`; completion is signaled by `COMPLETE` (written via
  `os.replace` of a temp file — atomic). A hard crash leaves `status: "running"` and no
  marker: RUN-01 treats any run directory without `COMPLETE` as explicitly incomplete,
  deriving counts from `cases.jsonl`. This is crash-safe without two-phase commits.
- **A4 — manifest unknown fields are a hard error.** The manifest uses strict
  `extra="forbid"` parsing, so a manifest carrying trust-looking fields fails validation
  (exit 2) rather than being silently ignored — stronger than "cannot create a binding".
- **A5 — peak RSS method per platform.** Linux: `resource.getrusage(RUSAGE_SELF)
  .ru_maxrss` (KiB, reported as bytes, method recorded). Windows: `ctypes`
  `GetProcessMemoryInfo` `PeakWorkingSetSize` when callable, else null with reason.
  Baseline (no-model) RSS is NOT subtracted; both raw values are reported so a reader
  can subtract. Unmeasured stays null with a reason, never zero.
- **A6 — `cases.jsonl`, one JSON object per line, flushed per case** (chosen over one
  file per case: append-only crash safety and cheap line counting for RUN-02).
- **A7 — interruption handling.** Only infrastructure failures abort the loop (I/O,
  manifest/oracle invalidity mid-run, verifier-factory construction errors). Per-case
  input/backend errors are persisted as case results and never abort (doc 06).
  `KeyboardInterrupt`/`SystemExit` are caught **only at the CLI top level**, where the
  incomplete marker and counts are written and the exit code becomes 3 — then the
  exception propagates (nothing is swallowed; the library-level `evaluate` lets control
  exceptions fly after writing status best-effort).

## 1. EvaluationManifest schema 1 (requirement 1)

Strict Pydantic model, `extra="forbid"` (A4), frozen. Fields (doc 06):

```json
{
  "schema_version": "1",
  "benchmark_id": "nitelos-synthetic-v1",
  "benchmark_version": 1,
  "split": "dev",                       // "dev" | "test"
  "evidence_view": "assertion",         // "assertion" | "visual"
  "seed": null,                          // integer or null; fixed by the benchmark
  "policy": {                            // reviewed configuration; hash = policy_hash()
    "id": "strict", "version": "1", "allow_model_inference": false, "hash": "<sha256>"
  },
  "cases": [
    {
      "case_id": "<uuid-like>",
      "group_id": "s01:L1",
      "primary_scenario": "S01",
      "request": "requests/<case>-<view>.json",     // relative path (§2 rules)
      "artifacts": [ {"id": "art-1", "path": "artifacts/<file>.png", "sha256": "<hex>"} ],
      "oracle": "oracle/<case_id>.json"              // A1
    }
  ],
  "provenance": {
    "license": "Apache-2.0", "synthetic": true,
    "data_card": "DATA_CARD.md", "generator_version": "<str>", "freeze_sha256": "<hex>"
  },
  "configuration_fingerprint": "<sha256>",           // §6; verified to match the run
  "expected_count": 60
}
```

Limits enforced at load: manifest file ≤ 4 MiB; `len(cases) == expected_count`;
`len(cases) ≤ 10 000`; case IDs unique; every path passes §2 validation; artifact IDs
unique per case; the recorded policy hash equals `policy_hash(parse_policy(policy))`.
Each referenced request is itself parsed by `parse_request` (doc 03 limits apply). The
`allow_model_inference` value is the reviewed opt-in that NIT-010-A5's visual-view
expected decisions assume.

`load_evaluation_manifest(path, artifacts_root)` (public name per doc 11) returns a
validated, frozen manifest bound to a resolved root; all later loads are relative to it.

## 2. Safe path loading (requirement 2, SEC-07)

One function, `safe_relative_path(root, relative) -> Path`, used for requests, artifacts,
oracle and fixture-collector files. Checks, in order, stdlib-only and identical on
Windows and Linux:

1. **String-level rejection** of the raw, un-normalized relative path (`input_error/
   PATH_NOT_ALLOWED`, safe message, path `$.cases[i]…` context added by the caller):
   - empty; contains NUL (`"\x00"`); backslashes are treated as literal characters that
     can never match a real file on POSIX, so any `\` is rejected outright (this also
     kills `\\server\share`, `\\?\C:\…`, `\\.\…` and `C:\…` forms on sight);
   - absolute POSIX paths (`PurePosixPath(p).is_absolute()`), drive letters
     (`^[A-Za-z]:`), and UNC prefixes (`^//` after treating leading `//` as absolute
     too);
   - any `..` component (before or after normalization — both rejected; `.` components
     are dropped by normalization but a path consisting only of `.` is rejected);
   - any `:` anywhere (alternate data streams `file:stream` and drive remnants);
   - Windows-reserved characters in any component: `< > " | ? *`;
   - components whose names end with a dot or a space (`"x."`, `"x "` — Windows strips
     these, creating aliasing);
   - device names: the component's first dot-split token, case-insensitively, in
     {CON, PRN, AUX, NUL, COM1–COM9, LPT1–LPT8} — this catches `CON`, `NUL.txt`,
     `com1.log`.
2. **Root confinement with link resolution**: `resolved = Path(os.path.realpath(root /
   relative))` and `resolved_root = Path(os.path.realpath(root))`; require
   `resolved.is_relative_to(resolved_root)`. `realpath` resolves symlinks and, on
   Windows (Py 3.12 `ntpath.realpath`), junctions and other reparse points, so any link
   escaping the root fails this check. Links that stay inside the root are allowed (doc
   07 rejects only escaping links).
3. **Kind check**: the final path must be a regular file (`Path.is_file()` follows
   links; a link to a directory or device fails here).

No archive extraction anywhere: the runner opens individual files only; the module
contains no `zipfile`/`tarfile` imports (asserted by a test). File-size caps: manifest
≤ 4 MiB; each request file is fed to `parse_request` (1 MiB ceiling); artifacts go
through `ArtifactStore` + `prepare_evidence` (8/32 MiB image ceilings, NIT-003).

**SEC-07 test table** (each → `PATH_NOT_ALLOWED`, plus positive controls): `../x`,
`a/../../b`, `/abs`, `C:\x`, `\\server\share\x`, `\\?\C:\x`, `\\.\NUL`, `a:b` (ADS),
`CON`, `NUL.bin`, `com1.log`, `x.`, `x `, `a<b`, `..\x`, path containing `\x00`,
`..` alone, `//server/share`, deep-but-legal positive, inside-root symlink (positive),
symlink escaping root (negative, created in tmp), Windows junction escaping root
(negative, `pytest.mark.skipif(not windows)`), reparse-point path (negative,
Windows-only). Plus: no-extraction test (a crafted `.zip` artifact path is just a file;
nothing decompresses it).

## 3. Oracle separation (requirement 3, EVAL-04)

Two disjoint types and loaders, never mixed:

- `BackendCaseData` (pre-inference): parsed `VerificationRequest`, `ArtifactStore`,
  per-case `TrustBinding` tuple — exactly what the verifier factory receives.
- `OracleRecord` (post-inference): truth/sufficiency/expected-per-view/state/rationale/
  annotators (NIT-010 §6), loaded by a separate `load_oracle(root, case)` only after
  that case's inference result exists — in practice in the metrics phase; strict schema,
  triple validation per decisions.md (error status ⇒ null expected decision; ok ⇒
  decision present; violations are infrastructure failures: incomplete run, exit 3,
  results preserved).

`evaluate()`'s verifier factory parameter receives `(case_id, request, artifacts,
bindings)` — structurally incapable of carrying oracle data. **EVAL-04 proof**: a
recording factory wraps the real verifier and serializes every object it receives; the
test poisons oracle records with a sentinel field/value and asserts the sentinel never
appears in anything the factory saw, in the backend inputs, or in `cases.jsonl`; plus a
determinism check — two runs over the same manifest produce byte-identical reports
modulo the whitelist `{run_id, started_at, finished_at, elapsed/duration fields}`.

## 4. Fixture trust (requirement 4)

The reviewed `fixture-collector.json` (NIT-010 §8) lives at a fixed relative path under
the artifact root and is loaded once by the built-in fixture-collector configuration:
for every entry (evidence_id, sha256, source_id, subject, checkpoint_id), the loader
verifies the referenced artifact's digest against the actual bytes and then constructs
`TrustBinding` objects **in code**, sliced per case (only the current case's bindings
reach the factory — different cases never see each other's bindings). No manifest field
can create a binding: the manifest schema has no binding fields at all, and with
`extra="forbid"` (A4) any attempt is a validation error. The CLI has no trust-related
flags. Tampering test: editing the fixture collector's digest for one case makes that
case's external criteria abstain (`UNTRUSTED_EXTERNAL`) and is reported, never coerced.

## 5. `evaluate(manifest, verifier_factory, output_dir)` (requirement 5)

Sequential, single process. Procedure:

1. `output_dir` must not exist (A2); create it. Write `run.json` (`status: "running"`,
   §6 configuration, manifest hash, scheduled count).
2. Per case, in manifest order: load request via `safe_relative_path` + `parse_request`;
   load artifacts into `ArtifactStore`; slice fixture bindings; call
   `verifier_factory(case_id, request, artifacts, bindings)`; run `verify`; append one
   line to `cases.jsonl` (flush + fsync per line). Input errors from `parse_request`
   and backend errors from `verify` become case results (execution_status carries them)
   — every scheduled case yields exactly one line, and `scheduled = input_errors +
   backend_errors + ok` holds as an identity (asserted at aggregation and by RUN-02).
3. After all cases: load oracles (A1 files) with triple validation; build
   `CaseRecord`s; compute `compute_metrics` + `breakdowns` + pair metrics (NIT-011);
   attach run-level cost/RAM/throughput (§10); write `metrics.json`; update `run.json`
   (`status: "complete"`); write `COMPLETE` atomically (A3).
4. Interruption/infrastructure failure: best-effort update of `run.json`
   (`status: "incomplete"`, `scheduled`, `completed`, safe reason code), no marker; exit
   3 from the CLI. **No resume and no hidden retries**: a second call with the same
   output dir is refused outright; per-case backend errors are never retried (doc 06).

Exit code semantics (requirement 9): 0 complete run **regardless of model accuracy**;
2 invalid manifest/config (load failures, §1/§2 violations, missing `--model-dir` for
smolvlm, unknown backend); 3 infrastructure failure or incomplete run.

### 5a. Shared-backend mode (added at nit/shared-backend; doc 02 "loaded once
per backend, lazily on first visual use")

`evaluate(manifest, verifier_factory, output_dir, *, backend=None)`. With
`backend=` the caller hands over ONE Backend instance: the verifier factory
must wire it into every per-case Verifier (verifiers stay per-case because
trust bindings are per-case), and `evaluate()` closes it exactly once when
the run ends — complete, per-case error or infra abort alike. The run's
`preprocessing_hash` is read directly from the instance's descriptor (no
probe). With `backend=None` nothing changes: per-case verifiers, probe-based
hash, nothing closed here. The CLI's `--backend smolvlm --model-dir` path
constructs the backend once up front (failures keep the infra classification,
exit 3) and passes it through; the deterministic path still builds per case
and passes None. A backend error on one case is a per-case result and never
prevents the final close.

## 6. Run configuration fingerprint (requirement 6)

`run.json.configuration` records, each null-with-reason when unmeasured (doc 03
`Measurements.unavailable_reasons` pattern; hardware fields get a run-level reasons
map):

| Field | Source |
|---|---|
| package_version, source_revision | `nitelos.__version__`, git rev if available (null + reason outside a repo) |
| lock_hash | SHA-256 of `uv.lock` |
| model_file_manifest | the verified `nitelos-manifest.json` digest map + its own hash (smolvlm); null for deterministic with reason |
| prompt_hash, preprocessing_hash | from the backend's `BackendDescriptor` |
| policy_hash | `policy_hash(parse_policy(manifest.policy))` — cross-checked against the manifest's declared hash |
| device, dtype | from backend construction (smolvlm); null for deterministic |
| seeds | declared generation seed(s); inference is greedy/deterministic, recorded as such |
| dependency_versions | torch/transformers/numpy/scipy as loaded, else null |
| os, hardware | `platform.platform()`, CPU model if readable, else null + reason |
| generation_deterministic | declared boolean: greedy decode, no sampling; "do not promise cross-device bit equality" (doc 06) |

The fingerprint itself is SHA-256 over canonical JSON of the non-null subset; recorded
as `configuration_fingerprint` and required to match the manifest's declared value
(mismatch → exit 2: the manifest was frozen against a different configuration).

## 7. Report file schemas and RUN-01 rules (requirement 7)

`run.json` — run_id (uuid4), status, benchmark/split/view, manifest hash, scheduled/
completed/error counts, started/finished (UTC), §6 configuration block, backend
descriptor, exit_code. `cases.jsonl` — per line: run_id, case_id, group_id,
primary_scenario, execution_status, decision (null iff error), reason_codes, per-
criterion summary (id, state, basis, reason count, ref count), diagnostics subset
(elapsed_ms, model_invoked, criterion durations count), error code + safe message when
present, per-case request hash and trust fingerprint (for §8). **Privacy**: IDs,
counts, hashes, codes and timings only — no objective, criterion text, subject maps,
payload values or image bytes (doc 07; "requests/images are referenced, not copied").
`metrics.json` — serialized NIT-011 `MetricReport`s (overall + split/family/scope/
backend breakdowns + pair metrics + probability applicability) plus run-level
cost/RAM/throughput fields and invocation counts (model_invoked totals; unused-backend
counts for deterministic-only visual views, doc 06). Incomplete marker: absence of
`COMPLETE` (A3) plus `run.json.status`.

**RUN-01 validator rules (implemented in NIT-013)**: fail on (a) any missing field
among {run_id, status, benchmark ids, manifest hash, configuration fingerprint};
(b) `cases.jsonl` line count ≠ scheduled, or any case_id outside the manifest, or
duplicates; (c) decision non-null on an error row (or null on ok); (d) any oracle-only
token (declared list: `outcome_truth`, `evidence_sufficiency`, `expected`, `rationale`,
`annotators`, plus the sentinel strings planted by EVAL-04) appearing anywhere in the
report directory; (e) measurement fields non-null without a recorded method, or zero
where the schema demands null-or-measured (fabricated-measurement check); (f) status
"complete" without the `COMPLETE` marker or with count identities broken; (g) a
determinism re-run differing outside the whitelist. RUN-02 additionally verifies report
count identities per family (every scheduled family present) and the
scheduled = errors + ok invariant per split/view.

## 8. `compare_reports(run_a, run_b)` (requirement 8)

Loads two completed run directories. **Refuses** (structured error, not an exception
storm) when: case ID sets differ; per-case request hashes differ; artifact/evidence
manifest hashes differ (raw evidence bytes/order changed); policy hashes differ; trust
fingerprints differ (eligibility changed); `evidence_view` differs (different-evidence
analysis is explicitly a future version, doc 06). **Allows**: model/backend versions,
timings, memory. Preprocessing records are compared and **disclosed**: identical →
comparison labeled preprocessing-matched; differing → labeled with the delta list and
excluded from any preprocessing-controlled claim (doc 06). Output: per-case paired
outcomes feeding NIT-011 `paired_group_bootstrap`, plus a header recording all
fingerprint checks. Same-model re-runs (determinism checks) compare byte-identical
modulo the §3 whitelist.

## 9. CLI (requirement 9)

`python -m nitelos.evaluation run --manifest PATH --artifacts ROOT --output NEW_DIR
--backend {deterministic,smolvlm} [--model-dir PATH]` — argparse (doc 08: no Typer);
no trust, policy-file or binding flags (policy comes from the reviewed manifest);
`--model-dir` required for smolvlm (else exit 2) and rejected for deterministic;
unknown backend → exit 2. Output goes to a user-selected new directory only (doc 07).
A future `compare` subcommand exposes §8 with the same exit-code conventions.

## 10. Peak RSS and cold/warm (requirement 10)

The CLI process is the isolation boundary (one run per process). Peak RSS (A5):
`ru_maxrss` on Linux (×1024 → bytes), `GetProcessMemoryInfo` via ctypes on Windows,
null + reason otherwise; method string recorded in `metrics.json`. The backend marks
its first inference cold and subsequent ones warm (instance lifecycle); `CaseRecord
.cold` carries the flag so NIT-011's cold/warm/all-attempts latency split works
unchanged. Throughput = completed cases / end-to-end wall seconds (model load
included, labeled end-to-end). Cost: null with reason "no price source" (local runs;
doc 06).

## 11. Test plan (requirement 11; tests written first at NIT-012 time)

- **EVAL-01** every scheduled case has an output: a manifest mixing an ok case, an
  input-error case (bad request file) and a backend-error case (raising fake verifier)
  → three `cases.jsonl` lines with the right execution statuses; identity
  scheduled = errors + ok asserted.
- **EVAL-02** no overwrite/resume: existing output dir → refusal; injected
  infrastructure failure mid-loop → status incomplete + scheduled/completed counts + no
  COMPLETE marker; a second evaluate() into the same dir refused; per-case backend
  errors do NOT abort.
- **EVAL-03** compare: rejects changed artifact bytes (hash mismatch), changed policy,
  changed case set, different evidence_view; accepts a same-evidence re-run with a
  version-differing fake backend; differing preprocessing records disclosed.
- **EVAL-04** oracle isolation + determinism: sentinel-poisoned oracle never reaches
  the recording factory/backend/reports; two runs byte-identical modulo whitelist.
- **SEC-07** the §2 path table (Windows and Linux variants, junction/reparse tests
  skipif-guarded), inside-root symlink allowed, no-extraction assertion.
- Supporting: manifest limit tests (4 MiB+1, 10 000+1, count mismatch, duplicate IDs,
  policy-hash mismatch → exit 2); oracle-triple validation (error/null, ok/decision);
  fixture-collector tamper → UNTRUSTED_EXTERNAL; marker-file semantics.

## 12. Hand-off notes

NIT-013 consumes §7's RUN-01/02 rules and runs the actual frozen benchmarks via §9.
NIT-006 supplies the verifier; this design assumes its `verify(request, artifacts=…)`
shape and the carried-forward AR-1 requirement that typed requests re-check byte/depth
ceilings at verify() entry (the runner always builds requests via `parse_request`, but
the verifier's own gate must hold for direct users).
