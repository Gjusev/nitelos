# Implementation status — Nitelos v0.1

Orchestrator: Claude Code (Opus 5.5) main session. Implementers/reviewers: Claude Code subagent instances
launched via the Agent tool, one git worktree + branch per active task under `C:\Code Main\nitelos-wt\`.
Integration branch: `integration/v0.1`. States: pending, ready, running, review, blocked, done.
No secrets or sensitive evidence are stored here.

## Tasks

| Task | State | Owner | Branch / worktree | Depends | Tests / results | Deviations / blockers |
|---|---|---|---|---|---|---|
| NIT-001 Foundations | done | orchestrator | integration/v0.1 (`1b1f074`,`+fix`) | — | PKG-01..03 5/5 pass on Win+Linux × py3.12/3.13; ruff, format, mypy strict, wheel+sdist OK | Linux run found uv-not-on-PATH defect in packaging test; fixed via `UV` env var |
| NIT-002 Contracts | done (merged `3a04870`; isolation fix `06ce9dc` merged) | nitelos-69 | nit/002-contracts `2671d5f` | 001 | 59 contract tests; suite 64 passed Win py3.12, Linux py3.12/3.13; ruff/mypy clean (orchestrator re-run) | 10 interpretations listed by implementer; key AR-1 questions: byte limits only in parse_request, top-level `canonical_json` export |
| NIT-003 Evidence | done (merged) | nitelos-69 | nit/003-evidence `cf25f7b` | 002, AR-1 | 31+2 tests (EVD-01..04, SEC-05/06); Win 132 passed; Linux py3.12/3.13 131 passed + 1 platform skip | reviewer nitelos-0f APPROVE-WITH-CHANGES; F2 decoded-vs-header dims made required |
| NIT-004 Assertions | done (merged) | nitelos-69 | nit/004-assertions `d06767e` | 003 | 17 DET tests; Win 172 passed; Linux full-offline replay OK | reviewer nitelos-0f APPROVE-WITH-CHANGES (huge index fix) |
| NIT-005 Policy | done (merged) | nitelos-69 | nit/005-policy `42ef33a` | 004 | Win 246 passed; Linux 245 + 1 platform skip | reviewer nitelos-0f APPROVE-WITH-CHANGES (visual refs, eligible_evidence helper, immutable map) |
| NIT-006 SDK | done (merged) | nitelos-69 | nit/006-sdk `fc7e278` | 005 | Win 288 passed; Linux strict replay OK | AR-2 approved; ADR-011 nullable request_id; F1 race, F2 strict env, F3 limitation code |
| NIT-007 Backend boundary | review (reviewer nitelos-08, queued after NIT-010 fixes) | nitelos-3a | nit/007-backend-boundary `4e24012` | 006, AR-2, 009 | 26 BAK/contract tests; Win 333 passed; Linux 332 + 1 platform skip | rationale export deferred; deadline None until NIT-008 |
| NIT-008 Local VLM | delivered; G3 PASSED (2.2B); AR-3 review running | nitelos-14 | nit/008-smolvlm `f1140e3` | 007 | 11/11 valid, 10 decisive, strict parser, prompt v1; orchestrator re-ran real-model integration test (pass) | dev agreement 4/12, over-support bias recorded; torchvision+num2words added to local extra |
| NIT-009 Traces | done (merged) | nitelos-0f/08 | nit/009-traces `2d5d3be` | 006, AR-2 | Win 307 passed after merge; Linux strict replay OK | reviewer nitelos-3a APPROVE-WITH-CHANGES (naive as_of fix) |
| NIT-010 Fixtures | done (merged; human gate pending for final-test audit/freeze) | nitelos-f2 impl, nitelos-14 review | nit/010-fixtures `f93e4d8` | 003, 009 | full truth table re-verified independently; compositions structural; numerals removed | G4 human reviewers scheduled by user at the end |
| NIT-011 Metrics | done (merged) | nitelos-0f | nit/011-metrics + nit/011b-metrics `5ffd8e8` | 002, AR-1 | STAT 26 + MET 19 tests; reviews by nitelos-69 (A: approve-with-changes fixed; B: approve) | metrics numpy/scipy-free; Wilson endpoints exact |
| NIT-012 Runner | done (merged with review fixes `82021a2`: smolvlm wiring, collector exit-2, preprocessing fingerprint) | nitelos-f2 impl, nitelos-14 review | nit/012-runner → nit/012-review-fix | 006, 010, 011 | Win 569+1 skip+1 desel; Linux 567+3 skips+1 desel | |
| NIT-013 Evaluation | dev-split done+merged (deterministic 60/60 exact; visual 60/60, agreement 41/60, over-support recorded); FINAL runs pending AR-4 + G4 human gate | nitelos-14 impl, nitelos-f2 review | nit/013b-runs `94baa2e` | 008, 012 | preflight ruling applied; both dev-visual records kept | shared-backend runner mode assigned (nitelos-f2) before final runs |
| NIT-014 Docs/demo | done (merged `8f19a3e` after merge-time update) | nitelos-f2 impl, nitelos-14 review | nit/014-docs | 006, 009, 012 | Win 575+1+1desel; Linux 573+3+1desel; visual demo wired and gated | |
| NIT-015 Release audit | prep delivered+verified (`41bce6d`, Win 506+1 skip, Linux 504+3 skips); gates/final audit pending | nitelos-f2 | nit/015-release | 013, 014 | | gates table/NOTICE/license inventory/workflow sketch |

## Architectural reviews

| Review | State | Reviewer | Evidence |
|---|---|---|---|
| AR-1 contracts | done (approved with changes; fixes `2671d5f` verified) | nitelos-0f | see decisions.md; constructor-path RecursionError fix + snapshot caveat requested from nitelos-69 |
| AR-2 deterministic flow | done (approved; conditions verified 2026-10-15) | nitelos-0f | decisions.md AR-2 |
| AR-3 local integration | done (approved; NIT-008 merged) | nitelos-f2 (independent) | brief sent 2026-10-15 |
| AR-4 protocol freeze | pending | | |
| AR-5 release candidate | pending | | |

## Open orchestrator items

- DONE 2026-10-15: CI full-offline + packaging jobs added by nitelos-0f (`5eb6bbc`), replayed on WSL Ubuntu by orchestrator against integration incl. NIT-003: 131 passed + 1 platform skip, no eval skips, coverage 87% (diagnostic). GitHub Actions itself never executed (no push authorized).

## Gates G1–G8

All pending.

## Log

- 2026-10-14: planning baseline committed (`3fbcdf4`); NIT-001 completed by orchestrator.
- 2026-10-14: eval extra (numpy 2.5.4, scipy 1.18.1) added centrally (`de32fe3`).
- 2026-10-14: user instruction: orchestrator session only plans/orchestrates; work delegated to peer sessions.
- 2026-10-14: smoke-set fixtures delivered by nitelos-0f (`7ab6871`): 12 cases/14 images, 13 tests pass on Windows; orchestrator re-run on WSL Linux fails byte-identical regeneration (FreeType rendering differs). Fix requested: declare renderer platform and scope regeneration check to it (doc 06 DATA-04); justify UNKNOWN labels (slot 4 questioned).
- 2026-10-14: smoke-set fix `5843f80` re-verified (Win 13 passed; Linux 12 passed + 1 platform-scoped skip); slot 4 relabeled REFUTED with rationale; merged into integration/v0.1.
- 2026-10-14: NIT-011A review by nitelos-69: APPROVE-WITH-CHANGES. Required: ±inf replicate statistics leak NaN (screen with isfinite, regression test); replace circular CP oracle with independent literals. Sent to nitelos-0f to apply after AR-1.
- 2026-10-14: AR-1 APPROVE-WITH-CHANGES. Orchestrator adds requirement: bound depth on constructor path (RecursionError on 5,000-deep dict). Decisions recorded in decisions.md.
- 2026-10-14: NIT-011A fixes verified (39 passed) and merged into integration; full regression green.
- 2026-10-14: NIT-002 merged. Post-merge regression found order-dependent test (in-process `PIL not in sys.modules` broken by smoke tests importing Pillow) on Win+Linux; fix assigned to nitelos-69 (nit/002-test-isolation). NIT-003 (nitelos-69) and NIT-011B (nitelos-0f) started.
- 2026-10-14: isolation fix merged; integration green (Win 99 passed; Linux py3.12/3.13 98 passed + 1 platform skip).
- 2026-10-14: NIT-011B delivered (`236b868`) and verified. Confirmed float noise wilson_interval(0,3).low=5.55e-17; exact-endpoint fix assigned to nitelos-0f.
- 2026-10-14: NIT-011B Wilson fix verified (`5ffd8e8`, 122 passed). NIT-003 delivered; Linux portability failure found by orchestrator; reviews launched: 0f→NIT-003, 69→NIT-011B.
- 2026-10-15: NIT-003 merged after Win + Linux py3.12/3.13 verification.
- 2026-10-15: CI jobs merged; NIT-011B merged; integration regression green.
- 2026-10-15: NIT-010 design merged; NIT-004 delivered+verified, to review; NIT-005 started test-first on top of NIT-004 branch.
- 2026-10-15: NIT-004 merged (Win 172 passed; Linux full-offline replay OK).
- 2026-10-15: NIT-008 adapter design merged (A1–A7 accepted). NIT-005 delivered+verified, to review; NIT-006 started.
- 2026-10-15: NIT-005 merged. Orchestrator process defect found: merged NIT-008 design doc fails `ruff format --check` (Ruff formats Markdown code blocks); orchestrator's WSL replay script masked the failure (`&&` chain under `set -e`). Script fixed; doc fix assigned to nitelos-0f. Integration format check RED until merged.
- 2026-10-15: format fix merged with NIT-012 design (`18e16d0`); integration fully green on Win and Linux (strict replay script).
- 2026-10-15: NIT-006 delivered+verified; AR-2 started. User approved ADR-011 (nullable request_id on input_error). G4 human reviewers: user will organize later (G4 pending).
- 2026-10-15: AR-2 approved conditionally (F1 averify/close race, F2 strict env parsing, F3 record new limitation code, ADR-011 commit). NIT-009 started.
- 2026-10-15: NIT-005/006 merged after ADR-011 confirmation by nitelos-0f. NIT-009 delivered; NIT-010 started.
- 2026-10-15: all Claude Code sessions restarted. Orchestrator is now `nitelos-f3`; peers are `nitelos-08` and `nitelos-3a` (context status being confirmed). State at restart: NIT-007 WIP commit `6aebf3a` plus uncommitted deterministic.py edit; NIT-009 review not delivered; NIT-010 no commits.
- 2026-10-15: nitelos-08 is resumed nitelos-0f. NIT-010 delivered and verified (Win+Linux). nitelos-3a unresponsive (message possibly held for user approval); NIT-009/010/007 reviews queued for it. NIT-007 handed to nitelos-08.
- 2026-10-15: nitelos-3a is resumed nitelos-69. To preserve independence: 3a reviews NIT-009/010 then finishes its own NIT-007 WIP; nitelos-08 implements NIT-012 and later reviews NIT-007.
- 2026-10-15: NIT-009 merged. Incident: a peer ran WSL `uv` inside the main checkout (11:32), creating a root-owned Linux `.venv`; orchestrator rebuilt it; both peers told never to run in the main checkout.
- 2026-10-15: NIT-007 delivered+verified; NIT-008 adapter assigned to nitelos-3a.
- 2026-10-15: orchestrator session renamed again (now `nitelos-6b`); peers notified. NIT-010 review fixes verified by orchestrator: S11 truth=success 8/8; S06 visual evidence has no database observation; S07v1/S15 carry visual criteria; family truth table consistent; Win 443 passed, Linux 441 + 2 platform skips. Re-verification queued for nitelos-3a at new head `f93e4d8` (eol pinning).
- 2026-10-15: NIT-012 delivered and verified by orchestrator (Win+Linux+real CLI). NIT-010 eol follow-up f93e4d8 verified via fresh LF Linux checkout. Reviews queued for nitelos-3a.
- 2026-10-15: peers identified after rename: `nitelos-f2` = nitelos-08 (ex 0f), full context, all work committed; `nitelos-14` = nitelos-3a (ex 69), full context, mid-NIT-008 (mocked tests green, WSL local env synced, CPU smoke imminent). Assignments: 14 continues NIT-008 (NIT-012 review + NIT-010 re-verify queued after smoke report); f2 reviews NIT-007 then implements the RUN-01/02 report validator (NIT-013 part A).
- 2026-10-15: user decision — the G4 human reviewers come at the very end of all work. Final-test audit, freeze and final benchmark runs wait for them; everything else proceeds.
- 2026-10-15: NIT-013A verified. NIT-008 G3 attempt 1 failed (0/11 valid, all ' UNKNOWN.'); ruling: one pre-declared prompt iteration round (v2/v3 + D1/D2 diagnostics), then viability review if still 0.
- 2026-10-15: ADR-012 user-approved: checkpoint swap to SmolVLM2-2.2B-Instruct @482adb5. Weights provisioned by orchestrator; shard 2 corrupt on first download (hash mismatch caught by upstream-oid cross-check; sidecar regenerated after clean re-download). NIT-007 merged; NIT-014 verified; NIT-015 prep assigned.
- 2026-10-15: SmolVLM2-2.2B weights fully provisioned and digest-verified on Windows and WSL (shard-2 corruption caught and fixed via upstream-oid cross-check). 2.2B smoke green-lit for nitelos-14. NIT-015 prep verified.
- 2026-10-15: G3 PASSED with SmolVLM2-2.2B (11/11 valid, 10 decisive). Orchestrator re-ran the real-model integration test independently (pass). AR-3 review assigned to nitelos-f2; NIT-012 review brief sent to nitelos-14.
- 2026-10-15: AR-3 APPROVED; NIT-008 merged (integration 375 passed + 1 deselected; Linux replay OK). Next: NIT-012 fix chain 010→012→013 merges.
- 2026-10-15: NIT-010 re-verification APPROVE; merged (511+1 deselected Win; Linux replay OK).
- 2026-10-15: NIT-012+NIT-013A chain merged (integration 569 passed +1 skip +1 deselected; Linux replay OK).
- 2026-10-15: NIT-014 merged (integration 580 passed + 1 skip + 1 deselected; Linux replay OK). Remaining live: NIT-013B dev runs (nitelos-14), NIT-015 finalization.
- 2026-10-15: preflight fix reviewed APPROVE and merged with dev-split records (582 passed). Shared-backend runner mode assigned to nitelos-f2.
