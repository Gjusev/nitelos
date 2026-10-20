# Commit map, 2026-10-20 history rewrite

On 2026-10-20 the repository history was rewritten to remove `Co-Authored-By` attribution
trailers from commit messages. File contents did not change: every branch tip and the
`v0.1.0` tag have the same tree as before. Commit ids did change. Documents written before
the rewrite (status, decisions, the sealed AR-4 freeze dossier) keep their original ids on
purpose, so sealed text stays byte-identical; use this table to resolve them.

`v0.1.0` (the commit published to PyPI as nitelos 0.1.0) was `6091e76` and is now `29813ce`.

| Old | New | Subject |
|---|---|---|
| `007f8cc` | `5d0ea78` | NIT-007 WIP: missing typing import in deterministic.py |
| `02ca881` | `7c11f0d` | NIT-008: environment-agnostic dependency-absence tests |
| `04d6e08` | `bb745f5` | decisions: G4 adjudication complete (2 label changes; other claims rejected on evidence) |
| `06a7df6` | `7e549d1` | NIT-013 part B: dev visual run record, family tables, measured findings |
| `06ce9dc` | `44d54d2` | NIT-002: isolate import-lightness check in subprocess |
| `085e012` | `7900b15` | NIT-008: gated real-local-model integration test |
| `08ace3b` | `8535980` | NIT-008: derive smoke bookkeeping from the attempt counter |
| `08d84f1` | `76fc930` | NIT-009: bounded action-context selection module |
| `0c55d73` | `d6fd991` | status: NIT-003 Linux finding, cross reviews, CI gap |
| `10b4d0c` | `545742c` | NIT-015: lint fixes in the new release tests (unused imports, condition order) |
| `15c141c` | `7856c00` | status/decisions: NIT-011 done, CI jobs merged |
| `1624e5e` | `51e6473` | decisions: record AR-1 outcome and carried-forward requirements |
| `16623e9` | `2967fb1` | Merge NIT-012 + NIT-013A chain: runner review fixes, smolvlm wiring, RUN validator (reviewed) |
| `17895d8` | `fa7aa05` | Merge branch 'integration/v0.1' into nit/007-backend-boundary |
| `18e16d0` | `73996eb` | docs: format code blocks in design specs |
| `196d752` | `c4d5119` | NIT-008: accept the bare-sequences generate return of transformers 5 |
| `1972fac` | `c7fcef8` | Merge NIT-015 finalization (REL-01..04, license inventory test, release workflow; G4-dependent items pending) |
| `19de069` | `38dfe1f` | Launch kit: brand, film sources, README and docs overhaul |
| `1b1f074` | `760e922` | NIT-001: repository foundations, core/dev lock, packaging tests and CI |
| `1bfaef2` | `558c09f` | status: NIT-002 to AR-1, NIT-011A to review |
| `1ce45f4` | `a4acb44` | Explainer cut to 28 s; README hero links to the hosted film |
| `2074a62` | `04c78f4` | status: NIT-011 part A assigned |
| `20893db` | `fa026c5` | decisions: ADR-012 checkpoint swap to SmolVLM2-2.2B (user-approved) |
| `2103c1a` | `6796133` | docs: implementer/reviewer rules |
| `219a128` | `187c92e` | decisions: ADR-011 nullable request_id (user-approved); G4 staffing pending |
| `2294091` | `5159e95` | NIT-007: F1 explanatory test for the duplicate-criterion guard |
| `236b868` | `4ef21cf` | NIT-011: metrics over case records (counts, rates, pairs, probability, latency) |
| `2671d5f` | `c0f9c69` | NIT-002: AR-1 fixes — constructor depth bound, snapshot README, bytearray signature |
| `28f0f97` | `3e887eb` | decisions: NIT-003 review outcome |
| `2940b01` | `ec5c46d` | NIT-010: authored benchmark fixtures, oracle separation and manifests |
| `2c4609c` | `7a402cc` | NIT-006: end-to-end verifier SDK and lifecycle |
| `2d5d3be` | `d608d23` | NIT-009: review fix — timezone-aware as_of in to_request (F1/F2/F4) |
| `2da002c` | `8d26db0` | NIT-013 part B: dev deterministic run (60/60 ok) + the labeled visual driver |
| `2f67aca` | `31e380d` | Merge branch 'nit/010-fixtures' into nit/012-runner |
| `3217998` | `3364cdc` | NIT-013B: ruff format |
| `321d001` | `d90fd43` | status: NIT-010 delivered; NIT-007 reassigned; reviewer availability |
| `32246c5` | `c0c0478` | NIT-015: release conformance tests, license inventory check, release-prep workflow |
| `3454f0b` | `2bc3cd2` | decisions: NIT-013B dev-run records and preflight ruling |
| `34631b6` | `943fe64` | Merge NIT-009: schema-v1 traces, action-context helper, caller recipe (reviewed by nitelos-3a; F1/F2/F4 verified) |
| `3631943` | `0ac782a` | NIT-012: Linux verification fixes — resolved-target symlink assertion, mypy-clean rss tail |
| `37e4b8a` | `22ab7d5` | NIT-008 phase B (ADR-012): checkpoint swap to SmolVLM2-2.2B-Instruct |
| `3831c29` | `65a4776` | status: NIT-005 review, NIT-006 started |
| `3a04870` | `3323ca6` | Merge NIT-002: strict domain models and schema snapshots (AR-1 approved with changes, fixes verified) |
| `3c888e2` | `8981662` | NIT-010: synthetic benchmark v1 design specification |
| `3d168e2` | `46482fe` | NIT-011: exclude non-finite replicate statistics, decircularize CP oracle |
| `3f1e171` | `3f1e171` | Initial commit |
| `3fbcdf4` | `ee10e51` | docs: add v0.1 planning baseline |
| `405d178` | `d2ac755` | NIT-008: D3 final pure diagnostic script (caption + QA, escalation evidence) |
| `40a3315` | `1d28f3e` | decisions: NIT-005 review outcome |
| `410e001` | `2731621` | decisions: ADR-013 agent-performed G4 audit (user-approved) |
| `41bce6d` | `79f1664` | NIT-015: release-preparation artifacts (checklist, NOTICE, licenses, workflow sketch) |
| `42ef33a` | `9f1c2f6` | NIT-005: review fixes — visual result refs, pure eligibility helper, immutable ineligible map |
| `4373fc7` | `85d7300` | NIT-015: quote the audit step name (colon breaks YAML mapping) |
| `45ae50a` | `e4f0231` | NIT-005: evidence eligibility and pure policy aggregation |
| `45bcabb` | `9df7766` | decisions: NIT-004 review outcome |
| `4622a4a` | `823aa5b` | decisions/status: AR-4 approved (protocol+inputs); human gate pending |
| `4965a22` | `c75b0a9` | Merge NIT-004: deterministic assertion evaluator (reviewed by nitelos-0f; F1 verified) |
| `4a7c610` | `e6d5d88` | status: NIT-011A integrated |
| `4b1383b` | `ed22f24` | Merge branch 'integration/v0.1' into nit/013b-runs |
| `4bdf263` | `e3d3ca5` | Merge branch 'integration/v0.1' into nit/014-docs |
| `4e24012` | `0c5c7d1` | NIT-007: wire bounded action context and omitted-context diagnostics |
| `4e6879a` | `fcc852d` | status: session churn; NIT-008 WIP state |
| `52c36d8` | `0873641` | decisions/status: NIT-010 review findings |
| `548ac96` | `e5ec749` | NIT-015: record AR-3 local-extra additions (torchvision, num2words) |
| `55de9ed` | `105131f` | status: 012/013A merged |
| `56e2c97` | `5b1a78f` | NIT-009: schema-v1 trace ingestion, to_request and caller recipe |
| `5842911` | `f460cc6` | Merge NIT-012 runner design spec + markdown code-block format fix |
| `5843f80` | `f531bca` | NIT-008: scope byte-identity to declared renderer, document UNKNOWN labels |
| `58ee5d7` | `b3f4af9` | Merge NIT-005: evidence eligibility and pure policy aggregation (reviewed by nitelos-0f; F1-F3 verified) |
| `5a52bb2` | `2c6997d` | status: delegate to peer sessions; record model probe |
| `5aa4612` | `c8f44c0` | NIT-008 phase B: G3 PASSED — 2.2B smoke record, sanity record, compatibility report |
| `5b63f8b` | `850eec3` | decisions/status: AR-5 approved — v0.1 release candidate complete |
| `5c47aca` | `5f8e6f2` | status: ADR-012 in progress; weight provisioning incident |
| `5d4fb0d` | `7ba0f0f` | README: explain the workflow first |
| `5d5f35e` | `4ed7fec` | NIT-010: review fixes — S11 truth, visual compositions, neutral decorations |
| `5d849dd` | `0b0f67d` | status: smoke-set integrated |
| `5dfacb9` | `ac56e0c` | Merge branch 'nit/013-reports' into nit/013b-runs |
| `5e28aa8` | `537b470` | Merge NIT-008 smoke-set fixtures (reviewed by orchestrator; Win pass, Linux pass+platform skip) |
| `5eb6bbc` | `84859bb` | infra: full-offline and packaging CI jobs per doc 12 |
| `5fc3f11` | `2ba41f5` | Merge NIT-003: evidence bytes, hashes, references and bounds (reviewed by nitelos-0f; F1/F2/F3 verified) |
| `5ffd8e8` | `23eaaa3` | NIT-011: exact Wilson boundary values (k=0 low 0.0, k=n high 1.0) |
| `6091e76` | `29813ce` | release-prep: audit the shipped closure (core+eval); exclude the custom-index local extra, disclosed |
| `60b1150` | `50b5dcd` | NIT-013 part B: methodology doc, family-table reporter, deterministic tables |
| `61e752d` | `1cb973c` | release-prep: attestations need a public repo — keep attest non-blocking, disclosed |
| `62436a3` | `fbbea03` | decisions/status: AR-3 approved; NIT-008 merged |
| `63ce67c` | `e6bc828` | status: smoke-set review findings |
| `64299ce` | `6b3d108` | README: PyPI version and supported-python badges |
| `64727b8` | `b05232c` | audit: reviewer 2 (fresh agent) final-test annotation audit |
| `65e482c` | `f6b14cc` | NIT-008 phase B: 2.2B sanity-caption script |
| `6aebf3a` | `ae1a1fc` | NIT-007 WIP: backend protocol, capabilities, finding validation, preflight |
| `6d31703` | `d83556c` | Merge branch 'integration/v0.1' into nit/012-review-fix |
| `6f1000f` | `f4d5b30` | status: NIT-010 fixes verified; orchestrator now nitelos-6b |
| `700e096` | `39bb660` | release-prep: attest job needs the attestations: write permission |
| `70facb3` | `a179d87` | release-prep: fix attest subject-path glob; exclude the editable project from the audit export |
| `7128211` | `a1583b2` | Merge NIT-011 part A: evaluation statistics (reviewed by nitelos-69, fixes verified) |
| `738f439` | `f47cbca` | NIT-012: evaluation runner design specification |
| `756968d` | `bd12d73` | NIT-010: drop unused local in composition test |
| `772be49` | `570ecaa` | NIT-008: approved iteration-round runner (D1/D2 + full 11-case, both templates) |
| `7a7f896` | `b5476c7` | Merge NIT-006: verifier SDK and lifecycle + ADR-011 (AR-2 approved; fixes verified) |
| `7ab6871` | `b36ac0a` | NIT-008: development smoke-set fixtures (12 doc-04 cases, 14 images) |
| `7ad92d1` | `741e346` | Merge G4 audit: reviewer 2 (fresh agent) — 44 agree / 16 disagree |
| `7ae6198` | `c146813` | status: NIT-011B delivered |
| `7ce7495` | `ee4ed25` | status: NIT-006 in AR-2; ADR-011 |
| `7d07e8b` | `1680840` | status: start implementation log |
| `7dfad84` | `732ae60` | Merge NIT-008: real SmolVLM adapter (ADR-012 SmolVLM2-2.2B; G3 passed; AR-3 approved) |
| `7fb9e09` | `db23a0f` | NIT-013B: shared-backend mode for the evaluation CLI — one backend per run |
| `80dcdba` | `5c73de6` | Merge NIT-010 design specification (A1-A6 accepted by orchestrator) |
| `81cda13` | `bcb34a5` | status: NIT-014 merged |
| `82021a2` | `36a804a` | NIT-012: review fixes — smolvlm wiring, collector exit-2, preprocessing fingerprint |
| `8215cca` | `1459107` | decisions/status: G3 passed with 2.2B; AR-3 launched |
| `82ded19` | `75dfaed` | release-prep: note the configured PyPI pending publisher |
| `82dfc42` | `5ecd91b` | decisions: accept NIT-010 design readings A1-A6 |
| `8953c78` | `b03a885` | NIT-013B: preflight fix per ruling — assertion criteria never consult backend capabilities |
| `8c3f20b` | `6f3e074` | NIT-008: local extra, offline SmolVLM adapter and mocked contract tests |
| `8e04c23` | `bcc7f5c` | NIT-011: pure evaluation statistics (Wilson, Clopper-Pearson, group bootstrap) |
| `8f19a3e` | `6a4c271` | NIT-014: merge-time update — gate record, 2.2B pin, real visual demo |
| `904728e` | `03ee425` | decisions: NIT-012 review outcome and rulings |
| `914f522` | `e794009` | Merge branch 'nit/009-traces' into nit/012-runner |
| `9189a27` | `8a31ba0` | Merge branch 'nit/010-fixtures' into nit/012-runner |
| `940f9cb` | `1f9a410` | decisions: shared-backend mode; preprocessing-probe defect record |
| `94baa2e` | `17a6ad4` | NIT-013B: dev-visual re-run on the fixed pipeline — 60/60 ok, agreement 41/60 |
| `94c8c90` | `9d9240b` | status: NIT-015 finalization merged |
| `95fbe79` | `0db0a8b` | status: NIT-006 merged, NIT-009 review, NIT-010 started |
| `9634d85` | `777dae4` | Merge NIT-011 part B: metrics over case records (reviewed by nitelos-69: APPROVE) |
| `98b60a2` | `48414be` | Merge AR-4 freeze dossier (approved by orchestrator) |
| `98dd2a1` | `7b24223` | NIT-008: D3 record — multimodal wiring WORKS; collapse is format instruction-following |
| `99285d8` | `df56e4b` | NIT-008: expose last_raw_output diagnostic and the CPU smoke-run script |
| `996bd1d` | `27b68ef` | Merge G4 audit: reviewer 1 (nitelos-14) — 48 agree / 12 disagree |
| `9b10fa8` | `df44bc9` | Merge NIT-007: backend boundary and capability validation (reviewed by nitelos-f2; F1 verified) |
| `9b9049b` | `d000afe` | status: shared-backend merged; AR-4 dossier assigned |
| `9f715a3` | `59fa03c` | status: weights provisioned; NIT-015 prep verified |
| `a011aae` | `d04a0b2` | Merge NIT-010: synthetic benchmark fixtures (reviewed; S11 truth, compositions, numeral fixes verified) |
| `a45ffd2` | `c9be339` | decisions: NIT-009 review outcome |
| `a4ce826` | `4a4ef24` | release-prep: dist/ must hold only distributions at publish time |
| `a4fc625` | `ed16010` | status: session restart recorded |
| `a5b6eaa` | `872af89` | status: integration green after isolation fix |
| `a5d88c7` | `3ab0265` | decisions: D3 result; NIT-007 merged |
| `a662086` | `1499ec7` | status: NIT-007 to review, NIT-008 started |
| `a662251` | `571ac0a` | status: integration green after format fix |
| `a6dfc45` | `994c9b5` | NIT-010: format the review-fix test additions |
| `a96b445` | `99e9de9` | status/decisions: NIT-005 merged, NIT-012 design accepted, format-check process defect |
| `acf9535` | `436ee8d` | NIT-008: fixed v2/v3 prompt candidates, honest smoke bookkeeping |
| `ade2f80` | `4414fb4` | decisions: accept NIT-008 design readings A1-A7 |
| `b12d55c` | `a1023f8` | Merge branch 'integration/v0.1' into nit/010-fixtures |
| `b192013` | `f410f55` | status: NIT-004 merged |
| `b392f17` | `32b10f9` | NIT-004: deterministic assertion evaluator |
| `b451a6a` | `837c137` | NIT-013: RUN-01/RUN-02 report validator (part A) |
| `b4d9756` | `e6783b0` | NIT-012: reproducible sequential evaluation runner |
| `b5bc5ed` | `38113e3` | decisions: G4 human reviewers scheduled at the end (user decision) |
| `b62b99f` | `785b8ae` | status: NIT-009 started |
| `b656dd3` | `84da215` | NIT-008: iteration-round record — G3 unreachable under every candidate |
| `b8affe9` | `83a0ff3` | Merge branch 'integration/v0.1' into nit/015-release |
| `b8ed6a2` | `969725c` | Explainer film: any model, the evidence, the decision, who it is for |
| `bb4e5bd` | `ec9c3d0` | decisions/status: NIT-010 merged |
| `bcc70a4` | `20548ca` | NIT-008: smoke script tolerates error-status results |
| `bf0ca3c` | `80dce91` | decisions: NIT-008 G3 attempt-1 result and iteration ruling |
| `c1278cb` | `dd3f3db` | decisions/status: AR-2 approved conditionally |
| `c2cedec` | `30f56fc` | Merge branch 'nit/009-traces' into nit/010-fixtures |
| `c35d20c` | `1254816` | NIT-013B: apply G4 adjudication (ADR-013) and seal the final-test freeze |
| `c5182f1` | `6e15906` | NIT-008: record raw generations even when the parser rejects them |
| `c780590` | `d6e3c68` | status: NIT-013B merged; shared-backend assigned |
| `c7882e6` | `d691f77` | status: reassignments after restart (independence preserved) |
| `cb93207` | `848a783` | status: NIT-012 delivered+verified |
| `cbcc8fd` | `8e7083d` | Merge NIT-002 test isolation fix |
| `cd9e224` | `acbdff3` | NIT-003: evidence bytes, hashes, references and bounds |
| `cf25f7b` | `e66c1d2` | NIT-003: portable test fixtures and decode/header dimension agreement |
| `cf683ea` | `4bce6bf` | status: NIT-003 merged; NIT-004 ready |
| `d06767e` | `c720656` | NIT-004: out-of-range handling for huge canonical array indices |
| `d2afc1d` | `8f28460` | NIT-002: strict domain models, safe parsing and schema snapshots |
| `d3227a3` | `52d3ad9` | decisions: NIT-007 review outcome (F1 ruling) |
| `d357037` | `a932781` | NIT-013B: AR-4 freeze dossier; reviewer follow-ups; methodology record fixes |
| `d5999d7` | `a90bcff` | status: peers identified; assignments issued |
| `d68df60` | `bf46552` | status: NIT-002 merged; NIT-003 and NIT-011B started |
| `d8c491a` | `2190704` | Merge runner shared-backend mode (reviewed by nitelos-14: APPROVE) |
| `d945626` | `959a815` | NIT-008 phase B: num2words in the local extra (SmolVLM processor requirement) |
| `d997177` | `2140f60` | NIT-001: locate uv via UV env var for Linux runs |
| `de32fe3` | `cdf2925` | deps: add eval extra (numpy, scipy) for NIT-011/012 |
| `e00794a` | `a2d1920` | Merge infra: CI full-offline and packaging jobs (doc 12) |
| `e00f9b1` | `a5ca050` | status: NIT-011A review findings |
| `e029aa8` | `03b8c63` | status: NIT-009 merged; venv incident |
| `e191746` | `04ba094` | NIT-008 phase B: torchvision in the local extra (processor-requiring, pre-authorized) |
| `e288289` | `17f5cf4` | status: NIT-004 review, NIT-005 started, NIT-010 design |
| `e63c667` | `b19c142` | decisions: G3 unreachable after ruled round; D3 commissioned |
| `e715dfd` | `d55212a` | NIT-013B: final-run reports on the sealed tree + G8 summary and checklist close-out |
| `e7b3a69` | `b5a7954` | Merge final runs: sealed-tree benchmark reports, G8 summary, ADR-013 audit records (pre-AR-5 verified by nitelos-14) |
| `e863318` | `1200097` | Merge NIT-008 adapter design specification (A1-A7 accepted by orchestrator) |
| `e955974` | `fb30662` | NIT-008: record the prompt-v1 CPU smoke run (G3 failed, 0/11 valid) |
| `ea4462f` | `015bb75` | NIT-008: SmolVLM adapter design specification |
| `ea4aa6e` | `4462fe0` | release-prep: audit the lock with --no-deps (pinned-only; resolvable without the torch index) |
| `ead8f09` | `3684449` | ADR-011: VerificationResult.request_id is nullable on input errors only |
| `ebe25d7` | `e5a1921` | NIT-008: pass the artifact mapping to verify (it builds the store) |
| `edec9a9` | `41c238c` | Merge NIT-013B: preflight fix per ruling + dev-split benchmark records (reviewed by nitelos-f2: APPROVE) |
| `ef0f602` | `d9aa4c5` | audit: reviewer 1 (nitelos-14) final-test annotation audit |
| `f04a519` | `241bbbc` | Merge NIT-014: developer documentation and honest offline demo (reviewed; merge-time update verified) |
| `f0ba219` | `4eaaa75` | NIT-014: developer documentation and the honest offline demo |
| `f1140e3` | `e22b912` | NIT-008: sort sanity-script imports |
| `f15cbef` | `f0b75a8` | decisions: NIT-014 review outcome |
| `f93e4d8` | `acda794` | NIT-010: pin benchmark eol to LF and make oracle derivation byte-stable |
| `fc03f38` | `408c3a2` | NIT-013B: SUMMARY precision fixes from pre-AR-5 review |
| `fc5da2e` | `d93f47a` | Merge branch 'integration/v0.1' into nit/007-backend-boundary |
| `fc7e278` | `c233bb3` | NIT-006: AR-2 fixes — submit under state lock, strict dev-reraise env, public partial-results limitation |
