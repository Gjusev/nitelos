# Testing and CI specification

Tests are to be implemented by GLM in the later execution phase. The planning session has run no application tests and installed nothing. Test IDs below are stable traceability identifiers; they may map to multiple parametrized pytest cases.

## Behavioral test matrix

| Family / owner | Required cases | Test layer |
|---|---|---|
| PKG / NIT-001 | Minimal import, wheel contents, supported Python, no extras or network | Packaging subprocess in clean environment |
| CON / NIT-002 | Five legal states, strict types/nulls, forbidden fields, duplicate JSON keys, safe validation, immutable copies | Unit + JSON Schema snapshots |
| EVD / NIT-003 | Exact hashes, mismatch/missing artifact, event dedup preservation, bbox bounds, MIME/dimension validation | Unit / decoder integration |
| DET / NIT-004 | Scalar equality/membership/presence, null vs missing, pointer escapes/arrays, booleans vs numbers | Pure unit tables |
| POL / NIT-005 | 27 conjunction combinations, contradictory facts, phase/time/subject/checkpoint, trust digest binding, model opt-in | Pure unit tables + adversarial cases |
| SDK / NIT-006 | Success/failure/abstention/error end to end, safe diagnostics, zero network | Integration without optional model |
| LIFE / NIT-006 | Busy, close, async cancel, worker completion, cooperative timeout limits | Controlled events/barriers, no flaky sleep-based assertions |
| BAK / NIT-007 | Capabilities, foreign IDs, invalid refs/boxes, score semantics, attempts to forge grounding | Backend conformance suite reusable by custom backends |
| VLM / NIT-008 | Actual processor inputs, image ordering, prompt stripping, exact label parsing, offline load, token preflight | Mock boundary tests plus separately gated real inference |
| TRC / NIT-009 | Order/tool linkage, unsupported formats, trace/direct parity, omitted-context diagnostics | Unit + SDK integration |
| DATA / NIT-010 | Scenario/count coverage, split lineage, provenance/license, independent oracle, render reproducibility | Data validation |
| MET / STAT / NIT-011 | Hand-derived rates, undefined cases, all abstain/errors, score target, uncertainty and clustered pairs | Numerical unit tests |
| EVAL / NIT-012 | Complete denominator, no label leakage, no overwrite/resume, error persistence, comparison fingerprints | Filesystem integration |
| RUN / NIT-013 | Real report count/version/hash validity, negative-result completeness | Artifact/report validation |
| DOC / NIT-014 | Installed-wheel quickstart/demo, scope labels, abstention/error handling | Executable example tests |
| REL / NIT-015 | Clean wheel/sdist, extras isolation, notices, release workflow permission | Release audit |

Security IDs: SEC-01 injection content cannot grant actions/authority; SEC-02 trust forgery; SEC-03 secret/log/repr leakage; SEC-04 no network; SEC-05 image bombs/malformed images; SEC-06 size/depth bounds; SEC-07 path traversal/escaping links; SEC-08 safe model loading. Map these to the responsible task and shared `tests/test_security.py`; no separate late security retrofit.

## Mocking principles

Fake backends emit valid states and deliberately malformed structures. Assert what the engine does with them, not the fake's behavior. Processor/model fakes capture image order, kwargs, token boundaries and output lengths; validate missing/extra outputs. Never use fake VLM results to support model accuracy claims. Real-model tests remain separate from ordinary CI.

Mock wall clock/timers and use thread events for deadlines/cancellation; never assert exact elapsed milliseconds in unit tests. Accept positive real duration and stable field presence. Block network at the socket boundary in ordinary tests using a reviewed test fixture or pytest-socket; its exact package/license must be added to the dev inventory if selected. Also run the core smoke job with network disabled after dependencies are provisioned. No hidden model cache dependency in unit tests.

## Commands (future implementation, not executed during planning)

Core developer path, after approved dependency installation:

```text
uv sync --frozen --group dev
uv run pytest -m "not local_model and not paid_api" -q
uv run ruff check .
uv run ruff format --check .
uv run mypy src/nitelos
uv build
```

One-command ordinary test execution is `uv run pytest -m "not local_model and not paid_api" -q`. Configure default markers so plain `uv run pytest` also excludes live integrations. Unknown markers fail. Eval tests skip only if explicitly running a core-only environment; the full CI job installs `--extra eval` and requires them.

```text
uv sync --frozen --group dev --extra eval
uv run pytest -m "not local_model and not paid_api" --cov=nitelos --cov-branch
uv run python -m nitelos.evaluation run --manifest benchmarks/synthetic_v1/dev.json --artifacts benchmarks/synthetic_v1 --output reports/dev-new --backend deterministic
```

The synthetic benchmark has assertion and visual evidence views. The `dev.json` command above selects the assertion view; provide separate `dev-visual.json`, `test.json`, `test-visual.json` manifests with shared underlying case IDs and explicitly different criteria/view fingerprints. Counts are 60 cases per split/view, 120 unique cases. No deterministic backend is expected to handle visual criteria. The final report joins view results only for scenario diagnostics, never a matched accuracy ranking.

Real local integration requires manually pre-provisioned reviewed weights and environment flags `NITELOS_RUN_LOCAL=1` and `NITELOS_MODEL_DIR` pointing to a pinned directory. Tests check both and otherwise skip with a precise reason. They must not download on missing files. Shell-specific syntax is documented for PowerShell and POSIX at implementation time; do not embed secrets in command history.

```text
uv sync --frozen --group dev --extra local --extra eval
uv run pytest -m local_model tests/integration/test_local_model.py -q
uv run python -m nitelos.evaluation run --manifest benchmarks/synthetic_v1/test-visual.json --artifacts benchmarks/synthetic_v1 --output reports/final-visual-new --backend smolvlm --model-dir PREPROVISIONED_PATH
```

These commands consume final data only after AR-4. Exact local platform/wheel source is recorded in NIT-008. Paid API tests are reserved markers only; v0.1 ships no paid adapter or paid test requirement. Later they require a separate explicit opt-in, credentials and bounded spend, never fork-PR secrets.

## CI jobs and merge gates

| Job | Matrix and trigger | Required checks |
|---|---|---|
| Core | Linux + Windows × Python 3.12/3.13, every PR | Frozen core/dev deps, no extras, tests/import, path tests |
| Full offline | Linux Python 3.12, every PR | Eval extra, all offline test families, strict lint/type/format |
| Packaging | Linux Python 3.12, every PR/release | Wheel/sdist build, clean install, example run, contents/license check |
| Local model | Linux CPU Python 3.12, manual/protected release candidate | Opt-in actual inference from pre-provisioned pinned cache; no untrusted fork execution with secrets |
| Supply chain | Protected scheduled/release workflow | Dependency vulnerability/license audit; advisory DB network disclosed |
| Publish preparation | Protected release candidate | G1–G8 evidence complete, immutable artifacts, minimal read permissions |

Pin GitHub Actions to reviewed commit SHAs; use least-privilege permissions and no untrusted PR code in a privileged `pull_request_target` execution. Dependency cache keys include lock/platform/Python; never cache credentials or screenshots from users. Artifact retention defaults to 14 days for CI logs/test reports; only reviewed synthetic data can be uploaded. Release publishing, if later authorized, uses trusted publishing and a protected environment, not a long-lived repository token.

Merge gates: task acceptance tests, dependency regressions, lint/format/type checks, no unexplained contract snapshot diff, no unrelated scope changes, required architectural review complete. Target >=90% branch coverage for policy and result/error handling, >=85% for remaining core as a diagnostic target; missing critical negative behavior blocks merge even at 100%. Optional model/library internals are not measured as project coverage. Do not manufacture tests merely to cross a percentage.

## Release verification

Run the full matrix once on the release candidate commit and reuse those artifacts; repeat only affected checks after new changes. Validate a clean wheel install, offline demo, actual local integration, report schemas and all gates. Audit exact resolved distributions and advisories; record exceptions and reasons rather than claiming scans prove safety. No unresolved high/critical reachable issue is permitted. A final-test performance weakness is reported, not fixed through undeclared tuning.
