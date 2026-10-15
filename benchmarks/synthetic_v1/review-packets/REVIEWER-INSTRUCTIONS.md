# Reviewer instructions — nitelos-synthetic-v1 final-test audit

You are one of two independent human reviewers for the 60 final-test cases. You must
not have authored the generator or the oracle derivation, and you never see any model
output. Work through the packets in this directory; each references the rendered
images, the fixture state record and the derived labels for one case.

For each case, verify six items and mark each APPROVED or FIX (with a note):
1. The rendered image matches the state record (the scene shows what the state says).
2. Each criterion's expected per-view finding matches what a careful reader derives.
3. The outcome_truth label is correct for the state.
4. The evidence_sufficiency label is correct.
5. The expected decision and reason codes per view are correct.
6. The scope tags are correct.

Do not consult the other reviewer while working. When you finish, record your
annotator ID, the date and your per-case verdicts on the packet sign-off lines; the
adjudicator resolves disagreements, and unresolved cases keep unknown labels and are
reported. Estimated effort: three to four minutes per case.
