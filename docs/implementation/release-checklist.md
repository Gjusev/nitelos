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
| Human annotation (G4 gate) | **DONE — agent-audited (ADR-013)** | two independent AI reviewers (nitelos-14; fresh no-context agent) + orchestrator adjudication; audit records `benchmarks/synthetic_v1/audit/`; 2 adjudicated label changes applied (S07 subject_mismatch → unknown); sign-off fields in all 60 final-test oracles (`agent_audited_2026-10-15`); binding no-human-audit label on the data card and every downstream artifact. **Human annotation review remains a precondition for any publication.** | final freeze sealed: `accf8f46de2fa9be99aa31c0fe367593bbb5697cb1dd1f28fe64e38a89d7f185` (delta vs provisional = the adjudication edits, expected) |
| Complete reports, deterministic configuration | **DONE** | four final runs on the sealed tree (2026-10-15, WSL CPU): deterministic dev+test 60/60 ok each, RUN-01/02 validated, artifacts in `reports/v0.1/` | reports stand as the sealed-tree record; nitelos-14 independent verification pending |
| Local visual configuration reports | **DONE** | visual dev+test final runs on the sealed tree: 60/60 ok each, 40 invocations per run, preprocessing hash recorded (probe fix confirmed live), RUN-01/02 validated (`reports/v0.1/*-visual-smolvlm/`) | same as above |
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
| Per-family results, errors/abstentions/coverage | **DONE** | `reports/v0.1/SUMMARY.md` + four `*-families.json` tables: aggregate and per-family results with denominators always shown; zero input/backend errors in all four runs | nitelos-14 verification, then AR-5 |
| Actual hardware/versions | **DONE** | run.json records in `reports/v0.1/` (package 0.1.0, lock `83a01dc0…`, policy hashes, prompt/preprocessing hashes `08fde1e3…`/`c7b4c1d1…`, ru_maxrss method; WSL Ubuntu CPU, torch 2.14.1+cpu / transformers 5.19.0 per the run environment) | same |
| No unsupported accuracy/calibration/real-world claims | **DONE** | docs carry only the pointer to `reports/v0.1/SUMMARY.md`; SUMMARY states the synthetic/no-real-world-generalization boundary explicitly and carries the ADR-013 label; negative results (over-support) published as headline limitations | release notes cite SUMMARY only |
| No MK-SH-V claim | DONE | no MK-SH-V code/assets (PKG + benchmark provenance) | checklist assertion at release review |

## REL — release mechanics

| Test | Concrete command | Status |
|---|---|---|
| REL-01 installed wheel runs full core conformance + demo | `tests/test_release_conformance.py` (NIT-015): builds the wheel, installs ONLY it (+ locked pytest) into a fresh venv, runs the eight-file conformance selection and both offline demos from outside the repo with sockets denied; asserts nitelos resolves from the venv | **DONE** (test-linked; green Windows + Linux) |
| REL-02 sdist independence | same file: sdist contents checked (fixtures present; no weights/secrets/venv/benchmarks/reports), then `uv pip install --no-build-isolation` into a fresh venv (locked hatchling) → import + quickstart with sockets denied | **DONE** (test-linked; green Windows + Linux) |
| REL-03 extras resolve + core-import lightness with local installed | eval half: un-gated test (bare `import nitelos` pulls no numpy/scipy in this eval-synced env). local half: gated on `NITELOS_LOCAL_EXTRA_VENV` — run for real in the release-prep audit job and on a provisioned WSL venv; local-extra ABSENT gives the actionable DEPENDENCY_MISSING hint (tested against the bare wheel venv) | **DONE** (eval + error paths un-gated; local half gated-and-executed) |
| REL-04 security/license inventory completeness | `tests/test_license_inventory.py`: lock-vs-inventory — direct core/eval/local membership from the nitelos lock block, per-row version equality, completeness over all locked distributions, non-empty license cells, flagged rows carry release-action notes | **DONE** (test-linked against the merged lock `83a01dc0…`) |

## Open items blocking release (summary)

1. Maintainer publication authority: package name availability + publish
   decision (doc 13 §1). The publish path itself is landed and gated
   (release-prep manual dispatch + protected environment; no secrets in repo).
   Per ADR-013, human annotation review remains a precondition for any
   publication — the agent-audited labels are a release-CANDIDATE basis.

Resolved: G3 (ADR-012, smoke PASSED, over-support attached), G4 (agent-audited
per ADR-013, freeze sealed `accf8f46…`), the four final runs + RUN-01/02
validation (`reports/v0.1/`), G8 reporting (SUMMARY + family tables), REL-01..04
(test-linked). Version stays 0.1.0. Next: nitelos-14's independent report
verification, then AR-5.
