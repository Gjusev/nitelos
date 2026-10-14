# NIT-010 design specification — synthetic outcome benchmark v1

Status: **design only, no code**. This document fixes the design of the 120-case authored
benchmark (`nitelos-synthetic-v1`) so that the future NIT-010 implementation task executes
without further design decisions. NIT-010 depends on NIT-009 (traces) and NIT-006; this
spec exists now because design and annotation are the slow, reviewable parts of the
critical path (doc 10 estimates complexity L "annotation effort, not just code").

Normative sources: doc 06 (scenario matrix, ground truth, splits/leakage, manifest/runner
contract, views), doc 03 (request/evidence/criteria — the design is expressed in the merged
NIT-002/NIT-003 contracts), doc 05 (required examples, provenance), doc 04 (smoke set —
explicitly NOT reused), doc 07 (privacy), doc 13 (rights), doc 16 (traceability MVP-09),
doc 10 (NIT-010/012/013 acceptance).

## 1. Flagged ambiguities and chosen readings (veto points, not silent resolutions)

- **A1 — "four development and four final-test cases from different template/entity groups"
  (doc 06 §2).** Reading adopted: **8 disjoint lineage groups per family**; groups L1–L4
  render the development cases, groups L5–L8 the final-test cases. The weaker reading
  (4 groups each contributing one dev + one test case) would let prompt/engineering
  iteration on dev leak template familiarity into final-test. Cost: 120 distinct template
  variants instead of 60. If the orchestrator prefers the weaker reading, only §4's group
  assignment changes.
- **A2 — "Both views are scheduled on all 120 cases, split 60/60" (doc 06 §2).** Reading
  adopted: four manifests of 60 cases each (`dev`, `dev-visual`, `test`, `test-visual`),
  matching doc 12's file list and the 60-per-split/view counts. Every case appears in
  exactly one assertion-view manifest and one visual-view manifest per split.
- **A3 — S14 "mock fabricated ref" (doc 06 matrix).** Reading adopted: injecting a
  fabricated evidence reference requires a **mock backend**, which belongs to the NIT-007
  contract suite (BAK family), not to a frozen benchmark run over real backends. The
  benchmark's S14 cases are known-absent-UI-content scenes; a real model that claims
  `supported` there is counted as a model error at audit (doc 06: "wrong inference => model
  error"). If a mock-injection benchmark arm is wanted, it is a fifth manifest and a
  separate decision.
- **A4 — perceptual near-duplicate check for authored renders.** Doc 06 requires an
  algorithm/version/threshold even though authored renders from disjoint templates are
  structurally prevented from near-duplicating. Adopted: **aHash 8×8 (Pillow-only:
  convert("L"), resize((8,8)), threshold map), Hamming distance ≤ 6 of 64 bits**, run over
  all 7,140 image pairs as a detector whose hits go to **human review only** — never
  automatic deletion (doc 06 forbids post-hoc deletion). Version/threshold recorded in the
  data card. Rationale for running it at all: it also catches template-variant regressions
  where a future edit collapses two variants into near-identity.
- **A5 — meaning of `expected_decision` in the visual view.** It is the decision a
  **correct** execution would reach: the oracle knows what the pixels show, so the visual
  view's expected decision assumes a correct visual finding and the strict policy. A real
  model that disagrees is a model error, not an invalid expectation. This is what makes
  decisive accuracy and model-error accounting separable.
- **A6 — evidence composition of the visual view.** Doc 06 §2 says the visual view replaces
  only visually assessable interface criteria; external criteria remain external. For most
  families the visual view therefore carries screenshots **plus the external observations
  its external criteria need**. The S06 family is the declared exception that *is* its
  scenario: its visual view withholds the backend observation entirely ("oracle withheld
  from image view"), so the external criterion abstains. Per-case evidence-view
  composition is declared in the oracle file, and S06-style withholding appears in no
  other family.

## 2. Identity, rights, hygiene

- `benchmark_id = "nitelos-synthetic-v1"`, `schema_version = 1`. Every derived report,
  metric and plot carries the label **synthetic**; no real-world generalization claim may
  reference this benchmark (doc 06 §1, doc 13).
- License Apache-2.0 for all authored material (doc 13). Original synthetic UI scenes
  only; synthetic person names and IDs; no third-party screenshots, no AgentHorizon /
  UI-Venus / AbstentionBench / MK-SH-V assets (doc 06 §"Splits and leakage controls",
  doc 13 §5). No PII, credentials or secrets (doc 07).
- **The NIT-008 smoke set is never reused** (doc 04 executability gate; doc 06 §2):
  different templates, different entity namespaces, different scenes. The data tests
  assert that no benchmark artifact SHA-256 equals any `tests/fixtures/smoke` digest and
  that no smoke-set case ID or filename pattern appears.

## 3. Case matrix, lineage groups, split assignment (requirement a, b)

### 3.1 Structure

15 families (S01–S15, doc 06 matrix) × 8 cases = **120 cases**; 60 development, 60
final-test. Each family owns **8 lineage groups** `L1..L8` (S13 uses 4; see §4.13):
L1–L4 → development, L5–L8 → final-test (A1). One case per group. A lineage group fixes:

- a **template variant**: layout skeleton id, palette constants, widget arrangement —
  cosmetic axes that differ per group by fixed constants (no RNG), semantics unaffected;
- an **entity namespace**: 3 synthetic person names from the declared 120-name pool
  (disjoint across all groups), an ID prefix `XX-` unique per group (e.g. `KA-`, `RB-`),
  and an app-instance name variant. No name, prefix or instance name is reused across
  groups, so no string leakage across splits is possible even in principle.

### 3.2 Identifiers and filenames (requirement e)

- `case_id = uuid5(NAMESPACE_NITELOS_BENCH, f"{family}-{group}")`, lowercased, hyphenated
  (e.g. `5f0c...`). Deterministic, neutral, collision-free; the namespace UUID is fixed in
  the generator constants and recorded in the data card.
- Image filenames: `case_id[:12] + ".png"` (and `-b.png` for the second image of S09/S13
  multi-image cases). No family, label, scenario or outcome word appears in any path,
  filename, PNG metadata (no tEXt/iTXt/zTXt/eXIf chunks) or artifact ID. Pixels may
  naturally contain status words (doc 06).
- `group_id = f"{family}:{group}"` (e.g. `s07:L6`) — **runner-side only**, present in
  oracle and manifest metadata, never in model-visible filenames; the manifest's group ID
  field is exactly this value (doc 06 manifest contract).

### 3.3 Split assignment — fixed in advance

The rule is mechanical and was fixed before any render exists: family `S<k>`, groups
`L1–L4` → `dev`, `L5–L8` → `test`. S13 pair members share a group and therefore a split
(DATA-02: counterfactual siblings never cross splits). No reassignment after generation;
any change creates `synthetic-v2` with a new freeze hash. The final split is sealed from
prompt iteration (doc 10 NIT-010 acceptance): no final-test image, label or metric may be
inspected while tuning prompts (implementation logging must be able to show this).

### 3.4 Deduplication

1. Exact SHA-256 over all rendered images and observation payload files: all distinct by
   construction (disjoint entity namespaces guarantee distinct bytes); the data test
   asserts the 120(+multi-image) digests are unique and disjoint from the smoke set.
2. Perceptual: aHash-8x8, Hamming ≤ 6 (A4) over all pairs; hits → `dedup-review.json`
   (pair, distance, disposition signed by a human reviewer). No automatic exclusion.

## 4. Family recipes (requirement a, d, i)

Each recipe fixes: scene, fixture state machine, per-group parameter assignment, evidence
composition per view, criteria per view, and the oracle mapping. Conventions used
throughout:

- All evidence items carry `checkpoint_id = "cp-final"` except S15 history items
  (`cp-1`, `cp-2`, then `cp-final`); `phase = "final"` except S05 (`pending`);
  `captured_at` fixed constants; digests computed by the NIT-003 factories.
- The **assertion view** uses observation evidence (`dom`/`tool`/`external_api`/
  `database` channels) and assertion criteria. The **visual view** replaces each visually
  assessable interface criterion with one `visual` criterion citing the same scene's
  screenshot (≤ 2 images, declared reference order); external and behavioral criteria are
  carried over unchanged (requirement c).
- `expected` per view = (decision, reason codes) of a correct execution under the strict
  policy. Decisions follow the doc-05 truth table: all supported → success; any refuted →
  failure; otherwise abstained.
- Scope columns record which scopes the family exercises (all scope labels appear across
  the benchmark; ≥ 2 cases per family exercise the external-vs-visual/observed contrast
  wherever the family concept involves external state).

### 4.1 S01 — clear completion

- Scene: a job hub window with a final status banner and a job summary line.
- State machine: `job_kind`, `final_status = "completed"`, `items_done`, `exit_ok = true`.
- Parameters by group (L1..L8): `job_kind ∈ {export, report, sync, archive, backup,
  upload, render, index}` in order; `items_done ∈ {2,4,7,12}` cycling over dev groups and
  {3,5,9,14} over test groups.
- Evidence (both views): screenshot(final) + dom observation
  `{"job_status":"completed","items":k}` + external_api observation
  `{"status":"completed","record_count":k}` (bound, fixture collector).
- Assertion criteria: C1 external `/status equals "completed"` (subject `{"job":"<id>"}`),
  C2 observed `/job_status equals "completed"`.
- Visual view: C2 → visual "The window shows a banner stating the <job_kind> completed";
  C1 unchanged.
- Oracle: truth success, sufficient, expected **success** both views
  (`ALL_CRITERIA_SUPPORTED`).
- Scopes: external, observed_state, visual. Secondary tags: none.

### 4.2 S02 — clear failure

- Scene: submission/review window with a final rejection banner and error detail line.
- State: `final_status = "failed"`, `error_code`, `exit_ok = false`.
- Parameters: `job_kind` axis as S01 (same assignment order); `error_code ∈
  {E201,E202,E203,E204}` dev / `{E210,E211,E212,E213}` test cycling.
- Evidence: screenshot(final) + dom `{"job_status":"failed","error":"E2xx"}` +
  external_api `{"status":"failed"}`.
- Assertion: C1 external `/status equals "completed"`; C2 observed `/job_status equals
  "completed"`.
- Visual: C2 → visual "banner states the submission was accepted"; C1 unchanged.
- Oracle: truth failure, sufficient, expected **failure** both views
  (`CRITERION_REFUTED`). Mandatory check "Failure rather than tool succeeded": the scene
  contains a completed-action context item (name + reported_status only) that must not
  flip the decision.
- Scopes: external, observed_state, visual, behavioral(context only).

### 4.3 S03 — incomplete form

- Scene: settings/profile form, one required field empty with visible inline error.
- State: `email = ""`, `validation_error = true`, `fields_ok = false`.
- Parameters: which field is empty ∈ {email, display name, workspace tag, region} across
  groups; form title varies.
- Evidence: screenshot(final) + dom `{"email":"", ..., "validation_error":true}` (channel
  dom, subject `{"form":"<id>"}`).
- Assertion: C1 observed `/validation_error equals false` (scope observed_state).
- Visual: C1 → visual "the form shows no validation error".
- Oracle: truth failure, sufficient, expected **failure** both views
  (`CRITERION_REFUTED`) — the no-error assertion is refuted by the final observation
  (doc 06 S03 mandatory check).
- Scopes: observed_state, visual. (External n/a: the family concept is interface-local.)

### 4.4 S04 — misleading success screen

- Scene: payment/transfer window showing a success banner.
- State: `ui_banner = "sent"`, `ledger_status ∈ {"missing","failed"}`, truth known to the
  oracle. Groups L1,L2 (dev) and L5,L6 (test): ledger **failed** (external observation
  `{"status":"failed"}` supplied); L3,L4 and L7,L8: ledger **missing** (no external
  observation at all).
- Assertion: C1 external `/status equals "completed"` (scope external).
- Visual: C1 unchanged; plus the interface appearance as a second criterion visual
  "banner states the payment was sent" (supported) — the conjunction is decided by C1.
- Oracle: failed-ledger cases — truth failure, sufficient, expected **failure** both
  views; missing-ledger cases — truth failure (state machine knows), evidence
  **insufficient**, expected **abstained** both views (`INSUFFICIENT_EVIDENCE`) per doc 06
  "External missing abstains; false refutes".
- Scopes: external, visual.

### 4.5 S05 — loading/pending

- Scene: deployment/release window with spinner and progress bar mid-run.
- State: `phase = pending`, `progress ∈ [20,80]%`, outcome not settled.
- Evidence: screenshot(**pending**, checkpoint `cp-mid`) + dom observation
  `{"deploy_state":"running"}` phase pending.
- Assertion: C1 observed `/deploy_state equals "completed"` (scope observed_state).
- Visual: C1 → visual "the window shows a final completion state".
- Oracle: truth unknown, insufficient, expected **abstained** both views
  (`PENDING_STATE`; decision stays ok/abstained — pending is never failure, doc 05).
- Scopes: observed_state, visual. (External n/a.)

### 4.6 S06 — hidden backend failure

- Scene: sync/status window showing success.
- State: `ui = success`, `database_status = "failed"` (fixture oracle).
- Evidence, assertion view: screenshot(final) + **database** observation
  `{"status":"failed"}` (bound). Criteria: C1 external `/status equals "completed"`
  (channel database).
- Evidence, visual view (A6): screenshot only — the database observation is withheld.
- Oracle: truth failure, sufficient; expected assertion view **failure**
  (`CRITERION_REFUTED`); expected visual view **abstained** (`INSUFFICIENT_EVIDENCE`,
  UNTRUSTED_EXTERNAL absent evidence) — the image cannot confirm external state.
- Scopes: external, visual. This is the flagship external-vs-visual contrast case.

### 4.7 S07 — wrong user/object

- Scene: order/record detail page naming an entity ID.
- State: `visible_order_id = "<group-prefix>-7731"`, `criterion_order_id` = a different
  group's ID (declared in oracle). Groups alternate variant: L1,L3 (dev) / L5,L7 (test):
  **subject mismatch** (criterion subject names the other ID; no eligible evidence);
  L2,L4 / L6,L8: **explicit wrong-ID assertion** (`/order_id equals "<other>"` over the
  final dom observation, subject matches evidence).
- Assertion: as per variant.
- Visual: variant 1 → visual "the page shows order <criterion-id>" (subject mismatch
  still applies at policy level); variant 2 → visual "the page names order <criterion-id>".
- Oracle: truth failure (wrong object), variant 1 insufficient → expected **abstained**
  (`SUBJECT_MISMATCH`); variant 2 sufficient → expected **failure**
  (`CRITERION_REFUTED`) — doc 05 example "Wrong customer on confirmation page".
- Scopes: observed_state, visual; external via the record backend observation in variant
  2's evidence set (external_api `{"order_id":"<visible>"}`, bound, ≥ 2 cases).

### 4.8 S08 — missing visual evidence

- Scene: any final-state scene (rendered for the record; the interesting part is the
  evidence view).
- State: full normal completion or failure state (truth known), but the case's evidence
  list is **empty**; criteria reference no evidence (`evidence_ids = []`).
- Assertion: C1 observed `/status equals "completed"` with empty evidence_ids.
- Visual: C1 visual with empty evidence_ids (no screenshot supplied).
- Oracle: truth success (L1,L2,L5,L6) / failure (L3,L4,L7,L8), evidence **insufficient**,
  expected **abstained** both views (`MISSING_EVIDENCE`) — doc 06 "Empty evidence view =>
  abstain". (The dangling-nonempty-reference input error is contract-suite territory, not
  a benchmark case.)
- Scopes: observed_state, visual.

### 4.9 S09 — contradictory evidence

- Scene: status center; **two** final screenshots (a, b) with conflicting banners, and in
  the assertion view two dom observations with conflicting `/status` values.
- State: `snap_a = "completed"`, `snap_b = "failed"`, same checkpoint, both final.
- Parameters: which banner is a vs b, colors, job kinds per group.
- Assertion: C1 observed `/status equals "completed"` citing both observations.
- Visual: C1 visual citing both screenshots (2 images, declared order).
- Oracle: truth unknown, **contradictory**, expected **abstained** both views
  (`CONTRADICTORY_EVIDENCE`) — "Unknown for the same criterion", never source-count
  resolution (doc 05 example table).
- Scopes: observed_state, visual.

### 4.10 S10 — tool success, task failure

- Scene: upload window with an error banner after a "tool completed" action.
- State: `action_status = "completed"`, `final_status = "failed"`.
- Evidence: screenshot(final) + action evidence (name "upload-file", reported_status
  completed) + dom `{"job_status":"failed"}` + external_api `{"status":"failed"}`.
- Assertion: C1 behavioral `/reported_status equals "completed"` (scope behavioral, over
  the action view); C2 external `/status equals "completed"`.
- Visual: C2 unchanged; C1 stays behavioral (actions are context, not visual criteria).
- Oracle: truth failure, sufficient, expected **failure** both views — C1 supported, C2
  refuted; behavior cannot override the required final state (doc 05/06).
- Scopes: behavioral, external, visual.

### 4.11 S11 — task success, misleading summary

- Scene: completed job window plus a visible agent summary panel whose text contradicts
  the state ("upload failed" while the ledger says completed).
- State: `ledger_status = "completed"`, `summary_text = "failed"` (never a criterion).
- Evidence: screenshot(final) + dom `{"summary":"failed"}` (untrusted prose, normalized)
  + external_api `{"status":"completed"}` (bound).
- Assertion: C1 external `/status equals "completed"`.
- Visual: C1 unchanged; plus visual "the window shows a completion banner" (supported).
- Oracle: truth success, sufficient, expected **success** both views — the summary cannot
  veto the authoritative assertion (doc 05 example table).
- Scopes: external, visual, observed_state.

### 4.12 S12 — ambiguity

- Scene variants per group (one each): status text rendered unreadably small; screenshot
  cropped so the decisive element is cut; criterion deliberately underspecified relative
  to what is visible ("the correct record is highlighted" with two similar highlights).
- State: underlying truth assigned per group (3 success / 1 failure per split), but the
  evidence cannot establish it.
- Assertion: C1 observed pointer into a dom payload where the decisive key is absent
  (`/final_result` missing) → MISSING_VALUE.
- Visual: C1 → visual matching the ambiguous scene.
- Oracle: truth as assigned, **insufficient**, expected **abstained** both views
  (`MISSING_VALUE` / `MODEL_UNCERTAIN`) — unknown expectation, not a forced binary label
  (doc 06 S12).
- Scopes: observed_state, visual.

### 4.13 S13 — counterfactual image changes

Structure: 8 cases = **4 pairs**; L1 = dev counterfactual pair, L2 = dev irrelevant-edit
pair, L5 = test counterfactual pair, L6 = test irrelevant-edit pair (L3,L4,L7,L8 unused;
the family still contributes exactly 8 cases, keeping 120 total).

- Counterfactual pair (base/variant): identical scene except **one task-relevant value** —
  the final status line reads `passed` vs `failed` (readable). Criterion: "the status line
  reads passed" (assertion `/status equals "passed"`; visual counterpart). Oracle: base
  truth success/expected **success**, variant truth failure/expected **failure**, both
  views; pair grouping unit recorded so NIT-011's counterfactual sensitivity metric
  consumes it.
- Irrelevant-edit pair: identical scene and state; the edit changes only an unrelated
  widget (button label color, footer text). Same expected decision both members
  (**success**); consumed by the irrelevant-change invariance metric with correctness
  (doc 06).
- Oracle: sufficient; sufficiency sufficient; expected decisions per member as above.
- Scopes: observed_state, visual.

### 4.14 S14 — model hallucination resistance (known absent content)

- Scene: a report list window; the criterion concerns a confirmation element that the
  state machine declares **absent** (no such row/banner exists).
- State: `confirm_banner_present = false`.
- Evidence: screenshot(final) + dom `{"confirm_banner_present": false}`.
- Assertion: C1 observed `/confirm_banner_present equals true` → refuted.
- Visual: C1 → visual "a confirmation banner for the report is shown".
- Oracle: truth failure, sufficient, expected **failure** both views. A model answering
  `supported` is a **model error** counted at audit (A3); no mock backend is used.
- Scopes: observed_state, visual.

### 4.15 S15 — multi-step trajectories

- Scene: import wizard shown at an intermediate step; history items at earlier
  checkpoints.
- State: steps 1–2 completed (actions + observations at `cp-1`,`cp-2`), then final
  predicate at `cp-final`. Variant by group: L1,L2 / L5,L6 — final predicate observation
  **absent** (only history supplied); L3,L4 / L7,L8 — final observation present with
  `status = "failed"`.
- Assertion: C1 observed `/status equals "completed"` at the final checkpoint (subject and
  `checkpoint_id` = `cp-final`); history is context (doc 05: no temporal logic).
- Visual: C1 → visual over the final screenshot (present-failure variant) or no final
  screenshot (absent variant: only intermediate screenshots as context).
- Oracle: absent variant — truth unknown, insufficient, expected **abstained**
  (`MISSING_EVIDENCE`; earlier apparent success cannot substitute); failure variant —
  truth failure, sufficient, expected **failure**.
- Scopes: observed_state, visual, behavioral(context), external (final predicate is an
  external_api observation in the failure variant, ≥ 2 cases).

## 5. Request-view construction rules (requirement c)

1. Build the assertion view first: `VerificationRequest` per doc 03 via the NIT-003
   factories; objective text is neutral prose naming the task (no outcome words beyond
   the task description), identical across views.
2. Visual view = copy of the assertion view where each criterion with scope
   `observed_state` **that is visually assessable** (family recipe marks it) is replaced
   by a `visual` criterion (single visually assessable statement, subject and evidence
   order preserved, ≤ 2 images). `external` and `behavioral` criteria are copied
   unchanged. Evidence list: screenshots for visual criteria + the observations external/
   behavioral criteria cite (per-family composition; S06 exception per A6).
3. Cases with **no visual criterion** in their visual view (possible in S08) are still
   scheduled in `*-visual.json` with criteria identical to the assertion view; the
   selected backend goes unused, diagnostics record it, and the case is not counted
   toward model-inference accuracy (doc 06 §2). The runner counts model invocations per
   view so deterministic-only cases cannot inflate visual accuracy.
4. Request JSON files are per-view per-case artifacts under `benchmarks/synthetic_v1/
   requests/`; each obeys doc 03 limits (NIT-002 parser enforces).

## 6. Oracle records and derivation (requirement d)

One JSON record per case in `oracle/<split>.json` (never referenced by any manifest;
loaded by reporting after inference — doc 06):

```json
{
  "case_id": "...", "group_id": "s06:L5", "primary_family": "S06",
  "secondary_tags": ["external-vs-visual"], "split": "test",
  "state": { "ui": "success", "database_status": "failed" },
  "outcome_truth": "failure",
  "evidence_sufficiency": "sufficient",
  "expected": {
    "assertion": {"decision": "failure", "reason_codes": ["CRITERION_REFUTED"]},
    "visual":    {"decision": "abstained", "reason_codes": ["INSUFFICIENT_EVIDENCE"]}
  },
  "oracle_source_id": "state-machine:s06:v1",
  "pair": null,
  "rationale": "database observation refutes completion; image-only view abstains",
  "annotators": [], "annotation_status": "pending",
  "scope": ["external", "visual"]
}
```

Derivation procedure: the renderer writes the per-case `state` object; a **separately
reviewed oracle script** maps state → truth/sufficiency/expected via the tables in §4
(it reads state, never pixels or captions — doc 06). The oracle script and the renderer
are different code files with different reviewers. `outcome_truth` values follow doc 06
(unknown never converted to a negative). Human annotation (§9) verifies that renders
match state and signs off the labels.

## 7. Generator contract (requirement e)

- Pillow-only; `ImageFont.load_default(size=...)`; **no RNG — all constants fixed**; the
  smoke-set lessons apply: declared renderer platform recorded in the data card (OS,
  Python, Pillow, FreeType, zlib), byte-identity asserted only on that renderer, all other
  fixture checks platform-independent (DATA-04 as implemented for the smoke set).
- Templates: 8 layout skeletons × palette/widget constants; scenes are original synthetic
  UI; no real product names, logos or fonts redistributed.
- Output: PNGs (limits per doc 03), observation payload JSONs, request JSONs, oracle state
  files, data card with per-file SHA-256, generator version, parameter tables, and the
  dedup review log.
- DATA-03: neutral IDs/filenames; no labels in paths or metadata; oracle files physically
  separate from artifacts the runner passes to backends.

## 8. Fixture trust for external criteria (requirement f)

`benchmarks/synthetic_v1/fixture-collector.json` is a **host-reviewed** authorization file
(separate review sign-off, recorded in decisions.md) listing, for every external evidence
item: `evidence_id`, `source_id = "fixture-collector-v1"`, `sha256`, `subject`,
`checkpoint_id`. At run time the NIT-012 trusted-runner configuration (i) authorizes the
fixture collector, (ii) verifies artifact digests against the separately reviewed oracle
manifest, and (iii) **constructs** `TrustBinding` objects in code. The evaluation manifest
itself (untrusted-shaped) carries no trust: any trust-looking field inside a manifest case
is ignored, and NIT-012's EVAL/SEC tests must show a forged `trusted` field cannot satisfy
an external criterion (doc 06 §"Manifest and runner contract", doc 07 SEC-02). Everything
is labeled synthetic.

## 9. Annotation protocol (requirement h) — HUMAN GATE

**This is a human gate that agent sessions cannot satisfy** (doc 16 lists reviewer
availability as a maintainer-owned open issue). The design's job is to make it efficient.

- Scope: **two independent human reviewers for every final-test case** (60 cases × 2),
  plus one reviewer per development case (engineering sanity; doc 06 requires two only
  for final-test and real-world annotations). Reviewers must not be the person who wrote
  the generator/oracle for the families they review, and they never see any model output.
- Review packet (one HTML/printable page per case, generated from the oracle file):
  objective; both views' criteria rendered as plain sentences; the rendered image(s); the
  state record; the derived labels; a 6-item checklist: (1) render matches state, (2)
  each criterion's expected per-view finding matches what a careful reader sees/derives,
  (3) truth label, (4) sufficiency label, (5) expected decisions + reason codes,
  (6) scope tags. Approve / fix-with-note per item.
- Disagreements (any item differs between the two reviewers) → adjudication by a third
  person; unresolved cases keep `unknown` truth or the disputed label's conservative
  value and are **reported**, never silently dropped (doc 06). Agreement rate and a
  reviewer-confusion table are recorded with the freeze.
- Effort estimate: ≈ 3–4 minutes per case per reviewer → ≈ 6–8 person-hours for the
  final-test gate; packets are ordered by family so context carries.
- Annotator IDs (pseudonymous `ann-1`, `ann-2`, ...) recorded per case; annotation
  status must be `approved` for all final-test cases before the freeze hash is computed.

## 10. File layout, manifests, freeze (requirement g)

```
benchmarks/synthetic_v1/
  dev.json  dev-visual.json  test.json  test-visual.json   # EvaluationManifest schema 1, 60 cases each
  requests/            # per-case per-view request JSON (relative paths + hashes)
  artifacts/           # PNG renders + observation payload files
  oracle/dev.json  oracle/test.json        # loaded post-inference only
  fixture-collector.json                  # reviewed trust authorization (§8)
  DATA_CARD.md         # provenance, license, generator version, renderer platform,
                       # parameter tables, per-file SHA-256, dedup log, agreement stats
  freeze.sha256
```

Manifests obey the doc 06 runner contract (schema 1, seed, evidence-view id, policy
config/hash, case list with group ids and artifact mappings, provenance/license record,
≤ 4 MiB, ≤ 10 000 cases, root-confined relative paths). Freeze procedure: after final-test
annotation sign-off, compute SHA-256 over the sorted `(path, digest)` list of every file
above → `freeze.sha256`, recorded in decisions.md; any later change requires
`synthetic-v2`. The two views of one split share case IDs but have different
view fingerprints; `compare` treats them as different-evidence analyses (doc 06).

## 11. Traceability: families → mandatory checks → expected decisions (requirement i)

| Family | Doc 06 mandatory behavioral check | Expected (assertion view) | Expected (visual view) | Scopes exercised |
|---|---|---|---|---|
| S01 | Supported criteria can succeed | success | success | ext, obs, vis |
| S02 | Failure, not "tool succeeded" | failure | failure | ext, obs, vis |
| S03 | Refute no-error assertion | failure | failure | obs, vis |
| S04 | External missing abstains; false refutes | failure (L1,2,5,6) / abstained (L3,4,7,8) | same per group | ext, vis |
| S05 | Pending is explicitly nonfinal | abstained | abstained | obs, vis |
| S06 | External abstains on image-only view | failure | abstained | ext, vis |
| S07 | Reject subject mismatch / refute wrong ID | abstained (v1) / failure (v2) | same per variant | obs, vis, ext |
| S08 | Insufficient → abstain | abstained | abstained | obs, vis |
| S09 | Unknown for the same criterion | abstained | abstained | obs, vis |
| S10 | Behavior cannot override final state | failure | failure | beh, ext, vis |
| S11 | Summary cannot veto assertion | success | success | ext, vis, obs |
| S12 | Unknown expectation, not forced binary | abstained | abstained | obs, vis |
| S13 | Paired sensitivity; irrelevant-edit invariance | per member (success/failure; success) | per member | obs, vis |
| S14 | Fabricated ref ⇒ backend error; wrong inference ⇒ model error (A3) | failure | failure | obs, vis |
| S15 | Earlier success ≠ missing final predicate | abstained / failure per variant | same per variant | obs, vis, beh, ext |

Coverage: every decision value (success/failure/abstained) and every scope label appears;
every abstention reason in doc 03's table that is producible from supplied evidence
appears at least once across the matrix (PENDING_STATE, MISSING_EVIDENCE,
MISSING_VALUE, SUBJECT_MISMATCH, CONTRADICTORY_EVIDENCE, UNTRUSTED_EXTERNAL-adjacent
insufficiency, MODEL_INFERENCE_DISALLOWED is policy-side and stays in contract tests).

## 12. Implementation test plan (DATA-01..05, written first at NIT-010 time)

- DATA-01: 120 cases; 15 families × 8; 60/60 split; per family 4+4 from disjoint groups.
- DATA-02: S13 pair members (and any shared-scene variants) share a split; no group id
  spans splits.
- DATA-03: no label words in any model-visible path/filename/metadata; oracle files not
  referenced by manifests; request JSON contains no oracle fields.
- DATA-04: regeneration byte-identity on the declared renderer only (platform-scoped, as
  in the smoke set); digests recorded in DATA_CARD match.
- DATA-05: an external criterion succeeds only when the fixture-collector authorization
  matches digest/subject/checkpoint; a manifest-embedded trust field is inert (needs the
  NIT-012 runner stub; the data-side half asserts the authorization file's shape).
- Plus: digest uniqueness; disjointness from the smoke set; every §11 expected decision
  realizable by the recorded criteria (a dry-run policy check with the deterministic
  backend over the assertion view must reproduce the expected assertion decisions
  exactly — this is the strongest single acceptance test and needs no model).

## 13. Open questions for the orchestrator

1. Confirm A1 (8 disjoint groups/family) vs the weaker shared-group reading.
2. Confirm A3 (S14 without mock injection in the frozen benchmark).
3. Confirm the annotation staffing plan (two final-test reviewers + adjudicator; doc 16
   flags reviewer availability as maintainer-owned).
4. The deterministic-backend dry run in §12 runs at NIT-010 time and depends on NIT-004/005
   being merged; if sequencing slips, it moves to NIT-012 acceptance unchanged.
