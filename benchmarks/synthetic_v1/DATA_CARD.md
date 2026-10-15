# DATA CARD — nitelos-synthetic-v1 (NIT-010)

## Purpose

Synthetic authored outcome benchmark for the Nitelos verifier (120 cases: 15 families
x 8, four development and four final-test cases per family from eight disjoint lineage
groups; S13 uses counterfactual and irrelevant-edit pairs as grouping units). License
Apache-2.0 for all authored material. All scenes, names, prefixes and IDs are original
synthetic content; no PII, credentials or third-party assets. Every derived report
must carry the label synthetic.

## Generation

```
python benchmarks/synthetic_v1/tools/generate_benchmark.py
```

No RNG exists anywhere in the generator: every value is a fixed constant or a
deterministic function of (family, group, slot). Fonts are Pillow's bundled default
(`ImageFont.load_default(size=...)`). Case IDs are UUID5 over the fixed namespace
7e1f2a54-6b0d-4c8e-9a3f-5d21c8b40e97; artifact filenames are the first 12 hex characters of the case ID
(plus `-b` for second images). No label, family or scenario word appears in any
model-visible path, filename, request metadata or PNG metadata chunk.

## Declared renderer platform

Regeneration byte-identity is asserted only on the renderer recorded here; on any
other renderer the byte-identity check skips with a reason naming the mismatch.

| Key | Value |
|---|---|
| os | Windows |
| python | 3.12 |
| pillow | 12.3.0 |
| freetype | 2.14.3 |
| zlib | 1.3.1.zlib-ng |

## Layout

- `artifacts/` PNG renders (neutral hex filenames)
- `requests/<case_id>-assertion.json` and `-visual.json` — the two request views
- `oracle/<case_id>.json` — per-case oracle (labels derived by `tools/derive_oracle.py`
  from the state record only, never from pixels or captions)
- `dev.json`, `dev-visual.json`, `test.json`, `test-visual.json` — manifests of 60
- `fixture-collector.json` — host-reviewed external-trust authorization
- `dedup-review.json` — aHash-8x8 (threshold 6 bits) near-duplicate detector log
- `review-packets/` — human-audit packets for the 60 final-test cases
- `freeze.sha256.provisional` — provisional content digest (see Human gate)

## Deduplication

Exact SHA-256 digests are unique across all artifacts by construction and disjoint
from the NIT-008 smoke set. Perceptual near-duplicates are checked with aHash 8x8
(Hamming distance <= 6 of 64 bits) over all pairs as a detector only: same-lineage-
group pairs are factually labeled (S13 pairs share scenes by design); every other hit
is recorded as pending_human_review in `dedup-review.json`. Cross-group hits are
expected to be text-level template variants — the 8x8 hash cannot read text, so
family templates that differ only in rendered words compare close — and the human
dedup reviewer signs the log; nothing is ever deleted automatically.

## Human gate (G4)

Final-test labels are NOT audited until two independent human reviewers plus an
adjudicator, organized by the user, have reviewed the packets in `review-packets/`.
Oracle records carry `annotation_status: pending_human_review` and empty annotator
lists. The freeze tool refuses a final freeze while any final-test record is pending;
`freeze.sha256.provisional` is a clearly labelled provisional digest only. The freeze
happens at AR-4 after the human audit.

## Final-test label audit (ADR-013, 2026-10-15)

**Binding label:** final-test labels audited by two independent AI reviewers
plus adjudication; NO human annotation audit was performed. Human annotation
review remains a precondition for any publication. The audit records
(`audit/r1-summary.md`, `audit/r1.jsonl`, `audit/r2-summary.md`,
`audit/r2.jsonl`) and the adjudication (decisions.md, 2026-10-15) are part of
this dataset; the two adjudicated label changes (S07 subject_mismatch ->
unknown) are noted in the affected review packets. Scientific caveat carried
into all reporting: AI reviewers may share biases a human audit was designed
to catch.

v2 improvement recorded by the adjudication: review packets should state the
per-view evidence composition, so a packet-only reviewer can derive
refuted-vs-subject-mismatch distinctions (the audited packets stand as issued).
