# Nitelos planning index

> **Historical baseline.** This directory is the design baseline as approved on
> 2026-10-14 and is kept unchanged as the normative reference. The status line
> below describes that date. The implementation has since shipped: nitelos 0.1.0
> was published on 2026-10-16. For the current state, start at the
> [project README](../../README.md) and the [documentation index](../README.md);
> later decisions that refine this baseline are recorded in
> [implementation/decisions.md](../implementation/decisions.md).

**Status: planning complete; implementation not started.** Baseline 2026-10-14. This directory specifies the first release of Nitelos: **Verify the outcome, not the attempt.** No application source, models, installed dependencies or test results accompany this plan.

## Recommended reading order

For project review: 00 → 01 → 09 → 02 → 03 → 05 → 14. For GLM 5.3: read 11 and 10 after those foundations, then 04/07/08/12; read 06 before evaluation work. Start implementation at **NIT-001**, only in a separately authorized implementation phase. Do not start from the future roadmap.

| Document | Purpose / dependency |
|---|---|
| [00 Executive summary](00-executive-summary.md) | Vision, recommendation and independent value hypothesis |
| [01 Competitive landscape](01-competitive-landscape.md) | Primary-source research, overlap, licenses and maintenance evidence |
| [02 System architecture](02-system-architecture.md) | Modules, lifecycle, data flow and diagnostics; depends on 03/05 |
| [03 Domain model and API](03-domain-model-and-api.md) | Authoritative types, state semantics, bounds and examples |
| [04 Verification backends](04-verification-backends.md) | Capabilities, deterministic/local procedures, future adapters |
| [05 Evidence and policies](05-evidence-and-policies.md) | Authoritative eligibility, trust and aggregation algorithm |
| [06 Evaluation methodology](06-evaluation-methodology.md) | Data, metrics, calibration design and scientific integrity |
| [07 Security and privacy](07-security-and-privacy.md) | Trust boundaries, controls, tests and limitations |
| [08 Technology decisions](08-technology-decisions.md) | Stack, alternatives, dependency and license inventory |
| [09 MVP scope](09-mvp-scope.md) | Authoritative committed features/exclusions and G1–G8 |
| [10 Implementation roadmap](10-implementation-roadmap.md) | Fifteen tickets, dependency graph, acceptance and review points |
| [11 GLM implementation handoff](11-glm-implementation-handoff.md) | Standalone execution instructions and trace schema |
| [12 Testing and CI](12-testing-and-ci.md) | Test matrix, future verification commands and quality gates |
| [13 Open-source release](13-open-source-release.md) | Docs, demo, packaging, rights and maintainer release procedure |
| [14 Risks and ADRs](14-risks-and-adrs.md) | Ten decisions, risk register and adversarial self-review |
| [15 Future roadmap](15-future-roadmap.md) | Optional priorities; no committed implementation authorization |
| [16 Requirements traceability](16-requirements-traceability.md) | Requirement→task→test→gate mapping and completion audit |
| [17 v0.2 product and plan](17-v0.2-product-and-plan.md) | v0.2 proposal: features F1–F15, tasks NIT-016..035, gates G9–G12; not approved scope until G9 |

## Authority and conflict resolution

User-approved scope/instructions take precedence. Within this baseline: document 09 defines what ships; document 03 defines public schemas and errors; document 05 defines evidence/decision semantics; document 07 defines security boundaries; document 06 defines scientific metrics and dataset protocol; document 04 defines the chosen adapter behavior. These documents govern within their domains. Document 14 explains the decisions. The roadmap/handoff/testing documents operationalize them; summaries and pseudocode cannot override normative tables.

If two normative requirements genuinely conflict, GLM must record the contradiction and proposed resolution in an ADR amendment and request architectural approval before changing the contract. Do not silently choose the more convenient interpretation. Routine implementation details within the documented contract can be resolved autonomously. Cross-document links are relative for portability.

## Decisions to understand before coding

ADR-001 modular package; ADR-002 execution/decision separation; ADR-003 evidence list and host-bound external trust; ADR-004 fixed assertions/conjunction; ADR-005 advisory visual inference; ADR-006 experimental local SmolVLM; ADR-007 no calibrated confidence at launch; ADR-008 sync backend with bounded async facade; ADR-009 reuse existing ecosystems; ADR-010 authored reproducible fixtures before real-world claims.

## Scope of examples and research

All interface examples are non-executable specifications. Shell commands describe future implementation verification, not commands run during planning. Candidate dependency versions are observed metadata, not a tested lock. Research was current at access time and must be revalidated when locking release dependencies. Local model accuracy, latency and calibration have not been measured. MK-SH-V is future-only and has no released final checkpoint assumed by this plan.
