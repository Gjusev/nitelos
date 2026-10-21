# Comparison with related tools

Every claim below is traced to the research ledger
([docs/planning/01-competitive-landscape.md](planning/01-competitive-landscape.md),
accessed 2026-10-14). The ledger inspected documentation and repositories,
not reproduced performance; "not established" means the reviewed material
did not substantiate a capability, not that it is absent. Where the ledger
records an interpretation, this page repeats it; nothing here adds new
claims.

## What nitelos is

A compact Python SDK that verifies agent outcomes from evidence the host
collects: versioned criteria, deterministic assertions, digests and host
trust bindings, a strict abstention-first policy, and opt-in integrations.
It is independent of which agent ran the task.

## Closest neighbors

- Microsoft Universal Verifier / Fara webeval: the strongest functional
  overlap (goal/screenshot/action verification, standalone trajectory
  rescoring, ambiguity diagnostics), but a larger evaluation and agent
  ecosystem rather than a small SDK
  ([ledger](planning/01-competitive-landscape.md#direct-overlap)).
- AgentVerify: deterministic postconditions over external observations
  with receipts and signing; explicit external verification and provenance
  are therefore not novel in nitelos
  ([ledger](planning/01-competitive-landscape.md#agentverify)).
- LLM-as-a-Verifier: framework-independent trajectory verification with
  generative judges; calibrated binary outcome probabilities and externally
  trusted state semantics are not established there
  ([ledger](planning/01-competitive-landscape.md#llm-as-a-verifier)).
- AgentHorizon: a direct benchmark overlap (1,373 screenshot/action
  trajectories with instruction-swapped negatives); redistribution license
  unresolved ([ledger](planning/01-competitive-landscape.md#agenthorizon)).

## Benchmarks and harnesses nitelos reuses rather than rebuilds

BrowserGym, AgentLab, WebArena, VisualWebArena and OSWorld provide
environments, trajectories and task evaluators; Inspect AI provides the
evaluation harness we integrate with as a scorer; Langfuse provides
observability; Playwright provides page state we capture read-only. The
ledger's standing instructions apply: reuse, do not rebuild, and do not
call a subset of a benchmark a reproduction
([ledger](planning/01-competitive-landscape.md#benchmarks-and-agent-research-infrastructure),
[components](planning/01-competitive-landscape.md#evaluation-observability-and-collection-components)).

## What nitelos does NOT do

- It does not claim a novel verifier algorithm, formal proof of
  authenticity, or state\-of\-the\-art performance; the ledger's novelty
  assessment says no individual differentiator is established as novel
  ([ledger](planning/01-competitive-landscape.md#novelty-assessment-and-integration-decision)).
- It does not act as an agent, drive browsers (the Playwright helper
  captures, never navigates), or replace an experiment platform like
  AgentLab.
- It does not authenticate external completion by itself: a digest proves
  bytes, a trust binding proves the host collected them, nothing more
  ([evidence-limits.md](evidence-limits.md)).
- It does not calibrate LLM confidence; the v0.1 visual backend ships with
  a recorded over\-support limitation
  ([evaluation.md](evaluation.md)).
- It does not bundle third-party datasets or screenshots; the ledger's
  licensing dispositions govern any future evaluation data
  ([ledger](planning/01-competitive-landscape.md#data-access-and-licensing-disposition)).

If adoption feedback shows that an Inspect scorer or a Universal Verifier
adapter fully solves the intended use case, the plan is to prioritize that
integration and shrink nitelos further
([ledger](planning/01-competitive-landscape.md#novelty-assessment-and-integration-decision)).
