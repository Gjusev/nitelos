# NIT-030 report: tau2-bench telecom re-scoring with three verdict sources

Status: complete. Pre-registered protocol signed at G11 on 2026-10-21
([nit-030-protocol-FREEZE-CANDIDATE.md](nit-030-protocol-FREEZE-CANDIDATE.md),
committed at 33c232e before any run); terms and license review in
[nit-030-license-review.md](nit-030-license-review.md). Upstream pin:
`sierra-research/tau2-bench` at `57e54143025bec219b5726884651c98eede202e2`
(checked three times on 2026-10-21, unchanged). Subset: the four telecom
result files named in the protocol, 114 tasks x 4 trials x 4 agent models =
1,824 trajectories. Reference: the benchmark's environment-computed reward.
All rates below carry Wilson 95% intervals and their denominators, computed
with `nitelos.evaluation.statistics.wilson_interval`.

## What was measured

Three verdict sources per trajectory against the reference reward:

- V-self: the agent's final message, parsed by the frozen rule P2.
- V-judge: glm-4.7 at temperature 0.0, one call per trajectory, prompt P1
  verbatim (provider Z.ai, api.z.ai; actual spend below). 6 replies
  (0.3%) were judge-unparseable and are counted as such, never retried.
- V-nitelos: the nitelos `Verifier` scoring host-authored deterministic
  criteria over the recorded final-state evidence (see the caveat below).

## Results

Pooled over 1,824 trajectories; per-model detail in the table.

| Source | False-success rate | False-failure rate | Abstain |
|---|---|---|---|
| V-judge | 33/602 = 0.055 [0.039, 0.076] | 202/1,216 = 0.166 [0.146, 0.188] | 6 unparseable (0.3%) |
| V-self (frozen P2) | 5/37 = 0.135 [0.059, 0.280] | 0/1 = 0.000 [0.000, 0.793] | 1,786 no-claim (97.9%) |
| V-nitelos | 0/772 = 0.000 [0.000, 0.005] | 1/1,016 = 0.001 [0.000, 0.006] | 36/1,824 = 0.020 [0.014, 0.027] |

Judge accuracy against the reference (excluding its 6 unparseables):
1,583/1,818 = 0.871 [0.855, 0.885]. Pairwise agreement where all three
sources decided (n = 38, because V-self almost never claims): judge~nitelos
0.974, self~nitelos 0.868, self~judge 0.895.

Per model (FSR / FFR / abstain-or-unparseable):

| Model | judge FSR | judge FFR | judge unp. | self FS | nitelos FSR | nitelos FFR | nitelos abstain |
|---|---|---|---|---|---|---|---|
| claude-3-7-sonnet | 9/183 = 0.049 | 51/273 = 0.187 | 0 | 0/16 | 0/224 | 1/231 = 0.004 | 1/456 |
| gpt-4.1 | 11/135 = 0.081 | 32/318 = 0.101 | 3 | 5/7 = 0.714 | 0/156 | 0/297 | 3/456 |
| gpt-4.1-mini | 4/160 = 0.025 | 43/295 = 0.146 | 1 | 0/0 | 0/200 | 0/224 | 32/456 = 0.070 |
| o4-mini | 9/124 = 0.073 | 76/330 = 0.230 | 2 | 0/14 | 0/192 | 0/264 | 0/456 |

## Findings against the pre-registered expectations

- E1 (self-report rare in dual-control telecom): confirmed and stronger than
  expected. The frozen literal rule P2 found no claim in 97.9% of final
  messages; agents close conversationally or transfer to a human. When a
  claim does appear it is unreliable: 5 of gpt-4.1's 7 done-claims were
  false [0.359, 0.918], a small denominator reported as such. P2's
  brittleness was pre-registered as a measured outcome; no list tuning was
  performed after seeing data.
- E2 (judge weak): confirmed. The judge's dominant error is the false
  failure: it marks 202 of 1,216 NOTDONE verdicts wrong (16.6%), up to 23.0%
  for o4-mini, while its false-success rate is 5.5%. Advani 2026 (arXiv
  2606.09863, abstract verified at the source) found judges keyed on
  confident closing language and never exceeded AUROC 0.65 on tau2-bench;
  this run adds the complementary observation that a full-transcript binary
  judge also under-certifies completed work, which would block or slow
  correct agents if used as a gate.
- E3 (nitelos over final state): supported on this evidence path, with the
  caveat below. 0 false successes in 772 success verdicts, 1 false failure
  in 1,016, 36 abstentions (2.0%), all (INSUFFICIENT_EVIDENCE,
  MISSING_VALUE) on trials where the environment had not recorded every
  check (gpt-4.1-mini: 32, runs that aborted before checks completed).

## The E3 caveat (verbatim as accepted at G11)

The evidence is the environment's own recorded check flags, so this leg
measures "do host-authored deterministic criteria over recorded final state
reproduce the environment verdict" — near-perfectly, with a 2% abstention
rate. It does not by itself demonstrate capture of final state by an
independent host channel; that is what the v0.2 collectors do, and it was
out of scope for this pre-registered study.

## Criteria ledger

725 criteria authored from the task specs alone (516 required-action
criteria, 209 environment-assertion criteria), mechanically translated per
task, blinded as affirmed below. Every criterion was expressible: the base
telecom split carries no conversational (nl/communicate) requirements, so
the impossible count is zero, itself a finding: this benchmark subset is
fully state-checkable. The full ledger ships in
[nit-030-data/nit-030-criteria.json](nit-030-data/nit-030-criteria.json).

## Blinding affirmance

Before and during criteria authoring the author saw: file schemas, counts,
the embedded task specifications (the sanctioned input), aggregate reward
base rates (four percentages), and the P2 abstention counts. Eight final
message snippets were read for the P2 format check. No transcript content
beyond that, and no per-trial reward, was inspected before the criteria were
generated. Criteria were never edited after the first trajectory was scored.

## Cost and runtime

Actual spend, from API-reported token usage at the cited prices (USD 0.6/M
input, 2.2/M output; Z.ai pricing page, 2026-10-21): 7,213,559 input +
681,847 output = **USD 5.83**, plus ~USD 0.03 for the 14 single-call rate
probes whose responses were not recorded: **USD 5.86 total** against the
signed USD 8.84 ceiling. The pre-run estimate (USD 4.36) under-predicted
output tokens: glm-4.7 emits reasoning tokens, averaging ~374 output tokens
per call against the 20-token placeholder. Offline legs (V-self, V-nitelos,
metrics) ran at zero marginal cost; the full nitelos verification of 1,824
requests completed in under a minute on the study machine (Windows 11,
Python 3.13). Judge wall-clock: ~14.5 s per call sequential; the batch ran
at two workers.

## Reproducibility and publication rules

Raw trajectories and model outputs are NOT republished (maintainer ruling
2026-10-21); everything published here is derived: verdict records
([nit-030-verdicts.jsonl](nit-030-data/nit-030-verdicts.jsonl)), judge
records with token counts
([nit-030-judge.jsonl](nit-030-data/nit-030-judge.jsonl)), and the criteria
ledger. The judge file retains 7 error records from early rate-limit probes
(superseded by later successful calls for the same trajectories) as part of
the audit trail. tau2-bench is MIT (Copyright (c) 2025 Sierra Research);
this study carries the notice above and cites: Barres, Dong, Ray, Si,
Narasimhan, "tau2-bench: Evaluating Conversational Agents in a Dual-Control
Environment" (arXiv 2506.07982). The study scripts live outside the
repository in the maintainer's study artifacts directory and can be
committed on request.

## Limitations

- The single judge model (glm-4.7) and single prompt (P1) were the signed
  choices; no judge or prompt sweep was run.
- One run per protocol; no seed variance across judge calls is claimed
  (temperature 0.0, but provider-side nondeterminism is not excluded).
- V-self's 97.9% no-claim rate means its rates rest on 38 decided cases.
- The 6 unparseable judge replies are counted, not repaired; they are
  0.3% of calls.

## Negative-result commitment, honored

All numbers above are reported as measured, including the ones unfavorable
to the product's story: V-nitelos abstained on every aborted-check trial of
gpt-4.1-mini it could not verify, the near-agreement with the reference is
qualified by the E3 caveat, and the study's most striking effect (the
judge's false-failure mass) belongs to the baseline, not to nitelos. No
domain was added, no threshold moved, and no criterion edited after the
first trajectory was scored.
