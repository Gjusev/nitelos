"""Pure statistics for evaluation uncertainty (NIT-011 part A).

Authority: docs/planning/06-evaluation-methodology.md - "Statistical plan" (Wilson 95%
intervals, one-sided 95% Clopper-Pearson zero-error bound, group bootstrap with 2,000
replicates and a fixed seed) and the null rules in "Metric definitions": empty denominators
yield null plus ``undefined_reason``, never 0 or NaN.

This module is contract-independent: it must not import Nitelos request/result schemas.
numpy/scipy are imported lazily inside the functions that need them; a missing dependency
raises :class:`EvalExtraRequired` with an installation hint instead of an ImportError at
import time. Wilson intervals and the zero-error Clopper-Pearson bound are pure ``math``
and work without the extra.

Limitations: the Wilson z constant is the exact two-sided 95% value; bootstrap reproducibility
holds for the pinned numpy version, and PCG64 streams are not a cross-version compatibility
promise.
"""

from __future__ import annotations

import importlib
import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

__all__ = [
    "EvalExtraRequired",
    "Interval",
    "clopper_pearson_upper_bound",
    "group_bootstrap",
    "paired_group_bootstrap",
    "wilson_interval",
]

# z for a two-sided 95% Wilson score interval; equals scipy.stats.norm.ppf(0.975), pinned
# as a constant so the interval needs no scipy.
_Z_975 = 1.959963984540054
# Doc 06 statistical plan: group bootstrap with 2,000 replicates.
_DEFAULT_REPLICATES = 2000


class EvalExtraRequired(RuntimeError):
    """A numpy/scipy function is needed but the ``eval`` extra is not installed."""


def _import(name: str) -> Any:
    """Import NAME lazily; missing modules become an actionable EvalExtraRequired."""
    try:
        return importlib.import_module(name)
    except ImportError as exc:
        msg = (
            f"{name} is required for this statistic but is not installed. "
            "Install the evaluation extra, e.g. `uv sync --extra eval` "
            "or `pip install 'nitelos[eval]'`."
        )
        raise EvalExtraRequired(msg) from exc


@dataclass(frozen=True)
class Interval:
    """Numeric statistical result with explicit undefined handling.

    ``value``/``low``/``high`` are plain floats or None; None means undefined, never NaN.
    ``low`` is None for one-sided bounds and when the result is undefined.
    ``undefined_reason`` is a machine code explaining which part is undefined and why.
    For bootstrap results, ``excluded`` counts replicates whose statistic was undefined;
    ``n`` is the total record (or pair) count. The repr is safe: numbers and codes only.
    """

    value: float | None
    low: float | None
    high: float | None
    n: int
    undefined_reason: str | None = None
    excluded: int = 0


def _validate_counts(k: int, n: int) -> None:
    if n < 0:
        raise ValueError(f"n must be nonnegative, got {n}")
    if k < 0 or k > n:
        raise ValueError(f"k must satisfy 0 <= k <= n, got k={k}, n={n}")


def _clean(value: float | None) -> float | None:
    """Map any non-finite float (NaN, +/-inf) to None; valid floats pass through."""
    if value is None or not math.isfinite(value):
        return None
    return value


def wilson_interval(k: int, n: int) -> Interval:
    """Two-sided 95% Wilson score interval for k successes of n.

    Pure math (no eval extra); z is the pinned constant ``_Z_975``. Bounds are clamped to
    [0, 1] only to remove floating-point overshoot at the boundaries (k=0 low, k=n high).
    n == 0 returns an undefined interval with reason ``empty_denominator`` (doc 06).
    """
    _validate_counts(k, n)
    if n == 0:
        return Interval(None, None, None, 0, "empty_denominator")
    z2 = _Z_975 * _Z_975
    denom = n + z2
    center = (k + z2 / 2) / denom
    half = _Z_975 / denom * math.sqrt(k * (n - k) / n + z2 / 4)
    return Interval(k / n, max(0.0, center - half), min(1.0, center + half), n)


def clopper_pearson_upper_bound(k: int, n: int) -> Interval:
    """One-sided 95% Clopper-Pearson upper bound on the error rate for k errors of n.

    k == 0 uses the exact closed form ``1 - 0.05**(1/n)`` (pure math); k > 0 uses
    ``scipy.stats.beta.ppf(0.95, k + 1, n - k)`` and requires the ``eval`` extra.
    ``low`` is None because the bound is one-sided; k == n yields exactly 1.0.
    n == 0 returns an undefined interval with reason ``empty_denominator``.
    """
    _validate_counts(k, n)
    if n == 0:
        return Interval(None, None, None, 0, "empty_denominator")
    if k == 0:
        return Interval(0.0, None, 1.0 - 0.05 ** (1.0 / n), n)
    if k == n:
        return Interval(float(k) / n, None, 1.0, n)
    beta_ppf = _import("scipy.stats").beta.ppf
    return Interval(k / n, None, float(beta_ppf(0.95, k + 1, n - k)), n)


def group_bootstrap[T](
    groups: Sequence[Sequence[T]],
    statistic: Callable[[Sequence[T]], float | None],
    *,
    seed: int,
    replicates: int = _DEFAULT_REPLICATES,
) -> Interval:
    """Percentile bootstrap that resamples whole groups with replacement (doc 06).

    Each replicate draws ``len(groups)`` groups with replacement from a numpy PCG64 stream
    seeded with ``seed``, so counterfactual pairs, template lineages and other clustered
    records stay together; individuals are never split across the sampling boundary.
    The interval is the empirical 2.5/97.5 percentiles (numpy's default linear
    interpolation) over the replicates where the statistic is defined. A replicate whose
    statistic returns None or any non-finite float (NaN, +/-inf) is excluded and counted
    in ``excluded`` - never silently kept as NaN or infinity. If every replicate is
    undefined, the result is undefined with reason ``all_replicates_undefined``.
    ``value`` is the statistic over all records (also None when non-finite) and may
    independently be None. ``n`` counts records.

    Exceptions: ``EvalExtraRequired`` when numpy is missing; ``ValueError`` for
    ``replicates < 1``.
    """
    if replicates < 1:
        raise ValueError(f"replicates must be >= 1, got {replicates}")
    if not groups:
        return Interval(None, None, None, 0, "no_groups")
    units = [list(group) for group in groups]
    total = sum(len(unit) for unit in units)
    np = _import("numpy")
    rng = np.random.default_rng(seed)
    point = _clean(statistic([record for unit in units for record in unit]))
    values: list[float] = []
    excluded = 0
    n_groups = len(units)
    for _ in range(replicates):
        drawn = rng.integers(0, n_groups, size=n_groups)
        sample = [record for index in drawn for record in units[int(index)]]
        estimate = statistic(sample)
        if estimate is None or not math.isfinite(estimate):
            excluded += 1
        else:
            values.append(estimate)
    if not values:
        return Interval(point, None, None, total, "all_replicates_undefined", excluded)
    low, high = np.percentile(values, [2.5, 97.5])
    return Interval(point, float(low), float(high), total, None, excluded)


def paired_group_bootstrap[A, B](
    pair_groups: Sequence[Sequence[tuple[A, B]]],
    statistic: Callable[[Sequence[tuple[A, B]]], float | None],
    *,
    seed: int,
    replicates: int = _DEFAULT_REPLICATES,
) -> Interval:
    """Group bootstrap for comparing two backends on identical case IDs (doc 06).

    Each group holds matched records as ``(arm A, arm B)`` pairs; every replicate draws
    the same group indices for both arms, so pairs never separate - the statistic receives
    one replicate's concatenated pairs and typically computes a difference of per-arm
    statistics. Undefined handling, ``excluded`` counting and ``n`` (total pairs) follow
    :func:`group_bootstrap`.
    """
    return group_bootstrap(pair_groups, statistic, seed=seed, replicates=replicates)
