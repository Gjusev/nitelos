# Implementation status — Nitelos v0.1

Orchestrator: Claude Code (Opus 5.5) main session. Implementers/reviewers: Claude Code subagent instances
launched via the Agent tool, one git worktree + branch per active task under `C:\Code Main\nitelos-wt\`.
Integration branch: `integration/v0.1`. States: pending, ready, running, review, blocked, done.
No secrets or sensitive evidence are stored here.

## Tasks

| Task | State | Owner | Branch / worktree | Depends | Tests / results | Deviations / blockers |
|---|---|---|---|---|---|---|
| NIT-001 Foundations | done | orchestrator | integration/v0.1 (`1b1f074`,`+fix`) | — | PKG-01..03 5/5 pass on Win+Linux × py3.12/3.13; ruff, format, mypy strict, wheel+sdist OK | Linux run found uv-not-on-PATH defect in packaging test; fixed via `UV` env var |
| NIT-002 Contracts | running | implementer-002 | nit/002-contracts | 001 | | |
| NIT-003 Evidence | pending | | | 002, AR-1 | | |
| NIT-004 Assertions | pending | | | 003 | | |
| NIT-005 Policy | pending | | | 004 | | |
| NIT-006 SDK | pending | | | 005 | | |
| NIT-007 Backend boundary | pending | | | 006, AR-2 | | |
| NIT-008 Local VLM | pending | | | 007 | | |
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
