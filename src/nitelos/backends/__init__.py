"""Nitelos backends.

The deterministic assertion evaluator is core and dependency-free; the
optional local model adapter will live in ``nitelos.backends.smolvlm``
(NIT-008) and is never imported from here.
"""

from nitelos.backends.deterministic import (
    DeterministicBackend,
    evaluate_assertion,
    evaluate_reference,
)

__all__ = ["DeterministicBackend", "evaluate_assertion", "evaluate_reference"]
