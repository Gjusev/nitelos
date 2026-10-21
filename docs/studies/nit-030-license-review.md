# NIT-030 step 1: tau2-bench license and terms review

Status: complete for the pre-G11 package. Date of review: 2026-10-21. Reviewer
session: nitelos-97 (this file) on branch `nit/030-tau2-protocol`. Hard scope
respected: documents only; no runs, no model calls, no trajectory downloads.
Every claim below names its exact source; the repository state is pinned to one
commit because upstream moved on the day of review.

## 1. Sources examined

| # | Source | URL | Access |
|---|---|---|---|
| S1 | Repository landing page | https://github.com/sierra-research/tau2-bench | 2026-10-21 |
| S2 | HEAD commit of default branch | https://api.github.com/repos/sierra-research/tau2-bench/commits/main | 2026-10-21 |
| S3 | Root LICENSE at the pin | https://raw.githubusercontent.com/sierra-research/tau2-bench/57e54143025bec219b5726884651c98eede202e2/LICENSE | 2026-10-21 |
| S4 | Repository root listing at the pin | https://api.github.com/repos/sierra-research/tau2-bench/contents/?ref=57e54143025bec219b5726884651c98eede202e2 | 2026-10-21 |
| S5 | data/ listing | .../contents/data?ref=57e5414... | 2026-10-21 |
| S6 | data/tau2/ listing | .../contents/data/tau2?ref=57e5414... | 2026-10-21 |
| S7 | data/tau2/domains/ listing | .../contents/data/tau2/domains?ref=57e5414... | 2026-10-21 |
| S8 | data/tau2/results/ and results/final/ listings | .../contents/data/tau2/results/final?ref=57e5414... | 2026-10-21 |
| S9 | data/tau2/results/final/README.md (716 bytes) | https://raw.githubusercontent.com/sierra-research/tau2-bench/57e54143025bec219b5726884651c98eede202e2/data/tau2/results/final/README.md | 2026-10-21 |
| S10 | README.md at the pin (citation section) | https://raw.githubusercontent.com/sierra-research/tau2-bench/57e54143025bec219b5726884651c98eede202e2/README.md | 2026-10-21 |
| S11 | arXiv 2606.09863 abstract page | https://arxiv.org/abs/2606.09863 | 2026-10-21 |

"at the pin" means the URL pins ref `57e54143025bec219b5726884651c98eede202e2`.

## 2. Repository identity and pin

- Repository `sierra-research/tau2-bench`, default branch `main` (S1, S2).
- Reviewed commit: `57e54143025bec219b5726884651c98eede202e2`, "Merge pull
  request #653 from sierra-research/soham/sandbox-minimal-env", commit date
  2026-10-21 (S2). This was the branch HEAD on the day of review.
- The README now brands the project as tau3-bench and adds voice domains; the
  tau2 text benchmark remains in place under `data/tau2/` (S1, S6). This study
  uses text tau2 only.
- Citations the README requests (S10): original tau-bench, arXiv 2406.12045;
  tau2-bench, "$\tau^2$-Bench: Evaluating Conversational Agents in a Dual-Control
  Environment" (Barres, Dong, Ray, Si, Narasimhan, 2025), arXiv 2506.07982;
  tau-Voice, arXiv 2603.13686. The README asks: "If you use a specific component
  of $\tau^3$-bench, please cite the corresponding paper below" (S1).

## 3. License of the repository

- The root LICENSE at the pin is the MIT License, copyright line:
  "Copyright (c) 2025 Sierra Research" (S3). Standard MIT permission and
  warranty text; no additions or riders.
- The GitHub About sidebar reports "MIT license" (S1).
- No NOTICE, LICENSE-data, TERMS, DATA_LICENSE or similar file exists at the
  repository root (S4), under `data/` (S5), `data/tau2/` (S6),
  `data/tau2/domains/` (S7) or `data/tau2/results/` (S8). One license file
  governs the repository.

## 4. Environments and task sets: terms

- Location at the pin: `data/tau2/domains/{airline, banking_knowledge, intake,
  mock, retail, telecom}` (S7), frozen benchmark sets and task subsets under
  `data/tau2/benchmarks/` and `data/tau2/task_subsets/` (S6), environment code
  under `src/` (S4).
- These ship inside the repository under the single MIT license with no separate
  terms found (S3 through S7). MIT grants use, copying, modification and
  redistribution of the Software and its associated documentation files,
  including these data files, subject to preserving the copyright and permission
  notice in copies or substantial portions.

## 5. Trajectories: terms (assessed separately, as the plan requires)

- Location at the pin: `data/tau2/results/final/` (S8). Contents: per-model
  result JSONs named `{agent-model}_{domain}_{strategy}_{user-simulator}_4trials.json`,
  a README.md (716 bytes) and a `figs/` directory. Shipped agent models:
  claude-3-7-sonnet-20250219, gpt-4.1-2025-04-14, gpt-4.1-mini-2025-04-14,
  o4-mini-2025-04-16; domains airline, retail, telecom, telecom-workflow; user
  simulator gpt-4.1-2025-04-14; 4 trials per task (S8).
- The `results/final/README.md` states (S9, paraphrase of the 716-byte file; the
  file is the authority): these are the trajectory results from the original
  tau2-bench paper, generated with the June 2025 task sets, prior to the v1.0.0
  fixes; airline has 29 tasks that differ from the current base tasks and retail
  has 114; telecom is unchanged and verifies; the files are kept purely as a
  historical record of the paper's numbers, are not leaderboard submissions, and
  are not referenced by any code or tests; results that verify against the 1.x
  task sets should be produced with v1.0.1 or later.
- License: the trajectories are in-repo and governed by the same MIT license;
  no separate terms were found (S3 through S8). Redistribution and derivative
  works are permitted with the notice preserved.

## 6. Derived verdicts and criteria: are they allowed?

Yes, on the terms found. Our study produces (a) criteria authored from task
specs, (b) verdict records per trajectory, (c) aggregate rates. All inputs from
upstream are MIT-licensed repository content; MIT expressly allows derivative
works and redistribution of substantial portions with the copyright and
permission notice included. No term found restricts publishing derived verdicts,
criteria or aggregates.

Obligations we adopt for anything distributed:

1. Include the MIT copyright and permission notice with any distributed copy or
   substantial portion of tau2-bench data (this includes criteria files and
   verdict records that embed task text).
2. Cite the tau2-bench paper, arXiv 2506.07982, as the README requests (S1,
   S10).

## 7. What stays uncertain

1. Model-provider terms. The shipped trajectories contain outputs of commercial
   models (OpenAI GPT-4.1 family, Anthropic Claude 3.7 Sonnet, used as recorded
   in S8). Sierra's MIT license speaks for the repository; it cannot speak for
   those providers' terms of service governing their models' outputs. Publishing
   aggregates, verdict records and criteria does not redistribute raw model
   outputs and avoids the question; if raw trajectories were ever shipped, the
   provider terms would need a separate check. Flagged for the maintainer.
2. Enumeration depth. Listings were verified at six directory levels and two
   READMEs and the LICENSE were read. Every individual data file deeper in the
   tree was NOT opened (hard scope: no trajectory downloads), so a differently
   licensed header inside an individual JSON would not have surfaced. The
   per-file walk is cheap and is pre-run item V6 in the protocol draft.
3. Moving upstream. The pin is the day's HEAD; the project merged PR #653 hours
   before review (S2). The pin is exact but the branch is live; mandatory
   re-verification at G11 freeze (protocol item V6).
4. tau3 scope drift. The README describes tau3 domains (voice, intake,
   banking_knowledge). Nothing in this study touches them; recorded so a future
   reader knows the review examined `data/tau2/` deliberately, not by oversight.
5. Voice assets. README: the shipped voice IDs are Sierra-internal (S1).
   Irrelevant to a text-only study; recorded for completeness.

## 8. arXiv 2606.09863, checked at the source (plan section 6, item 5)

Page https://arxiv.org/abs/2606.09863 (S11), accessed 2026-10-21.
"From Confident Closing to Silent Failure: Characterizing False Success in LLM
Agents". Author: Laksh Advani (single author). Submitted 1 Jun 2026; v1 is the
only version. cs.LG. Comments: "Accepted to FAGEN@ICML2026". The page shows a
CC BY 4.0 license icon. Abstract, verbatim:

> LLM agents can fail silently by asserting task completion when the environment
> state shows otherwise. We study this failure mode, false success, across two
> agent benchmarks: 9,876 tau2-bench trajectories from 8 model families and
> 1,879 AppWorld trajectories from 4 model families with text-independent ground
> truth. False success is common but varies by setting: 45--48% of failures in
> single-control tau2-bench domains, 3% in dual-control telecom, and 75.8% among
> AppWorld self-assessing coding-agent trajectories with explicit status claims.
> LLM judges fail reliably: no configuration across 5 judges, 5 prompt
> strategies, and full task specifications exceeds AUROC 0.65 on tau2-bench, and
> the same judges reach only 0.54 AUROC on AppWorld API-call traces. Judges rely
> on surface completion proxies -- confident closing language in tau2-bench and
> coarse action-sequence volume in AppWorld -- rather than verified state
> changes. Lightweight TF-IDF detectors achieve task-disjoint AUROC 0.83 on
> tau2-bench and 0.95 on AppWorld, recovering 4--8x more false successes than the
> best judge at the same flag rate with 3,300x lower latency. These results
> suggest that production monitoring should use lightweight, domain-calibrated
> detectors as triage signals rather than relying on LLM judges as the primary
> monitor for false success.

Figures carried into the protocol draft's pre-registered expectations: 3% of
failures are false successes in dual-control telecom (45--48% single-control);
no judge configuration across 5 judges and 5 prompt strategies exceeded AUROC
0.65 on tau2-bench; judges keyed on closing language rather than verified state.

## 9. Conclusion for G11

The text tau2 data this study needs (task specs, environment definitions,
shipped telecom trajectories) is MIT licensed at the pinned commit with no
separate terms found anywhere the review enumerated. Redistribution of derived
verdicts and criteria is permitted with notice preservation and paper citation.
Two items go to the maintainer with this package: (1) model-provider terms if
raw trajectories are ever redistributed, and (2) confirmation of the pin at the
G11 freeze, since upstream is actively merging.
