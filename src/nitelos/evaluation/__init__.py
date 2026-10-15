"""Nitelos evaluation package: statistics, metrics and the benchmark runner.

Importing this package pulls no optional dependencies. numpy/scipy (the `eval` extra)
load lazily inside ``nitelos.evaluation.statistics`` functions, so core environments
without the extra stay light and ``import nitelos`` remains side-effect free. The
runner (NIT-012) is likewise dependency-free and offline.
"""

from __future__ import annotations

from nitelos.evaluation.runner import (
    compare_reports,
    evaluate,
    load_evaluation_manifest,
)

__all__ = ["compare_reports", "evaluate", "load_evaluation_manifest"]
