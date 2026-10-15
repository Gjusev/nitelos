# Reviewer 2 (fresh agent) — final-test annotation audit summary

- Date: 2026-10-15
- Scope: all 60 review packets in `benchmarks/synthetic_v1/review-packets/`, judged only from packet contents (objective, criteria, rendered PNGs, fixture state, proposed labels).
- Total: **60 cases — 44 agree, 16 disagree.**
- Per-case verdicts: `r2.jsonl` in this directory.

## Key interpretive fact

The packets never state what evidence each view receives. The S06 packets'
rationale ("the image-only view withholds it and abstains", cases 587af9b8 /
8771b647 / b77b375c / c5d4e603) establishes the working semantics I applied:
**visual view = images only; assertion view = fixture state/assertions.** Most
disagreements are cases where the visual-view expectation does not follow from
the image under those semantics.

## Disagreements (16)

S08 — renders contradict the "empty evidence view" labels (4):
1. `0417742f` — green "Record saved" banner for CI-0150; abstain + "empty evidence view" rationale contradicts the image; banner arguably supports the criterion.
2. `0e415022` — same as above for CJ-0160.
3. `3e0cccf0` — red "Record rejected" banner plainly refutes the completion-banner criterion; visual should be failure, evidence sufficient.
4. `91a387bf` — same as above for CL-0180.

S01 — visual success claimed but the backend-record criterion is not decidable from the image (4):
5. `13f58a97` 6. `7b182b3d` 7. `9a1b04de` 8. `e8f4265a` — images show a success banner + job details only, no backend record; under image-only semantics the visual view should abstain, not succeed (mirror image of the S06 abstains).

S11 — same flaw, plus self-contradictory images (4):
9. `551d9609` 10. `72a39098` 11. `90db5d91` 12. `d85eac08` — ledger record not visible in image; images contain a green "Transfer complete" banner AND an "Agent summary: transfer FAILED" line; visual success is not derivable from image-only evidence → abstain.

S04 ledger=failed — visual failure/refuted claimed but nothing in the image refutes anything (2):
13. `14db4858` 14. `b91a3673` — image shows a success "Payment sent" banner; the ledger is invisible to the image-only view, so the visual view should abstain exactly as the ledger=missing twins (015a1a0c, 13d54eb1) do.

S07 — internally inconsistent treatment of the "criterion names the wrong record" construct (2):
15. `de6871d7` (subject_mismatch) — page names CC-0170, so the "names CC-0999" criterion is refuted on its face, yet labeled abstain/unknown while the structurally identical wrong_id packets (474376a2, 6d1da7a6) are labeled failure/CRITERION_REFUTED. Both treatments cannot be right.
16. `f4467e8a` (subject_mismatch) — outcome_truth=failure directly contradicts its own rationale ("unknown, not failure") and its twin de6871d7 (unknown). Should be unknown.

## Cases I would label unknown

- `0417742f`, `0e415022` — expected_visual: does a green "Record saved" banner count as a "completion banner"? If yes → visual success; the wording mismatch makes it genuinely ambiguous; keep unknown pending adjudication.
- S07 family (474376a2, 6d1da7a6 vs de6871d7, f4467e8a) — the disputed per-view decisions and outcome_truth should stay unknown until the family-wide convention (refute vs subject-mismatch-abstain) is fixed.

## Systematic findings

1. **Visual-view expectations track ground truth, not image evidence.** In every S01/S11 success case and the S04 ledger=failed cases, the expected visual decision equals outcome_truth even though the refuting/supporting external-record evidence is not in the image; the mirrored S06 cases correctly abstain. Effect: visual-view labels are truth-leaking, inflating agreement between the visual decision and the gold outcome.
2. **S08 labels ignore the rendered banner entirely** ("empty evidence view" rationales while images contain decisive banners), suggesting the label derivation and the renderer disagree about what the evidence view contains.
3. **S07 has two incompatible conventions** for the same observable (wrong_id vs subject_mismatch), plus one self-contradictory packet (f4467e8a).
4. No directional bias toward success or failure overall; the bias is toward *decisiveness* — abstention is under-used in the visual view when truth is known, and over-used in S08.

## Packet-quality issues that made judging hard

- 10 packets have a **blank rationale** (06a56bc5, 14db4858, 37519544, 474376a2, 5ec9bee0, 6d1da7a6, 803337ee, 9fa57b64, b91a3673, ef0a1454).
- Evidence-view composition (what each view receives) is never stated in the packets; it had to be inferred from one family's rationale.
- S12 renders put the decisive value in near-illegible micro-text — verifying "unreadable" required zoom-level OCR judgment.
- Minor ID formatting drift ("DX 0161" rendered vs "DX-0161" in criteria).
- REVIEWER-INSTRUCTIONS mention verifying "scope tags", but no packet contains scope tags — nothing to verify for item 6.
