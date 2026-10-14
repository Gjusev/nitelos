"""Pure metric computation over evaluation case records (NIT-011 part B).

Authority: docs/planning/06-evaluation-methodology.md - "Metric definitions" (every row),
"Ground truth and annotation" (outcome_truth / evidence_sufficiency / expected decision),
and the null rules shared with part A: an empty denominator yields a null value plus an
``undefined_reason`` - never 0 and never NaN. Positive class is success: TP = success
decision with success truth, FP = success with failure truth; only decisive outcomes with
binary truth count toward the confusion table. Unknown-oracle cases are excluded only from
binary-truth metrics and remain in execution, abstention and sufficiency reporting.

Status/decision/score types come from the merged Nitelos schemas (NIT-002); they are not
redefined here. Wilson 95% intervals for the descriptive binomial proportions reuse part A
(``nitelos.evaluation.statistics``), which stays importable without the eval extra.

This module is deliberately numpy/scipy-free: rates, nearest-rank latency percentiles and
probability metrics (Brier, log loss, ECE) are pure ``math``. Probability metrics apply only
to an ``uncalibrated_probability`` score whose ``target`` names the expected binary event
and only to records with binary oracle truth; anything else is not_applicable with a reason,
and a ``null`` score is never ranked or read as zero. These values are never calibrated and
no threshold is fitted. Calibration fitting, threshold optimisation, leaderboards and report
file I/O are out of scope (NIT-012 and later).

Interpretations of underspecified text (conservative readings):

- latency cold/warm series contain ok executions only; the all-attempts series additionally
  includes error cases (doc 06: "include errors in all-attempt series");
- the nearest-rank percentile method (rank = ceil(p/100 * n)) is used for median and p95,
  so the median of an even-length series is its lower middle;
- ``calibrated_probability`` scores are treated like any other non-probability kind
  (v0.1 validates no calibration), giving ``score_kind_not_probability``;
- conformance requires all three expected fields on a record and compares status, decision
  and the full ordered reason-code tuple for exact equality.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

from nitelos.evaluation.statistics import Interval, wilson_interval
from nitelos.schemas import Decision, ExecutionStatus, Score, ScoreKind

__all__ = [
    "BinReport",
    "CaseRecord",
    "EvidenceSufficiency",
    "InvarianceReport",
    "LabeledPair",
    "MetricRecord",
    "MetricReport",
    "OutcomeCounts",
    "OutcomeTruth",
    "ProbabilityReport",
    "SensitivityReport",
    "breakdowns",
    "compute_metrics",
    "counterfactual_sensitivity",
    "irrelevant_change_invariance",
    "probability_metrics",
]

_DECISIVE = (Decision.SUCCESS, Decision.FAILURE)
_PROBABILITY_KIND = ScoreKind.UNCALIBRATED_PROBABILITY
_LOG_EPSILON = 1e-12
_ECE_BINS = 10


class OutcomeTruth(StrEnum):
    """Oracle outcome label; ``unknown`` never becomes a negative (doc 06)."""

    SUCCESS = "success"
    FAILURE = "failure"
    UNKNOWN = "unknown"


class EvidenceSufficiency(StrEnum):
    """Whether the evidence view could in principle decide the outcome."""

    SUFFICIENT = "sufficient"
    INSUFFICIENT = "insufficient"
    CONTRADICTORY = "contradictory"


@dataclass(frozen=True)
class CaseRecord:
    """One completed benchmark case as observed by the runner (produced by NIT-012).

    Fields: ``case_id`` unique case identifier; ``group_id`` leakage group (template
    lineage, counterfactual siblings, ...); ``primary_family`` scenario family (S01..S15);
    ``scopes`` scope tags reported in breakdowns; ``split`` and ``backend_id`` name the
    run arm; ``execution_status``/``decision`` follow the result contract (decision is
    null exactly on errors); ``reason_codes`` are the result-level codes; the three
    ``expected_*`` fields carry the conformance oracle where determinable (all three or
    none); ``outcome_truth`` is the oracle label; ``evidence_sufficiency`` is the
    independent sufficiency label; ``score`` is the backend-reported score or None;
    ``model_invoked`` records whether a model actually ran; ``elapsed_ms`` is the
    per-case monotonic wall time; ``cold`` marks cold-start executions;
    ``emitted_refs``/``valid_refs`` count reference-validity inputs measured before
    validator rejection.
    """

    case_id: str
    group_id: str
    primary_family: str
    scopes: tuple[str, ...]
    split: str
    backend_id: str
    execution_status: ExecutionStatus
    decision: Decision | None
    reason_codes: tuple[str, ...]
    outcome_truth: OutcomeTruth
    evidence_sufficiency: EvidenceSufficiency
    elapsed_ms: float
    expected_execution_status: ExecutionStatus | None = None
    expected_decision: Decision | None = None
    expected_reason_codes: tuple[str, ...] | None = None
    score: Score | None = None
    model_invoked: bool = False
    cold: bool = False
    emitted_refs: int = 0
    valid_refs: int = 0


@dataclass(frozen=True)
class MetricRecord:
    """One named rate: value with explicit numerator/denominator or an undefined reason.

    ``interval`` carries the 95% Wilson interval from part A for count-based rates
    (descriptive binomial proportions per doc 06); it is None when the value is undefined.
    """

    name: str
    value: float | None
    numerator: int | None
    denominator: int | None
    undefined_reason: str | None = None
    interval: Interval | None = None


@dataclass(frozen=True)
class OutcomeCounts:
    """Raw counts first (doc 06): N = E + B + O and O = A + D hold as identities."""

    n: int
    e: int
    b: int
    o: int
    a: int
    d: int
    tp: int
    fp: int
    tn: int
    fn: int
    n_positive: int
    n_negative: int
    unknown_truth: int
    insufficient_or_contradictory: int
    unsafe_acceptances: int
    conformance_cases: int
    conformance_matches: int
    emitted_refs: int
    valid_refs: int
    model_invoked: int

    @property
    def n_k(self) -> int:
        """Cases with binary oracle truth (K in doc 06)."""
        return self.n_positive + self.n_negative

    @property
    def d_binary(self) -> int:
        """Decisive results with binary truth; the TP/FP/TN/FN denominator."""
        return self.tp + self.fp + self.tn + self.fn

    def __repr__(self) -> str:
        return (
            f"OutcomeCounts(n={self.n}, e={self.e}, b={self.b}, o={self.o}, a={self.a}, d={self.d}, "
            f"tp={self.tp}, fp={self.fp}, tn={self.tn}, fn={self.fn})"
        )


@dataclass(frozen=True)
class LatencyStats:
    """Nearest-rank median/p95 of one latency series, with its size."""

    n: int
    median: float | None
    p95: float | None
    undefined_reason: str | None = None


@dataclass(frozen=True)
class LatencyReport:
    """Cold and warm series (ok executions) plus an all-attempts series with errors."""

    cold: LatencyStats
    warm: LatencyStats
    all_attempts: LatencyStats


@dataclass(frozen=True)
class MetricReport:
    """Counts plus every scalar metric row for one set of case records."""

    counts: OutcomeCounts
    metrics: tuple[MetricRecord, ...]
    latency: LatencyReport


@dataclass(frozen=True)
class BinReport:
    """One fixed ECE bin: count, mean predicted probability, empirical frequency."""

    index: int
    count: int
    mean_predicted: float | None
    empirical_frequency: float | None


@dataclass(frozen=True)
class ProbabilityReport:
    """Brier/log-loss/ECE over applicable scores, or a not_applicable reason.

    Applicable records have an ``uncalibrated_probability`` score whose target equals the
    expected event and binary oracle truth. Values are uncalibrated by construction and
    must never be reported as calibrated; curves and thresholds are not applicable.
    """

    n_used: int
    brier: float | None
    log_loss: float | None
    ece: float | None
    bins: tuple[BinReport, ...]
    not_applicable_reason: str | None


@dataclass(frozen=True)
class SensitivityReport:
    """Counterfactual sensitivity: both sides match their expected decisions."""

    matched: int
    complete: int
    errors: int
    unknowns: int
    value: float | None
    undefined_reason: str | None = None


@dataclass(frozen=True)
class InvarianceReport:
    """Irrelevant-change invariance plus correctness (against constant-answer rewards)."""

    same_decision: int
    correct_same_decision: int
    complete: int
    errors: int
    unknowns: int
    value: float | None
    correctness: float | None
    undefined_reason: str | None = None


@dataclass(frozen=True)
class LabeledPair:
    """A paired comparison (counterfactual or irrelevant-edit) with expected decisions."""

    base: CaseRecord
    variant: CaseRecord
    expected_base: Decision
    expected_variant: Decision


# ---------------------------------------------------------------------------
# validation
# ---------------------------------------------------------------------------


def _validate_record(record: CaseRecord) -> None:
    if record.execution_status == ExecutionStatus.OK:
        if record.decision is None:
            raise ValueError(f"case {record.case_id}: ok execution requires a decision")
    elif record.decision is not None:
        raise ValueError(f"case {record.case_id}: decision must be null on {record.execution_status!s}")
    if not math.isfinite(record.elapsed_ms) or record.elapsed_ms < 0:
        raise ValueError(f"case {record.case_id}: elapsed_ms must be finite and nonnegative")
    if record.valid_refs < 0 or record.emitted_refs < 0 or record.valid_refs > record.emitted_refs:
        raise ValueError(f"case {record.case_id}: valid_refs must be within 0..emitted_refs")


def _validate_records(records: Sequence[CaseRecord]) -> None:
    seen: set[str] = set()
    for record in records:
        _validate_record(record)
        if record.case_id in seen:
            raise ValueError(f"duplicate case id: {record.case_id}")
        seen.add(record.case_id)


# ---------------------------------------------------------------------------
# counting and scalar metrics
# ---------------------------------------------------------------------------


def _expected_triple(
    record: CaseRecord,
) -> tuple[ExecutionStatus, Decision | None, tuple[str, ...]] | None:
    """The conformance oracle where fully determinable, else None.

    All three expected fields must be present; an ``ok`` expectation additionally requires
    a non-null expected decision, while error expectations legitimately determine null.
    """
    status = record.expected_execution_status
    codes = record.expected_reason_codes
    decision = record.expected_decision
    if status is None or codes is None:
        return None
    if status == ExecutionStatus.OK and decision is None:
        return None
    return status, decision, codes


def _count(records: Sequence[CaseRecord]) -> OutcomeCounts:
    e = b = o = a = d = tp = fp = tn = fn = 0
    n_positive = n_negative = unknown_truth = 0
    insufficient = unsafe = 0
    conformance_cases = conformance_matches = emitted = valid = invoked = 0
    for record in records:
        status = record.execution_status
        if status == ExecutionStatus.INPUT_ERROR:
            e += 1
        elif status == ExecutionStatus.BACKEND_ERROR:
            b += 1
        else:
            o += 1
            if record.decision == Decision.ABSTAINED:
                a += 1
            else:
                d += 1
        if record.outcome_truth == OutcomeTruth.SUCCESS:
            n_positive += 1
        elif record.outcome_truth == OutcomeTruth.FAILURE:
            n_negative += 1
        else:
            unknown_truth += 1
        if record.evidence_sufficiency != EvidenceSufficiency.SUFFICIENT:
            insufficient += 1
            if status == ExecutionStatus.OK and record.decision == Decision.SUCCESS:
                unsafe += 1
        expected = _expected_triple(record)
        if expected is not None:
            conformance_cases += 1
            expected_status, expected_decision, expected_codes = expected
            if (
                record.execution_status == expected_status
                and record.decision == expected_decision
                and tuple(record.reason_codes) == tuple(expected_codes)
            ):
                conformance_matches += 1
        if record.decision in _DECISIVE and status == ExecutionStatus.OK:
            if record.outcome_truth == OutcomeTruth.SUCCESS:
                if record.decision == Decision.SUCCESS:
                    tp += 1
                else:
                    fn += 1
            elif record.outcome_truth == OutcomeTruth.FAILURE:
                if record.decision == Decision.SUCCESS:
                    fp += 1
                else:
                    tn += 1
        emitted += record.emitted_refs
        valid += record.valid_refs
        invoked += int(record.model_invoked)
    return OutcomeCounts(
        n=len(records),
        e=e,
        b=b,
        o=o,
        a=a,
        d=d,
        tp=tp,
        fp=fp,
        tn=tn,
        fn=fn,
        n_positive=n_positive,
        n_negative=n_negative,
        unknown_truth=unknown_truth,
        insufficient_or_contradictory=insufficient,
        unsafe_acceptances=unsafe,
        conformance_cases=conformance_cases,
        conformance_matches=conformance_matches,
        emitted_refs=emitted,
        valid_refs=valid,
        model_invoked=invoked,
    )


def _rate(name: str, numerator: int, denominator: int, reason: str) -> MetricRecord:
    """Rate with Wilson interval, or null value plus reason on an empty denominator."""
    if denominator == 0:
        return MetricRecord(name, None, numerator, 0, reason)
    return MetricRecord(
        name, numerator / denominator, numerator, denominator, None, wilson_interval(numerator, denominator)
    )


def _nearest_rank(sorted_values: Sequence[float], percentile: float) -> float:
    rank = math.ceil(percentile / 100 * len(sorted_values))
    return sorted_values[rank - 1]


def _latency_stats(values: Sequence[float]) -> LatencyStats:
    if not values:
        return LatencyStats(0, None, None, "no_cases")
    ordered = sorted(values)
    return LatencyStats(len(ordered), _nearest_rank(ordered, 50), _nearest_rank(ordered, 95))


def _latency(records: Sequence[CaseRecord]) -> LatencyReport:
    ok_cold: list[float] = []
    ok_warm: list[float] = []
    everything: list[float] = []
    for record in records:
        everything.append(record.elapsed_ms)
        if record.execution_status == ExecutionStatus.OK:
            (ok_cold if record.cold else ok_warm).append(record.elapsed_ms)
    return LatencyReport(_latency_stats(ok_cold), _latency_stats(ok_warm), _latency_stats(everything))


def compute_metrics(records: Sequence[CaseRecord]) -> MetricReport:
    """Counts (identities N=E+B+O, O=A+D) and every scalar metric row of doc 06.

    Conditional coverage is named ``conditional_coverage_d_over_o`` and must always be
    reported alongside overall coverage, never alone. Raises ValueError for structurally
    invalid records (illegal status/decision pair, duplicate case ids, bad elapsed/refs).
    """
    _validate_records(records)
    counts = _count(records)
    metrics = (
        _rate("execution_success_rate", counts.o, counts.n, "no_scheduled_cases"),
        _rate("input_error_rate", counts.e, counts.n, "no_scheduled_cases"),
        _rate("backend_error_rate", counts.b, counts.n, "no_scheduled_cases"),
        _rate("overall_coverage", counts.d, counts.n, "no_scheduled_cases"),
        _rate("binary_label_coverage", counts.d_binary, counts.n_k, "no_binary_truth_cases"),
        _rate("conditional_coverage_d_over_o", counts.d, counts.o, "no_ok_executions"),
        _rate("abstention_rate_over_n", counts.a, counts.n, "no_scheduled_cases"),
        _rate("abstention_rate_over_o", counts.a, counts.o, "no_ok_executions"),
        _rate("decisive_accuracy", counts.tp + counts.tn, counts.d_binary, "no_decisive_binary_results"),
        _rate("selective_risk", counts.fp + counts.fn, counts.d_binary, "no_decisive_binary_results"),
        _rate("end_to_end_correct_decision_rate", counts.tp + counts.tn, counts.n_k, "no_binary_truth_cases"),
        _rate("false_acceptance_rate", counts.fp, counts.n_negative, "no_negative_truth_cases"),
        _rate("decisive_negative_far", counts.fp, counts.fp + counts.tn, "no_decisive_negative_predictions"),
        _rate("false_rejection_rate", counts.fn, counts.n_positive, "no_positive_truth_cases"),
        _rate("decisive_positive_frr", counts.fn, counts.fn + counts.tp, "no_decisive_positive_predictions"),
        _rate("success_precision", counts.tp, counts.tp + counts.fp, "no_decisive_success_predictions"),
        _rate("success_recall", counts.tp, counts.n_positive, "no_positive_truth_cases"),
        _rate("failure_precision", counts.tn, counts.tn + counts.fn, "no_decisive_failure_predictions"),
        _rate("failure_recall", counts.tn, counts.n_negative, "no_negative_truth_cases"),
        _rate(
            "unsafe_acceptance_insufficient_evidence",
            counts.unsafe_acceptances,
            counts.insufficient_or_contradictory,
            "no_insufficient_or_contradictory_cases",
        ),
        _rate(
            "policy_conformance_accuracy",
            counts.conformance_matches,
            counts.conformance_cases,
            "no_conformance_cases",
        ),
        _rate("reference_validity", counts.valid_refs, counts.emitted_refs, "no_emitted_references"),
    )
    return MetricReport(counts, metrics, _latency(records))


def breakdowns(records: Sequence[CaseRecord]) -> dict[str, dict[str, MetricReport]]:
    """Raw counts then metrics by split, family, scope tag and backend (doc 06).

    A record carrying several scope tags appears under each of them; family uses
    ``primary_family`` only. Bucket order follows first appearance in the input.
    """
    _validate_records(records)
    buckets: dict[str, dict[str, list[CaseRecord]]] = {
        "split": {},
        "family": {},
        "scope": {},
        "backend": {},
    }
    for record in records:
        buckets["split"].setdefault(record.split, []).append(record)
        buckets["family"].setdefault(record.primary_family, []).append(record)
        for tag in record.scopes:
            buckets["scope"].setdefault(tag, []).append(record)
        buckets["backend"].setdefault(record.backend_id, []).append(record)
    return {
        dimension: {key: compute_metrics(group) for key, group in grouped.items()}
        for dimension, grouped in buckets.items()
    }


# ---------------------------------------------------------------------------
# probability metrics
# ---------------------------------------------------------------------------


def _applicable_scores(
    records: Sequence[CaseRecord], expected_target: str
) -> tuple[list[tuple[float, int]], str | None]:
    """(probability, y) pairs plus None, or an empty list plus the not-applicable reason."""
    if all(record.score is None for record in records):
        return [], "no_scores"
    if not any(record.score is not None and record.score.kind == _PROBABILITY_KIND for record in records):
        return [], "score_kind_not_probability"
    if not any(
        record.score is not None
        and record.score.kind == _PROBABILITY_KIND
        and record.score.target == expected_target
        for record in records
    ):
        return [], "score_target_mismatch"
    pairs: list[tuple[float, int]] = []
    for record in records:
        score = record.score
        if (
            score is not None
            and score.kind == _PROBABILITY_KIND
            and score.target == expected_target
            and record.outcome_truth != OutcomeTruth.UNKNOWN
        ):
            pairs.append((score.value, 1 if record.outcome_truth == OutcomeTruth.SUCCESS else 0))
    if not pairs:
        return [], "no_binary_truth_cases"
    return pairs, None


def probability_metrics(records: Sequence[CaseRecord], *, expected_target: str) -> ProbabilityReport:
    """Brier score, clipped log loss and 10-bin count-weighted ECE (doc 06).

    Only ``uncalibrated_probability`` scores whose ``target`` equals EXPECTED_TARGET on
    records with binary oracle truth contribute. Log loss clips probabilities to
    [1e-12, 1 - 1e-12]; ECE uses 10 fixed equal-width bins weighted by bin count. Empty
    bins report null mean/frequency. The values are uncalibrated; risk-coverage curves and
    thresholds are not applicable in v0.1.
    """
    _validate_records(records)
    pairs, reason = _applicable_scores(records, expected_target)
    if reason is not None:
        return ProbabilityReport(0, None, None, None, (), reason)
    brier_total = 0.0
    log_loss_total = 0.0
    bin_counts = [0] * _ECE_BINS
    bin_p_total = [0.0] * _ECE_BINS
    bin_y_total = [0] * _ECE_BINS
    for probability, y in pairs:
        brier_total += (probability - y) ** 2
        # Per-operand clipping bounds each term at -ln(epsilon) exactly; clipping p first
        # and then computing 1 - p would reintroduce cancellation error near p = 1.
        if y == 1:
            log_loss_total += -math.log(max(probability, _LOG_EPSILON))
        else:
            log_loss_total += -math.log(max(1.0 - probability, _LOG_EPSILON))
        index = min(int(probability * _ECE_BINS), _ECE_BINS - 1)
        bin_counts[index] += 1
        bin_p_total[index] += probability
        bin_y_total[index] += y
    n_used = len(pairs)
    bins = tuple(
        BinReport(
            index=index,
            count=bin_counts[index],
            mean_predicted=bin_p_total[index] / bin_counts[index] if bin_counts[index] else None,
            empirical_frequency=bin_y_total[index] / bin_counts[index] if bin_counts[index] else None,
        )
        for index in range(_ECE_BINS)
    )
    ece = sum(
        bin_report.count
        / n_used
        * abs((bin_report.mean_predicted or 0.0) - (bin_report.empirical_frequency or 0.0))
        for bin_report in bins
        if bin_report.count
    )
    return ProbabilityReport(
        n_used=n_used,
        brier=brier_total / n_used,
        log_loss=log_loss_total / n_used,
        ece=ece,
        bins=bins,
        not_applicable_reason=None,
    )


# ---------------------------------------------------------------------------
# paired metrics
# ---------------------------------------------------------------------------


def _classify_pair(pair: LabeledPair) -> str:
    """'complete', 'error' or 'unknown' for one pair."""
    if (
        pair.base.execution_status != ExecutionStatus.OK
        or pair.variant.execution_status != ExecutionStatus.OK
    ):
        return "error"
    if pair.base.decision not in _DECISIVE or pair.variant.decision not in _DECISIVE:
        return "unknown"
    return "complete"


def counterfactual_sensitivity(pairs: Sequence[LabeledPair]) -> SensitivityReport:
    """Both sides match the pair's expected decisions / complete labeled pairs (doc 06).

    Complete pairs executed ok and decided decisively on both sides; pairs with an error
    on either side count in ``errors`` and undecided pairs in ``unknowns``, both reported
    separately and excluded from the denominator.
    """
    matched = complete = errors = unknowns = 0
    for pair in pairs:
        _validate_record(pair.base)
        _validate_record(pair.variant)
        state = _classify_pair(pair)
        if state == "error":
            errors += 1
        elif state == "unknown":
            unknowns += 1
        else:
            complete += 1
            if pair.base.decision == pair.expected_base and pair.variant.decision == pair.expected_variant:
                matched += 1
    value = matched / complete if complete else None
    return SensitivityReport(
        matched=matched,
        complete=complete,
        errors=errors,
        unknowns=unknowns,
        value=value,
        undefined_reason=None if complete else "no_complete_labeled_pairs",
    )


def irrelevant_change_invariance(pairs: Sequence[LabeledPair]) -> InvarianceReport:
    """Same decision across an irrelevant-edit pair / complete pairs, plus correctness.

    Correctness counts pairs whose shared decision equals the expected decision, so a
    constant-answer backend cannot score by never changing its mind. Both members must
    carry the same expected decision (ValueError otherwise, since a differing expectation
    is not an irrelevant edit).
    """
    for pair in pairs:
        if pair.expected_base != pair.expected_variant:
            raise ValueError("invariance pairs require identical expected decisions on both members")
    same = correct = complete = errors = unknowns = 0
    for pair in pairs:
        _validate_record(pair.base)
        _validate_record(pair.variant)
        state = _classify_pair(pair)
        if state == "error":
            errors += 1
        elif state == "unknown":
            unknowns += 1
        else:
            complete += 1
            if pair.base.decision == pair.variant.decision:
                same += 1
                if pair.base.decision == pair.expected_base:
                    correct += 1
    return InvarianceReport(
        same_decision=same,
        correct_same_decision=correct,
        complete=complete,
        errors=errors,
        unknowns=unknowns,
        value=same / complete if complete else None,
        correctness=correct / complete if complete else None,
        undefined_reason=None if complete else "no_complete_labeled_pairs",
    )
