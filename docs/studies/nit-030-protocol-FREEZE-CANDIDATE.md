# NIT-030 protocol FREEZE CANDIDATE: tau2-bench re-scoring with Nitelos

Status: freeze candidate for the maintainer's G11 signature. Nothing in this
file is a result: no runs were made, no model was called, no trajectory
payloads were opened for analysis. When signed, this document is the
pre-registration; any change after the first trajectory is scored requires a
new dated pre-registration note, not a silent edit.

## What the maintainer signs at G11

1. The pin: `sierra-research/tau2-bench` at commit
   `57e54143025bec219b5726884651c98eede202e2` (verified twice on 2026-10-21,
   unchanged between checks; re-checked at the moment of signature).
2. The subset: exactly the four telecom files named in section 2, every task
   present, every recorded trial. Airline and retail stay out (maintainer
   ruling 2026-10-21: separate pre-registration if ever).
3. Three verdicts per trajectory: agent self-report (rule P2), LLM judge,
   Nitelos over final environment state. The judge is glm-4.7 at temperature
   0.0, single call, prompt P1 (maintainer: accepted in principle).
4. The budget ceiling: the judge leg is estimated at USD 8.84 for the base
   split (arithmetic in section 8; labeled estimate, placeholders replaced at
   V1 before any spend). Paid spend approved in principle pending this figure.
5. The metrics of section 7, Wilson intervals, denominators always printed.
6. The negative-result commitment of section 9, including: raw trajectories
   and model outputs are never republished; only derived verdicts and
   criteria ship, with the tau2-bench citation (arXiv 2506.07982) and the
   MIT notice.

Companion: docs/studies/nit-030-license-review.md (terms, pin, and the arXiv
2606.09863 source check). Upstream prior art read before drafting (read-only):
`C:\Code Main\gate-calibrated`, which evaluated a gate on tau-bench retail,
pinned tau-bench at commit 59a200c, and published its negative results; its
"verify at start, do not assume" ledger style is adopted in section 10.

## 1. Study question

On tau2-bench telecom trajectories, how do three verdict sources compare
against the benchmark's environment-computed reward?

- V-self: the agent's self-report (what the agent's final message claims).
- V-judge: a single-call LLM judge over the transcript (the common practice
  baseline).
- V-nitelos: Nitelos, deterministic criteria authored from task specs only,
  evaluated over the final environment state.

Pre-registered, falsifiable expectations (sources: Advani 2026, arXiv
2606.09863, abstract verified at the source in the license review, section 8):

- E1 (self-report): false success exists but is rare in dual-control telecom;
  Advani measured 3% of failures as false successes there, versus 45--48% in
  single-control domains. We expect few events and therefore wide intervals.
  That is an honest outcome, not a failure of the study.
- E2 (judge): the judge will be weak. Advani found no configuration across 5
  judges and 5 prompt strategies exceeding AUROC 0.65 on tau2-bench, with
  judges keying on confident closing language. The judge leg is a baseline, not
  a gold standard.
- E3 (Nitelos, the product hypothesis): deterministic criteria over final
  environment state can classify trials with few false successes and few false
  failures, at the cost of abstentions where the state does not expose a
  required value. Falsified if Nitelos abstains on most trials, or most
  criteria turn out impossible to express, or error rates are indistinguishable
  from the judge. Any of those outcomes gets published.

## 2. Data and subset (fixed in advance)

Upstream pin: `sierra-research/tau2-bench` at commit
`57e54143025bec219b5726884651c98eede202e2` (license review, section 2;
re-checked later the same day, unchanged).

Selection rule, mechanical, no discretion at run time. Included: exactly these
four files under `data/tau2/results/final/`:

```
claude-3-7-sonnet-20250219_telecom_default_gpt-4.1-2025-04-14_4trials.json
gpt-4.1-2025-04-14_telecom_default_gpt-4.1-2025-04-14_4trials.json
gpt-4.1-mini-2025-04-14_telecom_base_gpt-4.1-2025-04-14_4trials.json
o4-mini-2025-04-16_telecom_default_gpt-4.1-2025-04-14_4trials.json
```

Units of analysis: every task present in each file, every recorded trial (4 per
task per model). The gpt-4.1-mini file ships with strategy "base" while the
others use "default"; recorded as observed upstream, not re-run.

Task counts at the pin (counted from the task spec files, see V3):
`data/tau2/domains/telecom/tasks.json` holds 2,285 unique task ids (the full
combinatorial set); `split_tasks.json` defines the named splits: base 114,
train 74, test 40, small 20, full 2285. The four included files are expected
to cover the base split (114 tasks), consistent with the upstream results
README's "telecom is unchanged and verifies". V1 confirms the actual per-file
task count structurally; any delta from 114 is recorded and the section 8 cost
is recomputed before spend, never after.

Exclusions, with reasons fixed now:

- Airline and retail shipped trajectories: the upstream results README states
  29 (airline) and 114 (retail) tasks differ from the current base task sets,
  so criteria could not be authored from the current tree against them.
  Maintainer ruling 2026-10-21: they stay out; any future use is a separate
  pre-registration.
- telecom-workflow and the no-user / no-user-op / op control variants: shipped
  for only two of the four models; a control-regime confound.
- Voice, multilingual, tau3 domains: out of scope for a text tau2 study.

Why telecom: it is the only domain whose shipped trajectories the upstream
README states are unchanged and verify against the current task set.

## 3. Reference (ground truth)

The benchmark's own environment-computed reward for each trial (the
final-state check native to tau2-bench). No human labels. This keeps the
reference reproducible offline and matches the "text-independent ground truth"
approach of Advani 2026.

## 4. The three verdicts

- V-self: parse rule P2 (appendix) over the agent's final message in the
  transcript. Three outcomes: claims-done, claims-not-done, no-claim. No-claim
  counts as abstain and is reported as such.
- V-judge (accepted in principle by the maintainer 2026-10-21): one call per
  trajectory, glm-4.7 at temperature 0.0, prompt P1 (appendix): task
  instruction plus full transcript, one binary question. Alternatives
  (claude-opus-5-5, gpt-5.2) may be substituted only by a dated note before
  the first call. Rationale for keeping the judge despite E2: it is the
  practice baseline the study compares against, and Advani's result is itself
  one of the things an independent replication speaks to.
- V-nitelos: the frozen criteria set (section 5) evaluated over final
  environment state evidence for the trial (section 6).

## 5. Criteria authorship (task specs only)

- The criteria author sees ONLY: the telecom task set at the pin (instruction,
  required actions and outputs, write constraints) and the schema of state the
  evidence exposes. No transcripts, no rewards, no self-reports, before or
  during authoring. Blinding is recorded by affirmance in the report.
- One criterion set per task: deterministic assertion criteria
  (subject, pointer, operator, expected value) over the final state. No LLM in
  the Nitelos leg anywhere.
- Hard-to-write ledger, per task exactly one of:
  `expressible` (clean deterministic criterion exists),
  `hard` (only a weaker or compound assertion is expressible),
  `impossible` (no deterministic pointer over available state).
  Each hard/impossible entry carries a one-line reason. The ledger is published
  in full; the hard+impossible rate is a reported metric with a Wilson
  interval. Hard tasks are never silently dropped; they are scored with the
  weaker criterion and the fact is visible in the ledger.
- Criteria freeze with the protocol at G11. After the first trajectory is
  scored, criteria are never edited; a discovered defect is recorded and the
  affected criteria are reported broken out, not repaired in place.

## 6. Evidence and replay rule for V-nitelos

- Preferred evidence: the final environment state as recorded in the shipped
  trajectory JSON (availability confirmed by pre-run item V1).
- Fallback: offline deterministic replay of the recorded actions through the
  pinned environment code to reconstruct the final state. Replay is accepted
  only if it reproduces the recorded reward for the trial (V2); trials where it
  does not are excluded, counted, and reported as evidence-unavailable.
- No network and no model calls anywhere in V-nitelos.

## 7. Metrics (fixed)

For each verdict source s in {self, judge, nitelos}, over all included trials
n (telecom, 4 agent models), with the benchmark reward as reference:

- False success count FS_s = #{s says success and reward = 0}; rate
  FSR_s = FS_s / #{s says success}.
- False failure count FF_s = #{s says failure and reward = 1}; rate
  FFR_s = FF_s / #{s says failure}.
- Abstention rate A_s = #{abstain_s} / n. Judge does not abstain (binary);
  V-self abstains on no-claim; V-nitelos abstains via MISSING_EVIDENCE and
  limitation codes.
- Nitelos abstention reason-code breakdown.
- Hard-criteria rate from the section 5 ledger, with interval.
- Pairwise agreement between the three sources, and a per-agent-model
  breakdown of every metric above.
- Every rate is printed next to its denominator n; no rate without its count.
- Intervals: Wilson 95% via `nitelos.evaluation.statistics.wilson_interval`
  (k, n).
- Cost: judge tokens in and out (counted regardless of payer) plus Nitelos
  wall-clock per trajectory; the machine spec is stated in the report.
- Runtime: end-to-end wall-clock per leg.

## 8. Cost (computed for the real N; labeled estimate)

Published price (source: Z.ai pricing page, https://docs.z.ai/guides/overview/pricing,
accessed 2026-10-21, USD per 1M tokens): GLM-4.7 input 0.6, output 2.2.

Judge calls, base split: 4 models x 4 trials x 114 tasks = 1,824 calls.

Token placeholders (per call, measured at V1 and replaced before spend):
8,000 input, 20 output.

- Input: 1,824 x 8,000 = 14,592,000 tokens -> 14.592M x USD 0.6 = USD 8.76
- Output: 1,824 x 20 = 36,480 tokens -> 0.03648M x USD 2.2 = USD 0.08
- Total estimate: USD 8.84

Ceiling if V1 finds the files cover more than the base split, at the full
2,285-task set (36,560 calls): input 292.48M -> USD 175.49, output 0.7312M ->
USD 1.61, total USD 177.10. The recomputed figure replaces this paragraph
before any spend; spend above the recomputed figure stops the judge leg and is
reported.

Everything except the judge leg (V-self, V-nitelos, replay, metrics) runs
offline at zero marginal cost.

## 9. Negative-result commitment

All numbers are published, including: Nitelos abstaining on most trials; most
criteria hard or impossible; zero false-success events in telecom (a real
possibility given E1's 3% of failures prior); the judge outperforming Nitelos.
No post-hoc domain switch: adding retail or airline is a separate follow-up
that requires its own frozen pre-registration. Raw trajectories and model
outputs are never republished (maintainer ruling 2026-10-21); only derived
verdicts and criteria ship, with the tau2-bench citation (arXiv 2506.07982)
and the preserved MIT notice. The gate-calibrated precedent (public negative
results on tau-bench retail) is the house style.

## 10. Pre-run verification items (verify at start, do not assume)

- V1 schema: field-level schema of the four included files at the pin; confirm
  what final-state evidence and task ids are present; count tasks per file
  structurally; measure transcript token distribution; replace the section 8
  placeholders. Done before any budget is committed.
- V2 replay: deterministic replay reproduces recorded rewards on a 20-trial
  pilot before any full run.
- V3 counts: DONE at the pin on 2026-10-21 from the task spec files:
  tasks.json 2,285 unique ids; split_tasks.json base 114, train 74, test 40,
  small 20, full 2285. The per-file trial counts remain a run-start check
  under V1.
- V4 P2 dry run: the self-report parse rule applied to 5 random trajectories
  per model for format confirmation only, before criteria authoring.
- V5 correspondence: telecom task files at the pin match the task ids in the
  shipped trajectories (independently verifies the upstream README's
  "telecom is unchanged" claim).
- V6 license re-pin: DONE twice on 2026-10-21 (unchanged, 57e5414); re-check
  once more at the G11 signature; per-file license headers of included files
  walked before the first run (closes license-review uncertainty 2).

## 11. Timeline (proposal, maintainer adjusts)

1. G11: maintainer signs this protocol (budget figure confirmed).
2. Same day, offline: V1 through V6 remaining items.
3. Criteria authoring, blinded (section 5), criteria file committed.
4. Judge leg, V-self and V-nitelos legs.
5. Metrics and report; criteria files, ledger and verdict records published
   under the license-review obligations (MIT notice plus arXiv 2506.07982
   citation).

## 12. Out of scope

Voice and multilingual sets, tau3 domains, AppWorld, any new agent runs, human
labels, republishing raw trajectories or model outputs, and any change of
subset after freeze.

## Appendix P1: judge prompt (frozen at G11 with the model choice)

```text
You are auditing an AI customer-service agent's completed session.

You will be given: (1) the task instruction the agent was assigned, and
(2) the full session transcript, including the agent's messages, its tool
calls and results, and the user's messages.

Question: did the agent complete the assigned task?

Judge only by what the transcript shows. Reply with exactly one word on the
last line: DONE or NOTDONE.

[task instruction]

[transcript]
```

Single call, temperature 0.0, no chain of thought requested, no retries except
transport errors (at most 2), responses that do not parse as DONE/NOTDONE are
recorded as judge-unparseable and counted separately (never silently dropped
or retried into compliance).

## Appendix P2: self-report parse rule (frozen at G11)

Applied to the agent's final assistant message in each transcript. Three
classes:

- claims-done: matches any fixed pattern from list L1 (for example
  "task is complete", "I have completed", "successfully completed", "all set",
  "is done"), and no pattern from L2.
- claims-not-done: matches any pattern from list L2 (for example "I was unable
  to", "I could not", "unfortunately", "cannot complete"), and no pattern from
  L1.
- no-claim: neither, or both. Counted as abstain.

L1 and L2 are literal, case-insensitive pattern lists finalized and committed
at G11, before any transcript is scored. The rule is deliberately mechanical;
its brittleness against the reward reference is one of the things the study
measures and reports.
