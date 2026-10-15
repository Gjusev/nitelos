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
| Adapter wiring | DONE (500M history) | NIT-008 branch `nit/008-smolvlm`: lazy offline load, manifest verification, preprocessing records, token preflight, strict parser — mocked VLM-01..05 + SEC-01/08 green | the checkpoint swap below re-proves wiring with the new pin |
| Checkpoint | **SWAPPED, PENDING** (ADR-012) | ADR-012 (user-approved 2026-10-15, per the orchestrator's record; to be merged into this branch's decisions.md at integration): visual checkpoint moves from SmolVLM-500M-Instruct @ `a7da5b9…` to **SmolVLM2-2.2B-Instruct @ `482adb5…`** | record ADR-012 in decisions.md; update the pin in the adapter + docs (installation/backends pages already use gate-neutral wording) |
| G3 smoke (≥1 valid decisive label) | **PENDING** | 500M history: iteration record `b656dd3` ("G3 unreachable under every candidate") and D3 record `98dd2a1` (multimodal wiring works; collapse is format instruction-following — probe decoded `' UNKNOWN.'`, invalid under the strict parser). These records are retained as history. nitelos-14 is re-running the 12-case smoke with the 2.2B pin | the re-run report (12 cases, statuses, cold/warm, valid-label rate, memory method, platform, lock hash, model manifest digests, prompt hash). **Ship rule per ADR-012: if G3 still fails, the release candidate ships with G3 recorded as FAILED — the checklist row moves to DONE(failed-recorded), never to a softened claim** |
| Compatibility manifest | PENDING (with the smoke) | — | reviewed model file manifest (revision + per-file SHA-256 vs upstream LFS oids) attached to the smoke report |

## G4 — Reproducible evaluation

| Item | Status | Evidence today | Release-time proof |
|---|---|---|---|
| 120-case manifest, frozen 60-case split | DONE (data) | NIT-010: 4 manifests × 60, disjoint lineage groups, per-case oracles, review packets; freeze tool refuses while annotation is pending (verified exit 1, 60 pending) | manifests unchanged since the review-fix commit; `freeze.py` refusal still exits 1 |
| Human annotation (G4 gate) | **PENDING** (user-scheduled) | decisions.md "G4 human annotation": the user organizes two independent reviewers + adjudicator; packets prepared at NIT-010 | reviewer IDs + signed-off packets; then `freeze.py` final freeze (records `freeze.sha256`) |
| Complete reports, deterministic configuration | READY | NIT-012 runner + NIT-013 validator: deterministic dev.json run exits 0 (60/60 ok) on Windows and Linux; RUN-01/02 validate shape, identities, no oracle leakage | the release run (NIT-13 proper) into `reports/`: deterministic view over dev AND test splits, validated by `validate_run_report` |
| Local visual configuration reports | BLOCKED on G3 | — | if G3 passes: visual-view runs on both splits; if G3 is recorded failed: this row is recorded NOT-RUN with the G3 record — no fabricated visual numbers |
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
| Vulnerability audit | **AT-RELEASE** | — | `pip-audit` (or equivalent) against the release lock, run in the release workflow sketch (advisory DB network access disclosed per doc 12); record exceptions — zero unresolved high/critical reachable in shipped paths |

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
| REL-01 installed wheel runs full core conformance + demo | `uv build` → fresh `uv venv` → `uv pip install dist/*.whl` → run `tests/test_contract.py …` selection + `examples/quickstart.py` + `examples/demo_incomplete_form.py` from outside the repo with sockets denied. The DOC-01 fixture in `tests/test_examples.py` already proves the quickstart half; the release run extends the same pattern to the conformance selection | pattern proven (DOC-01); full run AT-RELEASE |
| REL-02 sdist independence | `uv build` sdist → fresh venv → `pip install nitelos-0.1.0.tar.gz` → import + quickstart; PKG-02 already asserts sdist contents (no weights/tests-only paths) | contents DONE; install run AT-RELEASE |
| REL-03 extras resolve + core-import lightness with local installed | `uv sync --extra eval` and `--extra local` resolve from the frozen lock; then `python -c "import nitelos"` asserts `torch/transformers/numpy/scipy` absent from `sys.modules` (the packaging import test pattern) | eval half DONE (statistics lazy-import tests); local half PENDING the NIT-008 merge — the assertion already exists as a pattern |
| REL-04 security/license inventory completeness | a small test asserting every distribution in the core/eval/local closures of `uv.lock` appears in `dependency-licenses.md` (parse `[[package]]` name/version; check the doc's tables). Sketched in release-workflow.md; land it as `tests/test_license_inventory.py` at release | **AT-RELEASE** (needs the final merged lock) |

## Open items blocking release (summary)

1. **G3**: checkpoint swap (ADR-012) + smoke re-run by nitelos-14; ship rule decided
   (failed-G3 ships as a recorded failure).
2. **G4**: human annotation (user-scheduled) → final freeze hash.
3. **G6**: vulnerability audit at release time (network-disclosed advisory scan).
4. **NIT-008 merge**: brings the adapter + local extra into integration; REL-03's
   local half and the adapter-facing doc statements re-verify after it.
5. Package name availability + publish authority recheck (maintainer action; doc 13 §1).
