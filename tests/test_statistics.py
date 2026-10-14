"""STAT-01: pure evaluation statistics (NIT-011 part A, doc 06 statistical plan).

Authority: docs/planning/06-evaluation-methodology.md - Wilson intervals, one-sided
Clopper-Pearson zero-error bound, seeded group bootstrap (2,000 replicates), and the null
rules: empty denominators yield null plus undefined_reason, never 0/NaN. scipy/numpy tests
skip only when the eval extra is genuinely absent (doc 12 core-only environments).
"""

from __future__ import annotations

import importlib
import math
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from nitelos.evaluation import statistics

ROOT = Path(__file__).resolve().parents[1]


def _numpy_or_skip() -> Any:
    try:
        import numpy
    except ImportError:
        pytest.skip("numpy (eval extra) not installed in this environment")
    return numpy


def _scipy_stats_or_skip() -> Any:
    try:
        from scipy import stats
    except ImportError:
        pytest.skip("scipy (eval extra) not installed in this environment")
    return stats


def _all_finite(res: statistics.Interval) -> bool:
    parts = (res.value, res.low, res.high)
    return all(math.isfinite(x) for x in parts if x is not None)


def test_importing_evaluation_does_not_pull_numpy_or_scipy() -> None:
    code = (
        "import sys\n"
        "import nitelos.evaluation as ev\n"
        "assert ev.__doc__, 'evaluation package needs a docstring'\n"
        "heavy = [m for m in ('numpy', 'scipy') if m in sys.modules]\n"
        "assert not heavy, heavy\n"
    )
    proc = subprocess.run([sys.executable, "-c", code], check=False, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout == ""


@pytest.mark.parametrize(
    ("k", "n", "low", "high"),
    [
        (0, 10, 0.0, 0.27753279986288926),
        (5, 10, 0.236593090512564, 0.7634069094874361),
        (10, 10, 0.7224672001371109, 1.0),
        (3, 8, 0.13684428582359737, 0.6942576053973728),
    ],
)
def test_stat01_wilson_endpoints_are_hand_known(k: int, n: int, low: float, high: float) -> None:
    res = statistics.wilson_interval(k, n)
    assert res.value == pytest.approx(k / n, abs=1e-12)
    assert res.low == pytest.approx(low, abs=1e-10)
    assert res.high == pytest.approx(high, abs=1e-10)
    assert res.n == n
    assert res.undefined_reason is None
    assert res.excluded == 0
    assert _all_finite(res)


def test_stat01_zero_n_is_undefined_never_nan() -> None:
    for res in (statistics.wilson_interval(0, 0), statistics.clopper_pearson_upper_bound(0, 0)):
        assert res.value is None
        assert res.low is None
        assert res.high is None
        assert res.n == 0
        assert res.undefined_reason == "empty_denominator"


@pytest.mark.parametrize(
    ("n", "expected"),
    [
        (1, 0.95),
        (10, 0.2588655508930523),
        (298, 0.010002432437677733),
        (299, 0.009969146792899286),
    ],
)
def test_stat01_zero_error_upper_bound_exact_formula(n: int, expected: float) -> None:
    res = statistics.clopper_pearson_upper_bound(0, n)
    assert res.value == pytest.approx(0.0)
    assert res.low is None
    assert res.high == pytest.approx(1.0 - 0.05 ** (1.0 / n), abs=1e-12)
    assert res.high == pytest.approx(expected, abs=1e-12)
    assert res.undefined_reason is None
    assert _all_finite(res)


def test_stat01_about_299_zero_errors_needed_below_one_percent() -> None:
    below = statistics.clopper_pearson_upper_bound(0, 299).high
    above = statistics.clopper_pearson_upper_bound(0, 298).high
    assert below is not None
    assert below < 0.01
    assert above is not None
    assert above > 0.01


@pytest.mark.parametrize(("k", "n"), [(1, 40), (3, 20)])
def test_stat01_positive_error_bound_matches_scipy_beta(k: int, n: int) -> None:
    stats = _scipy_stats_or_skip()
    res = statistics.clopper_pearson_upper_bound(k, n)
    expected = float(stats.beta.ppf(0.95, k + 1, n - k))
    assert res.high == pytest.approx(expected, rel=1e-12)
    assert res.value == pytest.approx(k / n)
    assert res.low is None
    assert _all_finite(res)


@pytest.mark.parametrize(("k", "n"), [(5, 5), (7, 7)])
def test_stat01_all_errors_bound_is_exactly_one(k: int, n: int) -> None:
    # scipy's beta.ppf is degenerate for n - k == 0; the bound is exactly 1 by definition.
    res = statistics.clopper_pearson_upper_bound(k, n)
    assert res.high == 1.0
    assert res.value == 1.0
    assert res.low is None
    assert res.undefined_reason is None


def test_stat01_invalid_counts_raise_value_error() -> None:
    for bad in ((1, 0), (-1, 10), (11, 10)):
        k, n = bad
        with pytest.raises(ValueError, match=r"n must be nonnegative|k must satisfy"):
            statistics.wilson_interval(k, n)
        with pytest.raises(ValueError, match=r"n must be nonnegative|k must satisfy"):
            statistics.clopper_pearson_upper_bound(k, n)


def _demo_groups() -> list[list[tuple[int, float]]]:
    # Six groups of tagged records: (group_tag, value); sizes vary per group.
    return [
        [(1, 0.0), (1, 0.2), (1, 0.1)],
        [(2, 0.9), (2, 0.7)],
        [(3, 0.5)],
        [(4, 0.4), (4, 0.6), (4, 0.5), (4, 0.55)],
        [(5, 1.0), (5, 0.8)],
        [(6, 0.15), (6, 0.25)],
    ]


def _mean(records: list[tuple[int, float]]) -> float:
    return sum(v for _, v in records) / len(records)


def test_stat02_bootstrap_reproducible_and_seed_sensitive() -> None:
    _numpy_or_skip()
    first = statistics.group_bootstrap(_demo_groups(), _mean, seed=20261014)
    again = statistics.group_bootstrap(_demo_groups(), _mean, seed=20261014)
    other = statistics.group_bootstrap(_demo_groups(), _mean, seed=1)
    assert (first.low, first.high) == (again.low, again.high)
    assert (first.low, first.high) != (other.low, other.high)
    assert first.excluded == 0
    assert first.n == 14
    assert first.value == pytest.approx(_mean([r for g in _demo_groups() for r in g]))
    assert _all_finite(first)
    assert first.low is not None
    assert first.high is not None
    assert first.low <= first.high


def test_stat02_bootstrap_resamples_whole_groups() -> None:
    _numpy_or_skip()
    sizes = {tag: len(g) for g in _demo_groups() for tag, _ in g}
    captured: list[list[tuple[int, float]]] = []

    def instrumented(records: list[tuple[int, float]]) -> float:
        captured.append(records)
        return _mean(records)

    res = statistics.group_bootstrap(_demo_groups(), instrumented, seed=7, replicates=300)
    assert len(captured) == 301  # 300 replicates plus the full-sample point estimate
    for replicate in captured[1:]:
        by_tag: dict[int, list[float]] = {}
        for tag, value in replicate:
            by_tag.setdefault(tag, []).append(value)
        for tag, values in by_tag.items():
            assert len(values) % sizes[tag] == 0, "group split across sampling units"
        total_records = sum(len(v) for v in by_tag.values())
        assert total_records == sum(sizes[t] * (len(v) // sizes[t]) for t, v in by_tag.items())
    assert res.excluded == 0
    assert _all_finite(res)


def test_stat02_bootstrap_undefined_replicates_are_excluded_and_counted() -> None:
    _numpy_or_skip()
    poison_tag = 3

    def undefined_on_poison(records: list[tuple[int, float]]) -> float | None:
        return None if any(tag == poison_tag for tag, _ in records) else _mean(records)

    res = statistics.group_bootstrap(_demo_groups(), undefined_on_poison, seed=11, replicates=400)
    assert 0 < res.excluded < 400
    assert res.low is not None
    assert res.high is not None
    assert _all_finite(res)
    assert res.undefined_reason is None


def test_stat02_bootstrap_nan_statistics_count_as_undefined() -> None:
    _numpy_or_skip()
    poison_tag = 3

    def nan_on_poison(records: list[tuple[int, float]]) -> float:
        return math.nan if any(tag == poison_tag for tag, _ in records) else _mean(records)

    res = statistics.group_bootstrap(_demo_groups(), nan_on_poison, seed=11, replicates=400)
    assert 0 < res.excluded < 400
    assert _all_finite(res)


def test_stat02_bootstrap_all_undefined_is_reported_not_nan() -> None:
    _numpy_or_skip()
    res = statistics.group_bootstrap(_demo_groups(), lambda records: None, seed=3, replicates=50)
    assert res.excluded == 50
    assert res.low is None
    assert res.high is None
    assert res.value is None
    assert res.undefined_reason == "all_replicates_undefined"


def test_stat02_bootstrap_default_is_2000_replicates() -> None:
    _numpy_or_skip()
    calls: list[int] = []

    def counting(records: list[tuple[int, float]]) -> float:
        calls.append(len(records))
        return _mean(records)

    statistics.group_bootstrap(_demo_groups(), counting, seed=5)
    assert len(calls) == 2001  # 2,000 replicates plus one point estimate


def test_stat02_bootstrap_no_groups_and_bad_replicates() -> None:
    _numpy_or_skip()
    empty = statistics.group_bootstrap([], _mean, seed=1)
    assert empty.undefined_reason == "no_groups"
    with pytest.raises(ValueError, match="replicates must be >= 1"):
        statistics.group_bootstrap(_demo_groups(), _mean, seed=1, replicates=0)


def _paired_demo_groups() -> list[list[tuple[tuple[str, float], tuple[str, float]]]]:
    # Groups of matched (arm A, arm B) records; case IDs align across arms.
    return [
        [(("c1", 1.0), ("c1", 0.0)), (("c2", 0.0), ("c2", 0.0))],
        [(("c3", 1.0), ("c3", 1.0)), (("c4", 1.0), ("c4", 0.0))],
        [(("c5", 0.0), ("c5", 0.0)), (("c6", 1.0), ("c6", 1.0)), (("c7", 1.0), ("c7", 0.0))],
    ]


def _mean_difference(pairs: list[tuple[tuple[str, float], tuple[str, float]]]) -> float:
    return sum(a[1] for a, _ in pairs) / len(pairs) - sum(b[1] for _, b in pairs) / len(pairs)


def test_stat02_paired_bootstrap_keeps_pairs_aligned() -> None:
    _numpy_or_skip()

    def guarded(pairs: list[tuple[tuple[str, float], tuple[str, float]]]) -> float | None:
        if any(a[0] != b[0] for a, b in pairs):
            return None  # misaligned pair would be excluded and visible
        return _mean_difference(pairs)

    res = statistics.paired_group_bootstrap(_paired_demo_groups(), guarded, seed=42, replicates=500)
    assert res.excluded == 0, "a replicate received a misaligned pair"
    assert res.n == 7
    assert res.low is not None
    assert res.high is not None
    assert res.value == pytest.approx(_mean_difference([p for g in _paired_demo_groups() for p in g]))
    again = statistics.paired_group_bootstrap(_paired_demo_groups(), guarded, seed=42, replicates=500)
    assert (again.low, again.high) == (res.low, res.high)
    assert _all_finite(res)


def test_stat03_missing_eval_extra_raises_actionable_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_import = importlib.import_module

    def deny(name: str) -> Any:
        if name in ("numpy", "scipy.stats"):
            raise ImportError(f"No module named {name!r}")
        return real_import(name)

    monkeypatch.setattr(importlib, "import_module", deny)
    assert statistics.wilson_interval(5, 10).high is not None  # pure math needs no extra
    assert statistics.clopper_pearson_upper_bound(0, 10).high is not None  # k=0 closed form
    with pytest.raises(statistics.EvalExtraRequired) as cp_err:
        statistics.clopper_pearson_upper_bound(1, 10)
    assert "eval" in str(cp_err.value)
    with pytest.raises(statistics.EvalExtraRequired) as boot_err:
        statistics.group_bootstrap(_demo_groups(), _mean, seed=1)
    assert "numpy" in str(boot_err.value)
    assert "eval" in str(boot_err.value)
