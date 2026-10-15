# Release checklist — Nitelos v0.1.0 (NIT-015, AR-5 input)

Status legend: **DONE** (evidence exists and is linked), **PENDING** (a named gate must
close before release), **AT-RELEASE** (mechanical step executed during the release run
itself). Every claim below must remain true in the release report; nothing is inferred.

Artifact roots used below: `tests/` (test modules), `benchmarks/synthetic_v1/`,
`docs/implementation/` (decisions/status), `reports/` (NIT-013 outputs, created at run
time). The authoritative gate definitions are doc 09 §Gates; this table maps each gate
to its current evidence and its release-time proof.

## G1 — Contract

| Item | Status | Evidence today | Release-time proof |
|---|---|---|---|
| Conformance suite 100% | DONE | CON-01..04 (`tests/test_contract.py`), EVD (`test_evidence.py`), DET (`test_deterministic.py`), POL (`test_policy.py`), SDK/LIFE (`test_verifier.py`, `test_lifecycle.py`), BAK (`test_backend_contract.py`), TRC (`test_trace.py`) — all green in the full-suite runs recorded per task | `uv run --extra eval pytest -q` exit 0 on the release commit (Windows + Linux) |
| Schema snapshots stable | DONE | `tests/schemas/{request,result}.v1.json` guarded by `test_con02_schema_snapshots_match_generated`; ADR-011 regeneration recorded (decisions.md) | same test green; `git diff` empty over `tests/schemas/` since the ADR-011 commit |
| Legal result matrix | DONE | `(ok,success/failure/abstained)`, `(input_error,null)`, `(backend_error,null)` enforced in `VerificationResult` (NIT-002, AR-1) and exercised by CON-01 | CON-01 parametrization count unchanged (5 legal / 7 illegal pairs) |

## G2 — Trust/security

| Item | Status | Evidence today | Release-time proof |
|---|---|---|---|
| SEC negative cases | DONE | SEC-01..08 across `tests/test_security.py` (injection, trust forgery, secret/log/repr leakage, network denial, bombs/bounds, path traversal incl. UNC/junction via NIT-012's SEC-07) | full suite green with the conftest socket denial active (no skips except the platform-declared ones) |
| No false success from forged trust/refs | DONE | POL-04 substitution battery (NIT-005 review), AR-1/AR-2 end-to-end probes through `verify()`, BAK-02/03/04 output-forgery battery (NIT-007 review) | same suites green; no new `skip`/`xfail` added since AR-2 |
| No default network / raw logging | DONE | SEC-03/04; handler-less `nitelos` logger asserted in PKG tests; runner offline end-to-end (EVAL CLI runs) | packaging import test green; `grep -r "requests\|urllib\|socket.create_connection" src/` returns nothing outside conftest/tests |

## G3 — Executable local path

| Item | Status | Evidence today | Release-time proof |
|---|---|---|---|
| Adapter wiring | DONE | NIT-008 merged (adapter in `src/nitelos/backends/smolvlm.py` @ `37e4b8a`): lazy offline load, manifest verification, preprocessing records, token preflight, strict parser — mocked VLM-01..05 + SEC-01/08 green, re-proven with the 2.2B pin | wiring tests green on the release commit |
| Checkpoint | DONE (ADR-012) | ADR-012 (user-approved 2026-10-15, merged): pin is **SmolVLM2-2.2B-Instruct @ `482adb537c021c86670beed01cd58990d01e72e4`** in the adapter constants and every doc page; provenance in `docs/implementation/dependency-licenses.md` §Checkpoints; the 500M failure history is retained | pin unchanged in the release commit (AR-4 dossier records it as frozen) |
| G3 smoke (≥1 valid decisive label) | **DONE — PASSED** | NIT-008 phase B (decisions.md, 2026-10-15): 11/11 generations valid under the strict parser, 10 decisive SUPPORTED + 1 UNKNOWN abstention; records `benchmarks/smoke-run-2.2B.json` (sha256 `97482b00…`), `d3-2.2B-sanity.json` (`e96a449c…`) | the executability claim in the release notes cites this record **with the honest accuracy observation attached**: dev-label smoke agreement 4/12, format-compliant but over-supporting — dev-split agreement 41/60 (over-claim patterns in the NIT-013 methodology); no accuracy claim anywhere |
| Compatibility manifest | DONE (provenance) | per-file SHA-256 verification against upstream LFS oids is orchestrator-held outside the repo (ADR-012 impact note); the AR-4 freeze dossier records the pin, revision and this provenance statement | the release report attaches the final reviewed manifest for the shipped checkpoint |

## G4 — Reproducible evaluation

| Item | Status | Evidence today | Release-time proof |
|---|---|---|---|
| 120-case manifest, frozen 60-case split | DONE (data) | NIT-010: 4 manifests × 60, disjoint lineage groups, per-case oracles, review packets; freeze tool refuses while annotation is pending (verified exit 1, 60 pending) | manifests unchanged since the review-fix commit; `freeze.py` refusal still exits 1 |
| Human annotation (G4 gate) | **PENDING** (user-scheduled) | decisions.md "G4 human annotation": the user organizes two independent reviewers + adjudicator; packets prepared at NIT-010 | reviewer IDs + signed-off packets; then `freeze.py` final freeze (records `freeze.sha256`) |
| Complete reports, deterministic configuration | READY | NIT-012 runner + NIT-013 validator: deterministic dev.json run exits 0 (60/60 ok) on Windows and Linux; RUN-01/02 validate shape, identities, no oracle leakage | the release run (NIT-13 proper) into `reports/`: deterministic view over dev AND test splits, validated by `validate_run_report` |
| Local visual configuration reports | READY (pending G4 only) | dev-visual re-run on the fixed pipeline: 60/60 ok, 40 model invocations, RUN-01/02 validated (`reports/dev-split/dev-visual-smolvlm-fixed/`); the CLI now runs it directly (shared-backend mode, merged `d8c491a`) | visual-view final runs on the test split after the G4 sign-off, via the CLI commands in the AR-4 freeze dossier §4 |
| Evidence differences labeled; fingerprints valid | DONE (mechanism) | `compare_reports` fingerprint matching; per-run configuration fingerprints | the release report pack includes the fingerprints; the deterministic-vs-visual difference is labeled per doc 09 G4 note (no matched-model leaderboard claim) |

## G5 — Quality

| Item | Status | Evidence | Release-time proof |
|---|---|---|---|
| Core CI matrix (3.12/3.13 × Linux/Windows) | DONE | `.github/workflows/ci.yml` core job + full-offline + packaging jobs (infra/ci-jobs, merged; orchestrator-verified green incl. strict replay) | the release commit's CI run green |
| Lint/format/mypy | DONE | ruff check / format --check / strict mypy clean on every task branch (recorded per report) | same three commands green on the release commit |
| sdist/wheel validation | DONE | PKG-01..03 + REL mapping below | REL-01..04 table below |

## G6 — Rights and supply chain

| Item | Status | Evidence | Release-time proof |
|---|---|---|---|
| License inventory, core + extras + transitives | DONE (this task) | `docs/implementation/dependency-licenses.md` completed to release grade from the frozen locks (core closure, eval, local incl. torch/transformers transitives; ambiguous licenses flagged with release actions) | REL-04 completeness assertion (below) green against the release lock |
| Notices | DONE (this task) | `NOTICE` at repo root (Apache-2.0 header + third-party bootstrap) | NOTICE reviewed; wheel/sdist carry LICENSE (+ NOTICE per packaging config review) |
| Only authored fixtures redistributed | DONE | benchmarks/synthetic_v1 provenance record (DATA_CARD: original synthetic scenes, Apache-2.0, no PII/third-party assets); smoke set likewise; PKG tests forbid foreign payloads | PKG-02/03 green on the release build; DATA_CARD unchanged |
| Checkpoint rights: separate download only | DONE (statement) | dependency-licenses.md §Checkpoints: both pins' license/provenance/LFS-oid story, no redistribution | confirm no model files in any artifact (PKG tests already assert suffix bans) |
| Vulnerability audit | **AT-RELEASE** (workflow landed) | `.github/workflows/release-prep.yml` audit job: `uvx pip-audit@2.10.1` over the full exported lock, networked job disclosed per doc 12, findings warn (never auto-green) | the dispatched release-prep run's audit log attached to the release report; zero unresolved high/critical reachable in shipped paths, or recorded exceptions |

## G7 — Adoption documentation

| Item | Status | Evidence | Release-time proof |
|---|---|---|---|
| Fresh-wheel offline demo + quickstart | DONE | DOC-01 (`tests/test_examples.py`): wheel built → fresh venv → quickstart from outside the repo, sockets denied, cross-platform | DOC tests green on the release commit |
| Docs pages present, examples match contract | DONE | NIT-014: README first screen + 12 pages + demo trio; DOC-02/03/04 assertions | DOC tests green; docs re-read for statements invalidated by the G3 outcome (the wording was chosen to survive it) |

## G8 — Honest reporting

| Item | Status | Evidence | Release-time proof |
|---|---|---|---|
| Per-family results, errors/abstentions/coverage | READY (mechanism) | NIT-011 metrics + NIT-012 reports + NIT-013 validation | the release report pack includes aggregate AND per-family tables, error/abstention counts |
| Actual hardware/versions | READY | run.json configuration block (package/lock/policy fingerprints; OS; device/dtype null for deterministic) | visual runs (if any) record CPU model, memory method, model/prompt/lock hashes |
| No unsupported accuracy/calibration/real-world claims | DONE (docs side) | evaluation.md/performance.md state no-run-yet and no-calibration; no benchmark numbers anywhere in docs | release notes reviewed against the G3/G4 outcome; negative results published per doc 06 |
| No MK-SH-V claim | DONE | no MK-SH-V code/assets (PKG + benchmark provenance) | checklist assertion at release review |

## REL — release mechanics

| Test | Concrete command | Status |
|---|---|---|
| REL-01 installed wheel runs full core conformance + demo | `tests/test_release_conformance.py` (NIT-015): builds the wheel, installs ONLY it (+ locked pytest) into a fresh venv, runs the eight-file conformance selection and both offline demos from outside the repo with sockets denied; asserts nitelos resolves from the venv | **DONE** (test-linked; green Windows + Linux) |
| REL-02 sdist independence | same file: sdist contents checked (fixtures present; no weights/secrets/venv/benchmarks/reports), then `uv pip install --no-build-isolation` into a fresh venv (locked hatchling) → import + quickstart with sockets denied | **DONE** (test-linked; green Windows + Linux) |
| REL-03 extras resolve + core-import lightness with local installed | eval half: un-gated test (bare `import nitelos` pulls no numpy/scipy in this eval-synced env). local half: gated on `NITELOS_LOCAL_EXTRA_VENV` — run for real in the release-prep audit job and on a provisioned WSL venv; local-extra ABSENT gives the actionable DEPENDENCY_MISSING hint (tested against the bare wheel venv) | **DONE** (eval + error paths un-gated; local half gated-and-executed) |
| REL-04 security/license inventory completeness | `tests/test_license_inventory.py`: lock-vs-inventory — direct core/eval/local membership from the nitelos lock block, per-row version equality, completeness over all locked distributions, non-empty license cells, flagged rows carry release-action notes | **DONE** (test-linked against the merged lock `83a01dc0…`) |

## Open items blocking release (summary)

1. **G4**: human annotation (user-scheduled) — two reviewers + adjudicator sign
   the 60 final-test oracles → `freeze.py` final freeze → final runs (both
   views, test split) → G8 report pack.
2. **Release dispatch**: maintainer runs `release-prep` (manual dispatch; the
   audit job performs the networked pip-audit disclosed per doc 12).
3. Package name availability + publish authority recheck (maintainer action;
   doc 13 §1); publish stays behind the manual input + protected environment.

Resolved since the last revision: G3 (ADR-012 swap, smoke PASSED with the
over-support observation attached), the NIT-008 merge, and REL-01..04 (now
test-linked above). Version stays 0.1.0; no doc freeze changes needed beyond
the record corrections landed with the AR-4 dossier.
