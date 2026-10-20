# nitelos documentation

Start with the [project README](../README.md) for what nitelos is and a first
runnable check. This index is organized by what you are trying to do.

## Use nitelos

| Task | Guide |
|---|---|
| Install the core, the `eval` extra or the experimental `local` extra | [installation.md](installation.md) |
| Run a complete first check and change it | [quickstart.md](quickstart.md) |
| Decide what "done" means and write criteria for it | [success-criteria.md](success-criteria.md) |
| Collect evidence from your own agent runner | [traces.md](traces.md), then [recipes/caller-collection.md](recipes/caller-collection.md) |
| Know what a digest or a trust binding can and cannot prove | [evidence-limits.md](evidence-limits.md) |
| Interpret `success`, `failure`, `abstained` and every error code | [errors-and-abstention.md](errors-and-abstention.md) |
| Use the async API, close a verifier, cancel safely | [lifecycle.md](lifecycle.md) |
| Configure the experimental visual backend | [backends.md](backends.md) |
| Write your own backend and pass the conformance rules | [custom-adapters.md](custom-adapters.md) |
| Measure latency and memory honestly | [performance.md](performance.md) |
| Review the security and privacy boundaries | [security-privacy.md](security-privacy.md) |
| Export one span per verification | [opentelemetry.md](opentelemetry.md) |

## Evaluate nitelos

| Task | Read |
|---|---|
| Understand the evaluation design and its limits | [evaluation.md](evaluation.md) |
| Read the v0.1 benchmark results, with every denominator | [reports/v0.1/SUMMARY.md](../reports/v0.1/SUMMARY.md) |
| Inspect the benchmark data, labels and audit records | [benchmarks/synthetic_v1/DATA_CARD.md](../benchmarks/synthetic_v1/DATA_CARD.md) |

## Contribute

| Task | Read |
|---|---|
| Set up a development environment and the PR workflow | [CONTRIBUTING.md](../CONTRIBUTING.md) |
| Report a vulnerability privately | [SECURITY.md](../SECURITY.md) |
| Follow the decisions made during implementation | [implementation/decisions.md](implementation/decisions.md) |
| Check release gates and how releases are cut | [implementation/release-checklist.md](implementation/release-checklist.md), [implementation/release-workflow.md](implementation/release-workflow.md) |

## Brand and launch film

The logo files, colors and type live in [assets/brand](assets/brand/) and are
specified in [videos/nitelos-launch/DESIGN.md](../videos/nitelos-launch/DESIGN.md),
together with the launch film sources and the record of what every on-screen
claim is based on ([claims.md](../videos/nitelos-launch/claims.md)).

## History

[planning/](planning/README.md) holds the original design baseline (2026-10-14),
kept unchanged as the normative reference for the wire contract. It predates the
implementation; where later work refined it, `implementation/decisions.md` says
so.
