"""Nitelos evaluation package: statistics, metrics and the benchmark runner.

Importing this package pulls no optional dependencies. numpy/scipy (the `eval` extra)
load lazily inside ``nitelos.evaluation.statistics`` functions, so core environments
without the extra stay light and ``import nitelos`` remains side-effect free.
"""
