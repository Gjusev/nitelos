"""MET-01..04 / STAT: metric computation over case records (NIT-011 part B, doc 06).

Authority: docs/planning/06-evaluation-methodology.md "Metric definitions" (every row),
"Ground truth and annotation", "Statistical plan". All expected numbers in these tests are
hand-computed literals from fully worked confusion tables; tolerance is 1e-10 relative.
Positive class is success: TP = success decision with success truth, FP = success with
failure truth; only decisive outcomes with binary truth count toward the confusion table.
"""

from __future__ import annotations

import math
from dataclasses import replace
from typing import Any

import pytest

from nitelos.evaluation.metrics import (
    CaseRecord,
    EvidenceSufficiency,
    LabeledPair,
    MetricRecord,
    MetricReport,
    OutcomeTruth,
    breakdowns,
    compute_metrics,
    counterfactual_sensitivity,
    irrelevant_change_invariance,
    probability_metrics,
)
from nitelos.schemas import Decision, ExecutionStatus, Score, ScoreKind

OK = ExecutionStatus.OK
INPUT_ERROR = ExecutionStatus.INPUT_ERROR
BACKEND_ERROR = ExecutionStatus.BACKEND_ERROR
SUCCESS = Decision.SUCCESS
FAILURE = Decision.FAILURE
ABSTAINED = Decision.ABSTAINED
T_SUCCESS = OutcomeTruth.SUCCESS
T_FAILURE = OutcomeTruth.FAILURE
T_UNKNOWN = OutcomeTruth.UNKNOWN
SUFFICIENT = EvidenceSufficiency.SUFFICIENT
INSUFFICIENT = EvidenceSufficiency.INSUFFICIENT
CONTRADICTORY = EvidenceSufficiency.CONTRADICTORY
AGG = "ALL_CRITERIA_SUPPORTED"
REFUTED = "CRITERION_REFUTED"
INSUF = "INSUFFICIENT_EVIDENCE"


def _rec(case_id: str, **over: Any) -> CaseRecord:
    values: dict[str, Any] = {
        "case_id": case_id,
        "group_id": f"g-{case_id}",
        "primary_family": "S01",
        "scopes": ("external",),
        "split": "dev",
        "backend_id": "smolvlm",
        "execution_status": OK,
        "decision": SUCCESS,
        "reason_codes": (AGG,),
        "outcome_truth": T_SUCCESS,
        "evidence_sufficiency": SUFFICIENT,
        "elapsed_ms": 10.0,
    }
    values.update(over)
    return CaseRecord(**values)


def _err(case_id: str, **over: Any) -> CaseRecord:
    over.setdefault("execution_status", INPUT_ERROR)
    over["decision"] = None
    over.setdefault("reason_codes", ("INVALID_SCHEMA",))
    return _rec(case_id, **over)


def _metric(report: MetricReport, name: str) -> MetricRecord:
    for record in report.metrics:
        if record.name == name:
            return record
    pytest.fail(f"metric {name!r} was not produced")
    raise AssertionError  # pragma: no cover - pytest.fail raises


def _check_rate(report: MetricReport, name: str, value: float, numerator: int, denominator: int) -> None:
    record = _metric(report, name)
    assert record.value == pytest.approx(value, rel=1e-10, abs=1e-12), name
    assert record.numerator == numerator, name
    assert record.denominator == denominator, name
    assert record.undefined_reason is None, name
    assert record.interval is not None, name
    # part A Wilson bounds can overshoot the point estimate by float noise at k=0/k=n
    assert record.interval.low is not None
    assert record.interval.low <= value + 1e-12, name
    assert record.interval.high is not None
    assert record.interval.high >= value, name


def _check_undefined(report: MetricReport, name: str, reason: str) -> None:
    record = _metric(report, name)
    assert record.value is None, name
    assert record.undefined_reason == reason, (name, record.undefined_reason)


def _score(
    value: float, target: str = "criterion_satisfied", kind: ScoreKind = ScoreKind.UNCALIBRATED_PROBABILITY
) -> Score:
    return Score(kind=kind, value=value, target=target)


def _met01_records() -> list[CaseRecord]:
    """Hand-worked 20-record table.

    8 truth-success, 8 truth-failure, 4 truth-unknown; 3 input errors, 2 backend errors,
    4 abstentions, 11 decisive; TP=4 FP=1 TN=3 FN=1 (9 decisive with binary truth).
    Latency: cold oks [100, 102]; warm oks 13 values 12..38; errors 50..58.
    Conformance oracle on six records (c12 mismatches): 5/6.
    """
    conformance = {
        "c01": (OK, SUCCESS, (AGG,)),
        "c03": (OK, FAILURE, (REFUTED,)),
        "c05": (OK, ABSTAINED, (INSUF,)),
        "c10": (INPUT_ERROR, None, ("INVALID_SCHEMA",)),
        "c12": (OK, FAILURE, (REFUTED,)),  # actual: input_error -> mismatch
        "c15": (BACKEND_ERROR, None, ("BACKEND_EXCEPTION",)),
    }
    return [
        replace(
            record,
            expected_execution_status=conformance[record.case_id][0],
            expected_decision=conformance[record.case_id][1],
            expected_reason_codes=conformance[record.case_id][2],
        )
        if record.case_id in conformance
        else record
        for record in [
            _rec("c01", elapsed_ms=100.0, cold=True, emitted_refs=1, valid_refs=1),  # TP
            _rec("c02", elapsed_ms=12.0, emitted_refs=1, valid_refs=1),  # TP
            _rec(
                "c03",
                decision=FAILURE,
                reason_codes=(REFUTED,),
                elapsed_ms=14.0,
                emitted_refs=1,
                valid_refs=1,
            ),  # FN
            _rec(
                "c04", evidence_sufficiency=INSUFFICIENT, elapsed_ms=16.0, emitted_refs=1, valid_refs=0
            ),  # TP, unsafe
            _rec("c05", decision=ABSTAINED, reason_codes=(INSUF,), elapsed_ms=18.0),  # abstained
            _rec(
                "c06",
                outcome_truth=T_FAILURE,
                decision=FAILURE,
                reason_codes=(REFUTED,),
                elapsed_ms=102.0,
                cold=True,
                emitted_refs=1,
                valid_refs=1,
            ),  # TN
            _rec(
                "c07",
                outcome_truth=T_FAILURE,
                decision=FAILURE,
                reason_codes=(REFUTED,),
                elapsed_ms=22.0,
                emitted_refs=1,
                valid_refs=1,
            ),  # TN
            _rec(
                "c08",
                outcome_truth=T_FAILURE,
                evidence_sufficiency=CONTRADICTORY,
                elapsed_ms=24.0,
                emitted_refs=1,
                valid_refs=1,
            ),  # FP, unsafe
            _rec(
                "c09", outcome_truth=T_FAILURE, decision=ABSTAINED, reason_codes=(INSUF,), elapsed_ms=26.0
            ),  # abstained
            _err(
                "c10", outcome_truth=T_FAILURE, evidence_sufficiency=INSUFFICIENT, elapsed_ms=50.0
            ),  # input error
            _err(
                "c11",
                execution_status=BACKEND_ERROR,
                reason_codes=("BACKEND_EXCEPTION",),
                outcome_truth=T_FAILURE,
                elapsed_ms=52.0,
            ),  # backend error
            _err("c12", elapsed_ms=54.0),  # input error, truth success
            _rec(
                "c13", outcome_truth=T_UNKNOWN, elapsed_ms=28.0, emitted_refs=1, valid_refs=1
            ),  # decisive, no truth
            _rec(
                "c14",
                outcome_truth=T_UNKNOWN,
                evidence_sufficiency=INSUFFICIENT,
                decision=ABSTAINED,
                reason_codes=(INSUF,),
                elapsed_ms=30.0,
            ),
            _err(
                "c15",
                execution_status=BACKEND_ERROR,
                reason_codes=("BACKEND_EXCEPTION",),
                outcome_truth=T_UNKNOWN,
                evidence_sufficiency=CONTRADICTORY,
                elapsed_ms=56.0,
            ),
            _rec(
                "c16",
                outcome_truth=T_UNKNOWN,
                evidence_sufficiency=CONTRADICTORY,
                decision=FAILURE,
                reason_codes=(REFUTED,),
                elapsed_ms=32.0,
                emitted_refs=1,
                valid_refs=1,
            ),  # decisive, no truth
            _rec("c17", elapsed_ms=34.0, emitted_refs=1, valid_refs=1),  # TP
            _rec(
                "c18",
                outcome_truth=T_FAILURE,
                decision=FAILURE,
                reason_codes=(REFUTED,),
                elapsed_ms=36.0,
                emitted_refs=1,
                valid_refs=1,
            ),  # TN
            _err("c19", outcome_truth=T_FAILURE, elapsed_ms=58.0),  # input error
            _rec(
                "c20", decision=ABSTAINED, reason_codes=(INSUF,), elapsed_ms=38.0
            ),  # abstained, truth success
        ]
    ]


_MET01 = compute_metrics(_met01_records())


def test_met01_counts_and_identities() -> None:
    counts = _MET01.counts
    assert counts.n == 20
    assert counts.e == 3
    assert counts.b == 2
    assert counts.o == 15
    assert counts.a == 4
    assert counts.d == 11
    assert counts.n == counts.e + counts.b + counts.o
    assert counts.o == counts.a + counts.d
    assert (counts.tp, counts.fp, counts.tn, counts.fn) == (4, 1, 3, 1)
    assert counts.tp + counts.fp + counts.tn + counts.fn == 9  # decisive with binary truth
    assert counts.n_positive == 8
    assert counts.n_negative == 8
    assert counts.unknown_truth == 4
    assert counts.insufficient_or_contradictory == 6
    assert counts.unsafe_acceptances == 2
    assert counts.emitted_refs == 11
    assert counts.valid_refs == 10
    assert counts.model_invoked == 0


def test_met01_every_rate_with_numerator_and_denominator() -> None:
    report = _MET01
    _check_rate(report, "execution_success_rate", 0.75, 15, 20)
    _check_rate(report, "input_error_rate", 0.15, 3, 20)
    _check_rate(report, "backend_error_rate", 0.1, 2, 20)
    _check_rate(report, "overall_coverage", 0.55, 11, 20)
    _check_rate(report, "binary_label_coverage", 0.5625, 9, 16)
    _check_rate(report, "conditional_coverage_d_over_o", 11.0 / 15.0, 11, 15)
    _check_rate(report, "abstention_rate_over_n", 0.2, 4, 20)
    _check_rate(report, "abstention_rate_over_o", 4.0 / 15.0, 4, 15)
    _check_rate(report, "decisive_accuracy", 7.0 / 9.0, 7, 9)
    _check_rate(report, "selective_risk", 2.0 / 9.0, 2, 9)
    _check_rate(report, "end_to_end_correct_decision_rate", 0.4375, 7, 16)
    _check_rate(report, "false_acceptance_rate", 0.125, 1, 8)
    _check_rate(report, "decisive_negative_far", 0.25, 1, 4)
    _check_rate(report, "false_rejection_rate", 0.125, 1, 8)
    _check_rate(report, "decisive_positive_frr", 0.2, 1, 5)
    _check_rate(report, "success_precision", 0.8, 4, 5)
    _check_rate(report, "success_recall", 0.5, 4, 8)
    _check_rate(report, "failure_precision", 0.75, 3, 4)
    _check_rate(report, "failure_recall", 0.375, 3, 8)
    _check_rate(report, "unsafe_acceptance_insufficient_evidence", 2.0 / 6.0, 2, 6)
    _check_rate(report, "policy_conformance_accuracy", 5.0 / 6.0, 5, 6)
    _check_rate(report, "reference_validity", 10.0 / 11.0, 10, 11)


def test_met01_latency_nearest_rank_cold_warm_all() -> None:
    latency = _MET01.latency
    assert (latency.cold.n, latency.cold.median, latency.cold.p95) == (2, 100.0, 102.0)
    assert (latency.warm.n, latency.warm.median, latency.warm.p95) == (13, 26.0, 38.0)
    # all-attempts includes the five error cases: 20 values, 10th = 32, 19th = 100
    assert (latency.all_attempts.n, latency.all_attempts.median, latency.all_attempts.p95) == (
        20,
        32.0,
        100.0,
    )


def test_met01_conformance_details() -> None:
    assert _MET01.counts.conformance_cases == 6
    assert _MET01.counts.conformance_matches == 5  # c12 expects ok/failure, actually input_error


def test_met02_all_abstain_zero_coverage_undefined_risk() -> None:
    records = [
        _rec("a1", decision=ABSTAINED, reason_codes=(INSUF,)),
        _rec("a2", decision=ABSTAINED, reason_codes=(INSUF,), outcome_truth=T_FAILURE),
        _rec("a3", decision=ABSTAINED, reason_codes=(INSUF,), outcome_truth=T_FAILURE),
    ]
    report = compute_metrics(records)
    _check_rate(report, "execution_success_rate", 1.0, 3, 3)
    _check_rate(report, "overall_coverage", 0.0, 0, 3)
    _check_rate(report, "binary_label_coverage", 0.0, 0, 3)
    _check_rate(report, "abstention_rate_over_n", 1.0, 3, 3)
    _check_undefined(report, "decisive_accuracy", "no_decisive_binary_results")
    _check_undefined(report, "selective_risk", "no_decisive_binary_results")
    _check_undefined(report, "decisive_negative_far", "no_decisive_negative_predictions")
    _check_undefined(report, "decisive_positive_frr", "no_decisive_positive_predictions")
    _check_undefined(report, "success_precision", "no_decisive_success_predictions")
    _check_undefined(report, "failure_precision", "no_decisive_failure_predictions")
    _check_rate(report, "end_to_end_correct_decision_rate", 0.0, 0, 3)
    _check_rate(report, "false_acceptance_rate", 0.0, 0, 2)
    _check_rate(report, "false_rejection_rate", 0.0, 0, 1)
    _check_rate(report, "success_recall", 0.0, 0, 1)
    _check_rate(report, "failure_recall", 0.0, 0, 2)


def test_met02_all_errors() -> None:
    records = [_err("e1"), _err("e2", outcome_truth=T_FAILURE)]
    report = compute_metrics(records)
    _check_rate(report, "execution_success_rate", 0.0, 0, 2)
    _check_rate(report, "input_error_rate", 1.0, 2, 2)
    _check_undefined(report, "conditional_coverage_d_over_o", "no_ok_executions")
    _check_undefined(report, "abstention_rate_over_o", "no_ok_executions")
    assert report.latency.cold.n == 0
    assert report.latency.cold.median is None
    assert report.latency.warm.n == 0
    assert report.latency.all_attempts.n == 2
    assert report.latency.all_attempts.median == pytest.approx(10.0)


def test_met02_zero_positives_and_zero_negatives() -> None:
    no_positives = [
        _rec("n1", outcome_truth=T_FAILURE, decision=FAILURE, reason_codes=(REFUTED,)),
        _rec("n2", outcome_truth=T_FAILURE, decision=FAILURE, reason_codes=(REFUTED,)),
        _rec("n3", outcome_truth=T_FAILURE, decision=ABSTAINED, reason_codes=(INSUF,)),
    ]
    report = compute_metrics(no_positives)
    _check_undefined(report, "success_recall", "no_positive_truth_cases")
    _check_undefined(report, "false_rejection_rate", "no_positive_truth_cases")
    _check_undefined(report, "success_precision", "no_decisive_success_predictions")
    _check_rate(report, "failure_precision", 1.0, 2, 2)
    _check_rate(report, "failure_recall", 2.0 / 3.0, 2, 3)
    no_negatives = [
        _rec("p1"),
        _rec("p2", decision=ABSTAINED, reason_codes=(INSUF,)),
    ]
    report_p = compute_metrics(no_negatives)
    _check_undefined(report_p, "failure_recall", "no_negative_truth_cases")
    _check_undefined(report_p, "false_acceptance_rate", "no_negative_truth_cases")
    _check_undefined(report_p, "failure_precision", "no_decisive_failure_predictions")
    _check_rate(report_p, "success_recall", 0.5, 1, 2)


def test_met02_all_unknown_oracle_stays_in_execution_reporting() -> None:
    records = [
        _rec("u1", outcome_truth=T_UNKNOWN),
        _rec("u2", outcome_truth=T_UNKNOWN, decision=ABSTAINED, reason_codes=(INSUF,)),
    ]
    report = compute_metrics(records)
    assert report.counts.unknown_truth == 2
    _check_rate(report, "execution_success_rate", 1.0, 2, 2)
    _check_rate(report, "abstention_rate_over_n", 0.5, 1, 2)
    _check_undefined(report, "binary_label_coverage", "no_binary_truth_cases")
    _check_undefined(report, "decisive_accuracy", "no_decisive_binary_results")
    _check_undefined(report, "end_to_end_correct_decision_rate", "no_binary_truth_cases")
    _check_undefined(report, "false_acceptance_rate", "no_negative_truth_cases")
    _check_undefined(report, "false_rejection_rate", "no_positive_truth_cases")


def test_met02_empty_input_is_all_undefined_never_nan() -> None:
    report = compute_metrics([])
    assert report.counts.n == 0
    for record in report.metrics:
        assert record.value is None, record.name
        assert record.undefined_reason is not None, record.name
    assert report.latency.all_attempts.n == 0
    assert report.latency.all_attempts.median is None


def test_met03_no_scores_not_applicable() -> None:
    records = [_rec("s1"), _rec("s2", outcome_truth=T_FAILURE, decision=FAILURE, reason_codes=(REFUTED,))]
    report = probability_metrics(records, expected_target="criterion_satisfied")
    assert report.not_applicable_reason == "no_scores"
    assert report.brier is None
    assert report.log_loss is None
    assert report.ece is None
    assert report.bins == ()
    assert report.n_used == 0


def test_met04_wrong_target_and_wrong_kind_not_applicable() -> None:
    wrong_target = [_rec("w1", score=_score(0.9, target="other_event"))]
    assert probability_metrics(wrong_target, expected_target="criterion_satisfied").not_applicable_reason == (
        "score_target_mismatch"
    )
    wrong_kind = [
        _rec(
            "w2",
            score=Score(
                kind=ScoreKind.UNCALIBRATED_SCORE, value=4.5, target="criterion_satisfied", scale="0-5"
            ),
        )
    ]
    assert probability_metrics(wrong_kind, expected_target="criterion_satisfied").not_applicable_reason == (
        "score_kind_not_probability"
    )
    calibrated = [
        _rec(
            "w3",
            score=Score(
                kind=ScoreKind.CALIBRATED_PROBABILITY,
                value=0.5,
                target="criterion_satisfied",
                calibration_id="c1",
            ),
        )
    ]
    assert probability_metrics(calibrated, expected_target="criterion_satisfied").not_applicable_reason == (
        "score_kind_not_probability"
    )
    unknown_only = [_rec("w4", outcome_truth=T_UNKNOWN, score=_score(0.5))]
    assert probability_metrics(unknown_only, expected_target="criterion_satisfied").not_applicable_reason == (
        "no_binary_truth_cases"
    )


def test_met04_probability_metrics_hand_computed() -> None:
    # p = [0.9, 0.2, 0.5, 0.8], y = [1, 0, 1, 0]
    records = [
        _rec("p1", score=_score(0.9)),
        _rec("p2", outcome_truth=T_FAILURE, score=_score(0.2)),
        _rec("p3", score=_score(0.5)),
        _rec("p4", outcome_truth=T_FAILURE, score=_score(0.8)),
    ]
    report = probability_metrics(records, expected_target="criterion_satisfied")
    assert report.not_applicable_reason is None
    assert report.n_used == 4
    # Brier = (0.01 + 0.04 + 0.25 + 0.64) / 4
    assert report.brier == pytest.approx(0.235, rel=1e-10)
    # log loss = -(ln .9 + ln .8 + ln .5 + ln .2) / 4
    assert report.log_loss == pytest.approx(0.6577722899915204, rel=1e-10)
    # ECE = (0.2 + 0.5 + 0.8 + 0.1) / 4 over four singleton bins
    assert report.ece == pytest.approx(0.4, rel=1e-10)
    assert len(report.bins) == 10
    expected_nonempty = {
        2: (1, 0.2, 0.0),
        5: (1, 0.5, 1.0),
        8: (1, 0.8, 0.0),
        9: (1, 0.9, 1.0),
    }
    for bin_report in report.bins:
        if bin_report.index in expected_nonempty:
            count, mean_p, freq = expected_nonempty[bin_report.index]
            assert bin_report.count == count
            assert bin_report.mean_predicted == pytest.approx(mean_p, rel=1e-10)
            assert bin_report.empirical_frequency == pytest.approx(freq, rel=1e-10)
        else:
            assert bin_report.count == 0
            assert bin_report.mean_predicted is None
            assert bin_report.empirical_frequency is None


def test_met04_epsilon_clipping_at_extremes() -> None:
    records = [_rec("x1", outcome_truth=T_FAILURE, score=_score(1.0))]
    report = probability_metrics(records, expected_target="criterion_satisfied")
    assert report.brier == pytest.approx(1.0, rel=1e-10)
    assert report.log_loss == pytest.approx(-math.log(1e-12), rel=1e-10)
    assert report.ece == pytest.approx(1.0, rel=1e-10)
    assert report.bins[9].count == 1  # p = 1.0 lands in the last bin
    assert report.bins[0].count == 0


def test_pairs_counterfactual_sensitivity() -> None:
    pairs = [
        LabeledPair(
            base=_rec("k1a"),
            variant=_rec("k1b", decision=FAILURE, reason_codes=(REFUTED,)),
            expected_base=SUCCESS,
            expected_variant=FAILURE,
        ),  # both match
        LabeledPair(
            base=_rec("k2a"), variant=_rec("k2b"), expected_base=SUCCESS, expected_variant=FAILURE
        ),  # variant mismatch
        LabeledPair(
            base=_rec("k3a", decision=ABSTAINED, reason_codes=(INSUF,)),
            variant=_rec("k3b", decision=FAILURE, reason_codes=(REFUTED,)),
            expected_base=SUCCESS,
            expected_variant=FAILURE,
        ),  # undecided
        LabeledPair(
            base=_err("k4a"),
            variant=_rec("k4b", decision=FAILURE, reason_codes=(REFUTED,)),
            expected_base=SUCCESS,
            expected_variant=FAILURE,
        ),  # error
        LabeledPair(
            base=_rec("k5a", decision=FAILURE, reason_codes=(REFUTED,)),
            variant=_rec("k5b", decision=FAILURE, reason_codes=(REFUTED,)),
            expected_base=FAILURE,
            expected_variant=FAILURE,
        ),  # both match
    ]
    report = counterfactual_sensitivity(pairs)
    assert report.matched == 2
    assert report.complete == 3
    assert report.errors == 1
    assert report.unknowns == 1
    assert report.value == pytest.approx(2.0 / 3.0, rel=1e-10)


def test_pairs_irrelevant_change_invariance_with_correctness() -> None:
    pairs = [
        LabeledPair(base=_rec("i1a"), variant=_rec("i1b"), expected_base=SUCCESS, expected_variant=SUCCESS),
        LabeledPair(
            base=_rec("i2a", decision=FAILURE, reason_codes=(REFUTED,)),
            variant=_rec("i2b"),
            expected_base=FAILURE,
            expected_variant=FAILURE,
        ),  # decision changed
        LabeledPair(
            base=_rec("i3a"),
            variant=_rec("i3b", decision=FAILURE, reason_codes=(REFUTED,)),
            expected_base=SUCCESS,
            expected_variant=SUCCESS,
        ),  # decision changed
    ]
    report = irrelevant_change_invariance(pairs)
    assert report.complete == 3
    assert report.same_decision == 1
    assert report.value == pytest.approx(1.0 / 3.0, rel=1e-10)
    assert report.correctness == pytest.approx(1.0 / 3.0, rel=1e-10)  # only i1 is same AND correct
    with pytest.raises(ValueError, match="identical expected decisions"):
        irrelevant_change_invariance(
            [
                LabeledPair(
                    base=_rec("z1"), variant=_rec("z2"), expected_base=SUCCESS, expected_variant=FAILURE
                )
            ]
        )


def test_pairs_empty_and_undefined() -> None:
    sensitivity = counterfactual_sensitivity([])
    assert sensitivity.value is None
    assert sensitivity.undefined_reason == "no_complete_labeled_pairs"
    invariance = irrelevant_change_invariance(
        [LabeledPair(base=_err("y1"), variant=_err("y2"), expected_base=SUCCESS, expected_variant=SUCCESS)]
    )
    assert invariance.value is None
    assert invariance.undefined_reason == "no_complete_labeled_pairs"
    assert invariance.errors == 1


def test_breakdowns_split_family_scope_backend() -> None:
    records = [
        _rec("b1", split="dev", primary_family="S01", backend_id="det", scopes=("external",)),
        _rec(
            "b2",
            split="dev",
            primary_family="S02",
            backend_id="det",
            scopes=("visual",),
            decision=FAILURE,
            reason_codes=(REFUTED,),
            outcome_truth=T_FAILURE,
        ),
        _rec("b3", split="test", primary_family="S01", backend_id="smolvlm", scopes=("external", "visual")),
        _rec(
            "b4",
            split="dev",
            primary_family="S02",
            backend_id="smolvlm",
            scopes=("visual",),
            decision=FAILURE,
            reason_codes=(REFUTED,),
            outcome_truth=T_FAILURE,
        ),
    ]
    report = breakdowns(records)
    assert set(report) == {"split", "family", "scope", "backend"}
    assert report["split"]["dev"].counts.n == 3
    assert report["split"]["dev"].counts.d == 3
    assert _metric(report["split"]["dev"], "execution_success_rate").value == pytest.approx(1.0)
    assert report["split"]["test"].counts.n == 1
    assert report["family"]["S01"].counts.n == 2
    assert report["family"]["S02"].counts.n == 2
    assert report["scope"]["external"].counts.n == 2  # b1, b3
    assert report["scope"]["visual"].counts.n == 3  # b2, b3 carries both tags, b4
    assert report["backend"]["det"].counts.n == 2
    assert report["backend"]["smolvlm"].counts.n == 2
    assert _metric(report["scope"]["visual"], "overall_coverage").value == pytest.approx(1.0)


def test_invalid_records_raise_clear_errors() -> None:
    with pytest.raises(ValueError, match="duplicate case id"):
        compute_metrics([_rec("d1"), _rec("d1")])
    with pytest.raises(ValueError, match="decision"):
        compute_metrics([_rec("d1", decision=None)])
    with pytest.raises(ValueError, match="decision"):
        compute_metrics([_rec("d1", execution_status=INPUT_ERROR, decision=SUCCESS)])
    with pytest.raises(ValueError, match="elapsed"):
        compute_metrics([_rec("d1", elapsed_ms=float("nan"))])
    with pytest.raises(ValueError, match="elapsed"):
        compute_metrics([_rec("d1", elapsed_ms=-1.0)])
    with pytest.raises(ValueError, match="valid_refs"):
        compute_metrics([_rec("d1", emitted_refs=0, valid_refs=1)])


def test_metric_records_are_frozen_with_safe_repr() -> None:
    record = _metric(_MET01, "execution_success_rate")
    with pytest.raises(AttributeError):
        record.value = 0.5  # type: ignore[misc]
    assert "0.75" in repr(record)
    assert "c01" not in repr(_MET01.counts)  # counts repr carries no case ids
