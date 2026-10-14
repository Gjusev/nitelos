# Implementation status — Nitelos v0.1

Orchestrator: Claude Code (Opus 5.5) main session. Implementers/reviewers: Claude Code subagent instances
launched via the Agent tool, one git worktree + branch per active task under `C:\Code Main\nitelos-wt\`.
Integration branch: `integration/v0.1`. States: pending, ready, running, review, blocked, done.
No secrets or sensitive evidence are stored here.

## Tasks

| Task | State | Owner | Branch / worktree | Depends | Tests / results | Deviations / blockers |
|---|---|---|---|---|---|---|
| NIT-001 Foundations | done | orchestrator | integration/v0.1 (`1b1f074`,`+fix`) | — | PKG-01..03 5/5 pass on Win+Linux × py3.12/3.13; ruff, format, mypy strict, wheel+sdist OK | Linux run found uv-not-on-PATH defect in packaging test; fixed via `UV` env var |
| NIT-002 Contracts | running | nitelos-69 | nit/002-contracts | 001 | | Earlier subagent attempt stopped by user before writing code; reassigned |
| NIT-003 Evidence | pending | | | 002, AR-1 | | |
| NIT-004 Assertions | pending | | | 003 | | |
| NIT-005 Policy | pending | | | 004 | | |
| NIT-006 SDK | pending | | | 005 | | |
| NIT-007 Backend boundary | pending | | | 006, AR-2 | | |
| NIT-008 Local VLM | pending (smoke-set subtask done+integrated `5843f80`; adapter awaits NIT-007) | nitelos-0f | nit/008-smoke-fixtures | 007 (adapter); fixtures independent | | Weights pre-provisioned outside repo, SHA-256 verified; WSL CPU probe: torch 2.14.1+cpu / transformers 5.19.0 load+generate OK; `AutoModelForVision2Seq` absent in TF5, use `AutoModelForImageTextToText`; probe output `' UNKNOWN.'` would be INVALID_OUTPUT under strict parser |
| NIT-009 Traces | pending | | | 006, AR-2 | | |
| NIT-010 Fixtures | pending | | | 003, 009 | | |
| NIT-011 Metrics | pending | | | 002, AR-1 | | |
| NIT-012 Runner | pending | | | 006, 010, 011 | | |
| NIT-013 Evaluation | pending | | | 008, 012, AR-4 | | |
| NIT-014 Docs/demo | pending | | | 006, 009, 012 | | |
| NIT-015 Release audit | pending | | | 013, 014 | | |

## Architectural reviews

| Review | State | Reviewer | Evidence |
|---|---|---|---|
| AR-1 contracts | pending | | |
| AR-2 deterministic flow | pending | | |
| AR-3 local integration | pending | | |
| AR-4 protocol freeze | pending | | |
| AR-5 release candidate | pending | | |

## Gates G1–G8

All pending.

## Log

- 2026-10-14: planning baseline committed (`3fbcdf4`); NIT-001 completed by orchestrator.
- 2026-10-14: eval extra (numpy 2.5.4, scipy 1.18.1) added centrally (`de32fe3`).
- 2026-10-14: user instruction: orchestrator session only plans/orchestrates; work delegated to peer sessions.
- 2026-10-14: smoke-set fixtures delivered by nitelos-0f (`7ab6871`): 12 cases/14 images, 13 tests pass on Windows; orchestrator re-run on WSL Linux fails byte-identical regeneration (FreeType rendering differs). Fix requested: declare renderer platform and scope regeneration check to it (doc 06 DATA-04); justify UNKNOWN labels (slot 4 questioned).
- 2026-10-14: smoke-set fix `5843f80` re-verified (Win 13 passed; Linux 12 passed + 1 platform-scoped skip); slot 4 relabeled REFUTED with rationale; merged into integration/v0.1.
