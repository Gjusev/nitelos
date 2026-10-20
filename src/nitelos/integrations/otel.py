"""OpenTelemetry export for verification results (extra ``otel``).

Authority: this module only exports observability data. It never changes a
decision, never installs a tracer provider or exporter, never changes global
OpenTelemetry state and never adds logging handlers. Every attribute value is
an allowlisted code, count, id or duration; raw evidence values, objectives,
subjects, pointers, expected values, error messages and model rationale are
never exported.

Requires the ``otel`` extra. If ``opentelemetry`` is missing, importing this
module raises :class:`ImportError` naming the install command
(``pip install "nitelos[otel]"``).

Semantic-convention attributes (``gen_ai.evaluation.*``) follow
opentelemetry-semantic-conventions 0.66b1 incubating definitions; they are
pinned as string constants (the semconv package is a dev/test dependency, not
a runtime one) and may change with future semconv releases.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, Any

from nitelos import __version__
from nitelos.schemas import _ID_RE, VerificationResult

try:
    from opentelemetry import trace
    from opentelemetry.trace import Status, StatusCode
    from opentelemetry.util.types import AttributeValue
except ImportError as _exc:  # pragma: no cover - exercised via subprocess test
    raise ImportError(
        'nitelos.integrations.otel requires the otel extra; install it with: pip install "nitelos[otel]"'
    ) from None

if TYPE_CHECKING:  # pragma: no cover
    from opentelemetry.trace import Tracer

GEN_AI_EVALUATION_NAME_SEMCONV = "gen_ai.evaluation.name"
GEN_AI_EVALUATION_SCORE_LABEL_SEMCONV = "gen_ai.evaluation.score.label"

SEMCONV_VERSION_PINNED = "0.66b1 (incubating)"

_MAX_COLLECTORS = 64
_SPAN_NAME = "nitelos.verify"


def _validated_collectors(
    collector_ids: Sequence[str],
    collector_durations_ms: Mapping[str, float] | None,
) -> tuple[tuple[str, ...], tuple[float, ...] | None]:
    ids = tuple(collector_ids)
    if len(ids) > _MAX_COLLECTORS:
        raise ValueError(f"at most {_MAX_COLLECTORS} collector ids are allowed, got {len(ids)}")
    for collector_id in ids:
        if not isinstance(collector_id, str) or _ID_RE.fullmatch(collector_id) is None:
            raise ValueError("collector ids must match the nitelos ID pattern")
    if len(set(ids)) != len(ids):
        raise ValueError("collector ids must be unique")
    if collector_durations_ms is None:
        return ids, None
    if set(collector_durations_ms) != set(ids):
        raise ValueError("collector durations must cover exactly the given collector ids")
    durations: list[float] = []
    for collector_id in ids:
        value = collector_durations_ms[collector_id]
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError("collector durations must be numbers")
        duration = float(value)
        if not math.isfinite(duration) or duration < 0:
            raise ValueError("collector durations must be finite and non-negative")
        durations.append(duration)
    return ids, tuple(durations)


def span_attributes(
    result: VerificationResult,
    *,
    collector_ids: Sequence[str] = (),
    collector_durations_ms: Mapping[str, float] | None = None,
) -> dict[str, AttributeValue]:
    """Build the allowlisted span attributes for one verification result.

    Pure function and the single source of the attribute allowlist; hosts that
    run their own spans should reuse it. ``nitelos.evidence.cited_count`` is
    the number of distinct evidence ids cited by the returned criteria (the
    evidence the decision actually touched). ``collector_durations_ms``, when
    given, must cover exactly ``collector_ids``; durations are exported as a
    parallel tuple in ``collector_ids`` order.

    Raises :class:`ValueError` for invalid collector inputs.
    """
    ids, durations = _validated_collectors(collector_ids, collector_durations_ms)
    limitations = set(result.diagnostics.limitations)
    for criterion in result.criteria:
        limitations.update(criterion.limitations)
    attrs: dict[str, AttributeValue] = {
        "nitelos.execution_status": str(result.execution_status),
        "nitelos.verification_id": result.verification_id,
        "nitelos.criteria.count": len(result.criteria),
        "nitelos.criteria.supported": sum(1 for c in result.criteria if str(c.state) == "supported"),
        "nitelos.criteria.refuted": sum(1 for c in result.criteria if str(c.state) == "refuted"),
        "nitelos.criteria.unknown": sum(1 for c in result.criteria if str(c.state) == "unknown"),
        "nitelos.reason_codes": tuple(sorted({str(code) for code in result.reason_codes})),
        "nitelos.limitation_codes": tuple(sorted(limitations)),
        "nitelos.backend.id": result.diagnostics.backend.id,
        "nitelos.backend.version": result.diagnostics.backend.version,
        "nitelos.elapsed_ms": float(result.diagnostics.elapsed_ms),
        "nitelos.collector.ids": ids,
        "nitelos.evidence.cited_count": len(
            {ref.evidence_id for c in result.criteria for ref in c.evidence_refs}
        ),
    }
    if durations is not None:
        attrs["nitelos.collector.durations_ms"] = durations
    if result.decision is not None:
        attrs["nitelos.decision"] = str(result.decision)
    if str(result.execution_status) == "ok":
        decision_value = result.decision
        assert decision_value is not None  # noqa: S101 - schema guarantees decision on ok
        attrs[GEN_AI_EVALUATION_NAME_SEMCONV] = _SPAN_NAME
        attrs[GEN_AI_EVALUATION_SCORE_LABEL_SEMCONV] = str(decision_value)
    if result.error is not None:
        attrs["nitelos.error.code"] = str(result.error.code)
    return attrs


def verify_traced(
    verifier: Any,
    request: Any,
    artifacts: Mapping[str, Any] | None = None,
    *,
    tracer: Tracer | None = None,
    collector_ids: Sequence[str] = (),
    collector_durations_ms: Mapping[str, float] | None = None,
) -> VerificationResult:
    """Run ``verifier.verify`` under exactly one ``nitelos.verify`` span.

    The result is returned unchanged; export never influences a decision. If
    ``verify`` raises, the span records the exception type only (never the
    message; no ``record_exception`` call) and the exception propagates;
    ``KeyboardInterrupt`` and ``SystemExit`` propagate untouched. With
    ``tracer=None`` a tracer comes from the current global provider; nitelos
    never installs a provider itself.

    Raises :class:`ValueError` for invalid collector inputs before any span
    starts.
    """
    _validated_collectors(collector_ids, collector_durations_ms)
    active_tracer = tracer if tracer is not None else trace.get_tracer("nitelos", __version__)
    # start_span + manual end (not the context manager): the SDK context
    # manager auto-records propagating exceptions with their full message,
    # which would leak exception text into status and events.
    span = active_tracer.start_span(_SPAN_NAME)
    try:
        result = verifier.verify(request, artifacts=artifacts)
    except (KeyboardInterrupt, SystemExit):
        span.end()
        raise
    except Exception as exc:
        span.set_status(Status(StatusCode.ERROR, type(exc).__name__))
        span.end()
        raise
    if not isinstance(result, VerificationResult):
        span.end()
        raise TypeError("verifier.verify must return a VerificationResult")
    for key, value in span_attributes(
        result,
        collector_ids=collector_ids,
        collector_durations_ms=collector_durations_ms,
    ).items():
        span.set_attribute(key, value)
    if str(result.execution_status) != "ok":
        error = result.error
        assert error is not None  # noqa: S101 - schema guarantees error when not ok
        span.set_status(Status(StatusCode.ERROR, str(error.code)))
    span.end()
    return result
