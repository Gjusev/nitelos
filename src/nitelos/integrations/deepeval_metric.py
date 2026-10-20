"""The DeepEval outcome metric (plan F10, NIT-026; extra ``deepeval``).

Wraps one nitelos verification as a deterministic DeepEval metric: the score
is exactly 1.0 (decision success) or 0.0 (everything else) — no fractional
scores, no thresholds. Abstention is surfaced as ``is_successful`` false with
a reason that starts with ``abstained`` (and carries the verifier reason
codes); an execution error (input/backend) is a different failure with the
error code and an explicit "decision is null" note. Neither is ever scored
as a pass. Reasons carry criterion ids and reason codes only — never evidence
values.

Requires the ``deepeval`` extra. Importing this module without the package
raises :class:`ImportError` naming the install command
(``pip install "nitelos[deepeval]"``). Importing ``nitelos`` itself never
loads deepeval (BND-01).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

try:
    from deepeval.metrics import BaseMetric  # type: ignore[attr-defined]  # deepeval 2.9.3 re-exports without __all__
except ImportError as _exc:  # pragma: no cover - exercised via subprocess test
    raise ImportError(
        "nitelos.integrations.deepeval_metric requires the deepeval extra; "
        'install it with: pip install "nitelos[deepeval]"'
    ) from None

__all__ = ["NitelosOutcomeMetric"]


class NitelosOutcomeMetric(BaseMetric):
    """Score a verification outcome: 1.0 success, 0.0 anything else.

    ``result_provider`` is called once per ``measure`` and must return a
    ``VerificationResult`` (typically a closure that runs collectors and the
    verifier). ``test_case`` is accepted and ignored: the outcome comes from
    the verification, never from model output.
    """

    def __init__(self, result_provider: Callable[[], Any]) -> None:
        self._result_provider = result_provider
        self.score: float | None = None
        self.reason: str | None = None
        self.success: bool | None = None
        # BaseMetric.__name__ is a read-only property in deepeval 2.9.3
        # deriving the class name; do not assign it.

    def measure(self, test_case: Any = None, **_kwargs: Any) -> float:
        result = self._result_provider()
        if not hasattr(result, "execution_status"):
            self.score = 0.0
            self.success = False
            self.reason = "result_provider returned a non-VerificationResult"
            return self.score
        status = str(result.execution_status)
        if status != "ok":
            code = result.error.code.value if result.error is not None else "unknown"
            self.score = 0.0
            self.success = False
            self.reason = f"execution {status} ({code}); decision is null"
            return self.score
        decision = str(result.decision) if result.decision is not None else "abstained"
        if decision == "success":
            self.score = 1.0
            self.success = True
            self.reason = "decision success: all criteria supported"
            return self.score
        self.score = 0.0
        self.success = False
        if decision == "failure":
            failed = [c.criterion_id for c in result.criteria if str(c.state) == "refuted"]
            self.reason = f"decision failure: criteria {', '.join(failed) or '-'} refuted"
        else:
            unknown = [c for c in result.criteria if str(c.state) == "unknown"]
            codes = sorted({code for c in unknown for code in c.reason_codes})
            self.reason = f"abstained: {', '.join(codes) if codes else 'no criteria decided'}"
        return self.score

    def is_successful(self) -> bool:
        """The abstract success method (deepeval 2.9.3 declares it as a
        method, not a property); False before ``measure``."""
        return bool(self.success)

    @property
    def __name__(self) -> str:
        """The metric name (supertype returns the generic "Base Metric")."""
        return "NitelosOutcomeMetric"
