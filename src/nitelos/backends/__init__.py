"""Nitelos backends.

The deterministic assertion evaluator is core and dependency-free; the
optional local model adapter will live in ``nitelos.backends.smolvlm``
(NIT-008) and is never imported from here. ``base`` defines the Backend
protocol, capabilities and the reusable finding validator (NIT-007).
"""

from nitelos.backends.base import (
    Backend,
    BackendCapabilities,
    BackendOutputError,
    InferenceContext,
    PreparedVisualCriterion,
    validate_backend_finding,
)
from nitelos.backends.deterministic import DeterministicBackend, evaluate_assertion, evaluate_reference
from nitelos.schemas import BackendDescriptor, BackendFinding, Score

__all__ = [
    "Backend",
    "BackendCapabilities",
    "BackendDescriptor",
    "BackendFinding",
    "BackendOutputError",
    "DeterministicBackend",
    "InferenceContext",
    "PreparedVisualCriterion",
    "Score",
    "evaluate_assertion",
    "evaluate_reference",
    "validate_backend_finding",
]
