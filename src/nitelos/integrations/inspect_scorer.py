"""Inspect AI scorer for nitelos verification (plan F8, extra ``nitelos[inspect]``).

Bridges the Inspect AI evaluation framework to the nitelos verifier: a scorer
factory (:func:`nitelos_scorer`) that builds a :class:`VerificationRequest`
from SAMPLE METADATA and the final state the task captured, runs the
:class:`Verifier` and returns an Inspect :class:`Score`.

Contract (documented, versioned by this module):
- sample metadata (``state.metadata``): ``nitelos_criteria`` (a list of
  criterion documents in v0.1 wire form; each criterion carries its own
  subject), ``nitelos_checkpoint_id`` and an optional ``nitelos_request_id``.
  Missing
  criteria raise :class:`KeyError` — a task misconfiguration should be loud,
  not a silent score.
- final state (``state.store``): the evidence list under
  :data:`NITELOS_EVIDENCE_KEY` (v0.1 wire form), written by the task's
  solver/tools (for example a collector-backed tool). No evidence is a
  legitimate state — and so is a citation the agent could not satisfy:
  criteria citations are filtered to the ids actually present, so an empty
  store or a dangling citation abstains with MISSING_EVIDENCE instead of
  crashing the eval. Malformed agent-written evidence scores "A" with
  INVALID_SCHEMA; only eval-author mistakes (broken criteria documents) stay
  loud.
- ``as_of`` is the scoring moment (UTC); captured evidence is subject to the
  criteria's ``max_age_seconds`` freshness exactly as in core nitelos.

Score mapping: success → ``"C"``, failure → ``"I"``, everything else
(abstained, input_error, backend_error) → :data:`VALUE_ABSTAIN` ``"A"`` — a
value OUTSIDE the CORRECTNESS pair, so Inspect's ``accuracy()`` excludes it
from the numerator and the denominator (verified in the test suite: C, I and
A score accuracy 0.5). Score metadata carries ``nitelos.decision``,
``nitelos.execution_status``, ``nitelos.reason_codes``,
``nitelos.limitation_codes`` and ``nitelos.evidence_fingerprints`` (the
sha256 digests of the request's evidence items); the explanation is built
from safe codes only. Raw evidence values never enter the Score.

Authority: the scorer never weakens a request — it uses the verifier's own
parsing and evaluation unchanged. Requires the ``inspect`` extra; importing
this module without it raises :class:`ImportError` naming the install
command (``pip install "nitelos[inspect]"``). Pinned against
inspect-ai 0.3.x.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Protocol, cast

from nitelos import TrustBinding, Verifier, parse_request
from nitelos.schemas import VerificationResult

try:
    from inspect_ai.scorer import Score, metric, scorer
except ImportError as _exc:  # pragma: no cover - exercised via subprocess test
    raise ImportError(
        "nitelos.integrations.inspect_scorer requires the inspect extra; "
        'install it with: pip install "nitelos[inspect]"'
    ) from None

if TYPE_CHECKING:  # pragma: no cover
    pass


class Scorer(Protocol):
    """Structural stand-in for inspect's Scorer: callable on (state, target).

    Defined locally (never imported) so the module type-checks identically
    with and without the extra — inspect's own Scorer is Any under the
    core-env mypy override.
    """

    async def __call__(self, state: Any, target: Any) -> Any: ...


# inspect's decorators are typed with the extra installed and Any in
# core-only mypy runs (central override). The decorated defs below are
# deliberately UNANNOTATED inner factories wrapped by annotated outer
# functions: mypy has nothing to untype in either environment, so no
# per-line ignores are needed and none go unused in the other env.

__all__ = ["NITELOS_EVIDENCE_KEY", "VALUE_ABSTAIN", "nitelos_accuracy", "nitelos_scorer"]

NITELOS_EVIDENCE_KEY = "nitelos_evidence"
VALUE_CORRECT = "C"
VALUE_INCORRECT = "I"
VALUE_ABSTAIN = "A"


def nitelos_accuracy() -> Any:
    """C/(C+I) over the DECISIVE scores only — abstentions excluded.

    Inspect's stock ``accuracy()`` maps every unknown value (including our
    "A") to 0.0 and keeps it in the denominator, which would punish
    abstention like failure. This metric drops :data:`VALUE_ABSTAIN` scores
    entirely, matching the F8 contract ("abstained → a separate value
    documented as excluded from accuracy"). Attach the stock metric yourself
    if you want abstention counted as 0.
    """

    @metric
    def _factory():  # type: ignore[no-untyped-def]  # inspect decorator shape; see imports note

        def compute(scores: list[Any]) -> float:
            decisive = [s for s in scores if s.score.value in (VALUE_CORRECT, VALUE_INCORRECT)]
            if not decisive:
                return 0.0
            correct = sum(1 for s in decisive if s.score.value == VALUE_CORRECT)
            return correct / len(decisive)

        return compute

    return _factory()


def _score_metadata(result: VerificationResult, evidence: list[dict[str, Any]]) -> dict[str, Any]:
    limitations = set(result.diagnostics.limitations)
    for criterion in result.criteria:
        limitations.update(criterion.limitations)
    return {
        "nitelos": {
            "decision": str(result.decision) if result.decision is not None else None,
            "execution_status": str(result.execution_status),
            "reason_codes": sorted({str(code) for code in result.reason_codes}),
            "limitation_codes": sorted(limitations),
            "evidence_fingerprints": [str(item["sha256"]) for item in evidence],
        }
    }


def _explanation(result: VerificationResult) -> str:
    reasons = ",".join(sorted({str(code) for code in result.reason_codes})) or "-"
    if result.decision is not None:
        return f"nitelos {result.decision.value} ({reasons})"
    return f"nitelos {result.execution_status.value} ({reasons})"


def _agent_evidence_fault_score(evidence: list[dict[str, Any]], code: str) -> Score:
    """Score "A" for agent-side evidence faults (crashing would DoS the eval)."""
    return Score(
        value=VALUE_ABSTAIN,
        explanation=f"nitelos input_error ({code})",
        metadata={
            "nitelos": {
                "decision": None,
                "execution_status": "input_error",
                "reason_codes": [code],
                "limitation_codes": [],
                "evidence_fingerprints": [
                    str(item.get("sha256")) for item in evidence if isinstance(item, dict)
                ],
            }
        },
    )


def _to_score(result: VerificationResult, evidence: list[dict[str, Any]]) -> Score:
    if result.decision is not None and result.decision.value == "success":
        value = VALUE_CORRECT
    elif result.decision is not None and result.decision.value == "failure":
        value = VALUE_INCORRECT
    else:
        # abstained (a decision, but never a pass or fail), input_error,
        # backend_error: outside accuracy by design
        value = VALUE_ABSTAIN
    return Score(
        value=value,
        explanation=_explanation(result),
        metadata=_score_metadata(result, evidence),
    )


def nitelos_scorer(
    *,
    name: str = "nitelos",
    verifier: Verifier | None = None,
    policy: Any = None,
    trust_bindings: tuple[TrustBinding, ...] = (),
) -> Scorer:
    """Build an Inspect ``@scorer`` that verifies outcomes with nitelos.

    ``verifier`` overrides the default :class:`Verifier` (``policy`` and
    ``trust_bindings`` configure the default one). The returned scorer reads
    the contract documented in the module docstring, runs the verifier
    synchronously (deterministic evaluation, milliseconds) and maps the result
    to C / I / A with safe metadata. Raises :class:`KeyError` at scoring time
    when the sample metadata carries no ``nitelos_criteria``.
    """
    effective_verifier = (
        verifier if verifier is not None else Verifier(policy=policy, trust_bindings=trust_bindings)
    )

    @scorer(name=name, metrics=[nitelos_accuracy()])
    def factory():  # type: ignore[no-untyped-def]  # inspect decorator shape; see imports note
        # unannotated inner factory: see the typing note near the imports
        async def score(state, target):  # type: ignore[no-untyped-def]  # ditto

            del target  # the truth comes from evidence, never from the target string
            criteria = state.metadata["nitelos_criteria"]
            checkpoint_id = state.metadata.get("nitelos_checkpoint_id", "cp-inspect")
            request_id = state.metadata.get("nitelos_request_id", f"inspect-{state.sample_id}")
            evidence: list[dict[str, Any]] = list(state.store.get(NITELOS_EVIDENCE_KEY) or [])
            # NIT-023 composition: citations are filtered to the ids the agent's
            # store actually holds, so a dangling citation abstains with
            # MISSING_EVIDENCE instead of raising UNKNOWN_REFERENCE (an agent
            # that captured nothing must not crash — or DoS — the eval).
            present = {
                str(item.get("id"))
                for item in evidence
                if isinstance(item, dict) and item.get("id") is not None
            }
            filtered_criteria = []
            for raw in criteria:
                entry = dict(raw) if isinstance(raw, dict) else raw
                if isinstance(entry, dict):
                    entry["evidence_ids"] = [
                        cited for cited in entry.get("evidence_ids", []) if str(cited) in present
                    ]
                filtered_criteria.append(entry)
            document = {
                "schema_version": "1",
                "request_id": request_id,
                "objective": "Verify the outcome the agent claimed",
                "checkpoint_id": checkpoint_id,
                "as_of": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
                "criteria": filtered_criteria,
                "evidence": evidence,
                "metadata": {},
            }
            try:
                request = parse_request(json.dumps(document))
            except Exception:  # noqa: BLE001 - parse failures are discriminated below, not swallowed
                # Author-vs-agent split: re-validate with the evidence dropped
                # AND citations blanked — if that parses, the criteria document
                # itself is sound and the fault is the agent-written evidence
                # -> score A; otherwise the eval author misconfigured the
                # criteria -> stay loud.
                criteria_only = dict(document)
                criteria_only["evidence"] = []
                criteria_only["criteria"] = [
                    ({**entry, "evidence_ids": []} if isinstance(entry, dict) else entry)
                    for entry in document["criteria"]
                ]
                try:
                    parse_request(json.dumps(criteria_only))
                except Exception:
                    raise
                return _agent_evidence_fault_score(evidence, "INVALID_SCHEMA")
            result = effective_verifier.verify(request)
            return _to_score(result, evidence)

        return score

    return cast(Scorer, factory())
