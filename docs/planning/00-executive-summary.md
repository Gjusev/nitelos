# Nitelos: executive summary

Planning baseline: 2026-10-14. Status: specification, not implemented. Target: Apache-2.0, Python package `nitelos`, proposed repository `Gjusev/nitelos`.

**Verify the outcome, not the attempt.**

Nitelos is a model-agnostic Python library for checking explicitly stated agent success criteria against supplied evidence. Its users are agent developers, computer-use researchers, evaluation engineers, and reliability teams. An agent's successful tool call or confident summary does not establish that the objective was achieved.

The name is inspired by Tarifit *nican* and Greek *telos*. This is brand inspiration, not a linguistic authenticity claim. No model name belongs in the project's technical identity.

## Recommendation

Build a modular, single-process package with strict request/result schemas, bounded evidence loading, deterministic JSON assertions, an optional local SmolVLM-500M adapter, a policy evaluator, and a small offline evaluation runner. The Python SDK is the sole product interface in v0.1; an evaluation module command is an engineering utility, not a general CLI. There is no server, database, browser lifecycle manager, or dashboard.

Require an objective and one or more explicit criteria. A valid request with absent evidence abstains. Corrupt supplied evidence is an input error. Criteria specify their evidence scope: observed interface state, visual appearance, behavioral execution, or externally confirmed state. Every result is relative to those criteria and the declared checkpoint; it is never an unrestricted claim about the world.

Represent execution status (`ok`, `input_error`, `backend_error`) independently of decision (`success`, `failure`, `abstained`, or null on errors). Do not turn timeouts into task failures. No boolean convenience result may erase these distinctions.

Deterministic assertions evaluate immutable supplied JSON values. They do not execute user expressions or query databases. A trusted host can bind a particular external artifact digest to an authorized source and subject in runtime configuration. JSON claiming to be trusted is insufficient. Visual inferences require explicit policy opt-in, remain marked `model_inferred`, and cannot satisfy external criteria.

## What is distinctive—and what is not

Outcome verification, trajectory judging, counterfactual evaluation, and evidence receipts already exist. AgentHorizon and CUAVerifierBench evaluate judges; Microsoft's Universal Verifier separates process and outcome; AgentVerify checks system-of-record postconditions; Inspect supports custom scorers. See [the research ledger](01-competitive-landscape.md).

The defensible contribution is a small, reusable Python contract that combines explicit evidence scope, provenance limitations, conservative missing-evidence semantics, independent policy, and transparent evaluation accounting. This is an engineering integration hypothesis, not an established research novelty or performance advantage. Validate it with two external developers integrating the SDK without changing their agent orchestrators; treat feedback as adoption evidence, not a release blocker.

## Committed v0.1

- Strict typed contracts and JSON serialization, sync verification plus async facade, explicit instance-based custom backends.
- Equality, membership, and existence assertions on structured observations; no HTML query engine.
- PNG/JPEG screenshots and a bounded optional action/tool trace; external evidence only from caller-supplied snapshots.
- Optional local image inference with pinned model revision, no paid API, no training, no automatic downloads.
- Explicit abstention, evidence references, contradiction handling, null unavailable measurements, safe diagnostics.
- Fifteen scenario families, deterministic fixtures, error-aware metrics, an evaluation manifest and full per-case output.
- Tests, CI, packaging, documented offline demo, license inventory, and an honest measured local-backend report.

Defer hosted adapters, Playwright collection helper, calibration fitting and enforcement, REST, automatic state collectors, ensembles, large trajectory processing, visual localization, and MK-SH-V integration. Interfaces reserve score semantics but v0.1 ships no calibrated confidence claim.

## Release posture

The deterministic path is the reliable baseline; the VLM path is experimental. No universal accuracy floor is invented. Release requires all contract/safety fixtures passing, a real pinned local inference run, valid and invalid model-output accounting, reproducible benchmark outputs, and full disclosure of observed weaknesses. A backend that never produces a valid decision does not pass the executable-adapter gate. Statistical reliability claims require separately designed and adequately powered evidence.

MK-SH-V has no final released checkpoint. Nitelos neither depends on it nor accesses its experiments or final test data. A future adapter uses the same protocol after weights, license, interface, and isolated evaluation data become available.

## First implementation action

GLM 5.3 reads the [index](README.md), [handoff](11-glm-implementation-handoff.md), [contract](03-domain-model-and-api.md), [policies](05-evidence-and-policies.md), and [task roadmap](10-implementation-roadmap.md), then executes **NIT-001 only**. Implementation is a separately authorized phase. This planning session stops after documentation.
