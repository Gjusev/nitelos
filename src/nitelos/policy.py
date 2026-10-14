"""Evidence eligibility and pure policy aggregation (NIT-005).

Authority: docs/planning/05-evidence-and-policies.md in full (policy
configuration, eligibility steps 1-7, deterministic reason ordering,
aggregation truth table, required examples), 03-domain-model-and-api.md
(TrustBinding, CriterionResult/VerificationResult reason semantics,
INVALID_POLICY / UNSUPPORTED_CAPABILITY codes), 07-security-and-privacy.md
(SEC-02 trust boundaries). Everything here is pure: no I/O, no model calls,
no thresholds, no risk classification. Error-to-result conversion is NIT-006.

Eligibility follows document 05 exactly: only cited evidence counts; a cited
item with an incompatible kind/channel for the criterion scope raises
UNSUPPORTED_CAPABILITY (never a silent skip); subject, checkpoint, freshness
and phase are then checked in that order, plus the host trust binding for
external items. All applicable ineligibility reasons are collected per item
and deduplicated across items in citation order, preserving first
occurrence; comparison/model reasons are appended after them. There is no
"newest wins" rule.

Aggregation is the all-required conjunction: all supported -> success, any
refuted -> failure, otherwise abstained. A same-criterion contradiction is
unknown, never refuted. Result-level reasons start with the aggregate code
and then include criterion reasons in criterion order, deduplicated.

Interpretations (conservative):

- basis is DETERMINISTIC only when deterministic evaluations exist (an
  empty-citation or all-ineligible criterion has basis NONE); visual
  supported/refuted outcomes are MODEL_INFERRED and visual unknown outcomes
  (MODEL_UNCERTAIN / MODEL_INFERENCE_DISALLOWED / all ineligible) are NONE;
- when every cited item is ineligible, the criterion carries exactly the
  ineligibility reasons (MISSING_VALUE is reserved for eligible items whose
  values are missing, MISSING_EVIDENCE for empty citations);
- a visual criterion with model inference allowed but no eligible cited
  image does not need a finding (doc 04: no admissible referenced evidence
  abstains without invoking a model); passing allow_model_inference=True
  with eligible images but no finding is a caller programming error
  (ValueError), not a policy outcome;
- the finding's criterion_id and reference validity are NIT-007's checks;
  this module consumes an already-validated finding's state only;
- policy_hash is SHA-256 over canonical JSON v1 of the effective policy
  object {"allow_model_inference", "id", "version"} — every effective value,
  stable across processes (unlike digests of Pillow-encoded bytes).
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Literal, cast

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from nitelos._json import JsonError, parse_json
from nitelos.backends.deterministic import evaluate_assertion
from nitelos.errors import (
    DecisionCode,
    EvidenceValidationError,
    InputErrorCode,
    Issue,
    RequestValidationError,
)
from nitelos.schemas import (
    ActionEvidence,
    AssertionCriterion,
    BackendFinding,
    Basis,
    Channel,
    CriterionEvaluation,
    CriterionResult,
    CriterionState,
    Decision,
    EvidenceRef,
    Grounding,
    IDType,
    ObservationEvidence,
    Phase,
    Score,
    ScreenshotEvidence,
    Sha256Type,
    SubjectMap,
    VerificationRequest,
    VisualCriterion,
    canonical_json,
)

__all__ = [
    "AggregateResult",
    "CriterionOutcome",
    "TrustBinding",
    "VerificationPolicy",
    "aggregate_decision",
    "eligible_evidence",
    "evaluate_criterion",
    "parse_policy",
    "policy_hash",
    "to_criterion_result",
]


class _ConfigModel(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)


class VerificationPolicy(_ConfigModel):
    """Typed verification policy v1; the only knob in v0.1 is the model opt-in.

    All other semantics are fixed (document 05): all criteria required,
    contradiction becomes unknown, external binding required, temporal and
    subject checks enforced, unknown is not failure, no confidence
    thresholds. Use :func:`parse_policy` for serialized configuration; a
    Verifier constructed with invalid configuration raises
    ConfigurationError (NIT-006).
    """

    id: str = Field(default="strict", min_length=1)
    version: Literal["1"] = "1"
    allow_model_inference: bool = False


class TrustBinding(_ConfigModel):
    """Host-authorized external trust for exactly one evidence item.

    Constructed only by the trusted host after independently authorizing and
    collecting the data; never parsed from request or trace JSON. Binding
    both the source and the digest prevents a forged item from merely
    reusing an allowlisted source name.
    """

    evidence_id: IDType
    sha256: Sha256Type
    source_id: IDType
    subject: SubjectMap
    checkpoint_id: IDType


def parse_policy(data: Mapping[str, object] | str | bytes | bytearray) -> VerificationPolicy:
    """Parse serialized policy configuration strictly.

    Unknown keys, wrong types, duplicate JSON keys and any version other
    than "1" raise :class:`RequestValidationError` with the INVALID_POLICY
    code and a safe field path (the request-error type is reused because the
    issue shape is identical; the code distinguishes the category).
    """
    value: object = data
    if isinstance(data, (str, bytes, bytearray)):
        try:
            raw = data.encode("utf-8") if isinstance(data, str) else bytes(data)
            text = raw.decode("utf-8")
            value = parse_json(text, max_depth=4)
        except (UnicodeDecodeError, JsonError):
            raise _policy_error(InputErrorCode.INVALID_POLICY, "$", "policy is not valid JSON") from None
    if not isinstance(value, Mapping):
        raise _policy_error(InputErrorCode.INVALID_POLICY, "$", "policy must be a JSON object")
    known = {"id", "version", "allow_model_inference"}
    for key in value:
        if key not in known:
            raise _policy_error(InputErrorCode.INVALID_POLICY, f"$.{key}", "unknown policy field")
    try:
        return VerificationPolicy.model_validate(dict(value))
    except ValidationError:
        raise _policy_error(InputErrorCode.INVALID_POLICY, "$", "policy value failed validation") from None


def policy_hash(policy: VerificationPolicy) -> str:
    """SHA-256 over canonical JSON v1 of every effective policy value."""
    return hashlib.sha256(
        canonical_json(
            {
                "allow_model_inference": policy.allow_model_inference,
                "id": policy.id,
                "version": policy.version,
            }
        ).encode("utf-8")
    ).hexdigest()


def _policy_error(code: InputErrorCode, path: str, message: str) -> RequestValidationError:
    return RequestValidationError([Issue(code, path, message)])


# ---------------------------------------------------------------------------
# eligibility
# ---------------------------------------------------------------------------

AnyEvidence = ScreenshotEvidence | ObservationEvidence | ActionEvidence

_OBSERVED_CHANNELS = (Channel.DOM, Channel.ACCESSIBILITY, Channel.TOOL)
_EXTERNAL_CHANNELS = (Channel.EXTERNAL_API, Channel.DATABASE)


def _check_capability(criterion: AssertionCriterion | VisualCriterion, item: AnyEvidence) -> None:
    """Doc 05 step 3: incompatible kind/channel is an input error, never a skip."""
    scope = criterion.scope
    if scope == "visual":
        supported = isinstance(item, ScreenshotEvidence)
    elif scope == "observed_state":
        supported = isinstance(item, ObservationEvidence) and item.channel in _OBSERVED_CHANNELS
    elif scope == "behavioral":
        supported = isinstance(item, ActionEvidence) or (
            isinstance(item, ObservationEvidence) and item.channel == Channel.TOOL
        )
    else:  # external
        supported = isinstance(item, ObservationEvidence) and item.channel in _EXTERNAL_CHANNELS
    if not supported:
        raise EvidenceValidationError(
            Issue(
                InputErrorCode.UNSUPPORTED_CAPABILITY,
                "$.evidence",
                "cited evidence kind or channel is incompatible with the criterion scope",
            )
        )


def _binding_matches(binding: TrustBinding, item: ObservationEvidence) -> bool:
    return (
        binding.evidence_id == item.id
        and binding.sha256 == item.sha256
        and binding.source_id == item.source_id
        and dict(binding.subject) == dict(item.subject)
        and binding.checkpoint_id == item.checkpoint_id
    )


def _ineligibility_reasons(
    criterion: AssertionCriterion | VisualCriterion,
    item: AnyEvidence,
    request: VerificationRequest,
    bindings: Sequence[TrustBinding],
) -> tuple[str, ...]:
    """Doc 05 step 4-5 checks, in the documented order, all applicable codes."""
    reasons: list[str] = []
    if dict(criterion.subject) != dict(item.subject):
        reasons.append("SUBJECT_MISMATCH")
    if item.checkpoint_id != request.checkpoint_id:
        reasons.append("CHECKPOINT_MISMATCH")
    age = (request.as_of - item.captured_at).total_seconds()
    if age > criterion.max_age_seconds:
        reasons.append("STALE_EVIDENCE")
    if item.phase != Phase.FINAL:
        reasons.append("PENDING_STATE")
    if criterion.scope == "external" and isinstance(item, ObservationEvidence):  # noqa: SIM102 - mirrors doc-05 step 5
        if not any(_binding_matches(binding, item) for binding in bindings):
            reasons.append("UNTRUSTED_EXTERNAL")
    return tuple(reasons)


@dataclass(frozen=True)
class CriterionOutcome:
    """Pure per-criterion result of the policy algorithm (NIT-006 assembles results)."""

    state: CriterionState
    basis: Basis
    reason_codes: tuple[str, ...]
    limitations: tuple[str, ...] = ()
    evaluations: tuple[CriterionEvaluation, ...] = ()
    evidence_refs: tuple[EvidenceRef, ...] = ()
    cited_ids: tuple[str, ...] = ()
    eligible_ids: tuple[str, ...] = ()
    ineligible: Mapping[str, tuple[str, ...]] = field(default_factory=lambda: MappingProxyType({}))


def _dedupe(codes: Sequence[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(codes))


def eligible_evidence(
    criterion: AssertionCriterion | VisualCriterion,
    request: VerificationRequest,
    bindings: Sequence[TrustBinding] = (),
) -> tuple[tuple[AnyEvidence, ...], Mapping[str, tuple[str, ...]]]:
    """Pure doc-05 steps 2-5 filter over the cited evidence of one criterion.

    Returns the eligible items in citation order plus an immutable mapping of
    ineligible evidence IDs to their ordered reason tuples. Raises
    EvidenceValidationError/UNSUPPORTED_CAPABILITY for an incompatible kind
    or channel (step 3), including for every scope citing a human-channel
    observation. evaluate_criterion reuses this single implementation.
    """
    by_id = {item.id: item for item in request.evidence}
    eligible: list[AnyEvidence] = []
    ineligible: dict[str, tuple[str, ...]] = {}
    for evidence_id in criterion.evidence_ids:  # citation order
        item = by_id[evidence_id]
        _check_capability(criterion, item)
        reasons = _ineligibility_reasons(criterion, item, request, bindings)
        if reasons:
            ineligible[item.id] = reasons
        else:
            eligible.append(item)
    return tuple(eligible), MappingProxyType(ineligible)


def _model_inferred_refs(finding: BackendFinding) -> tuple[EvidenceRef, ...]:
    """Adopt a validated finding's refs; only the core assigns the grounding."""
    return tuple(
        EvidenceRef(
            evidence_id=ref.evidence_id,
            pointer=ref.pointer,
            bbox=ref.bbox,
            grounding=Grounding.MODEL_INFERRED,
        )
        for ref in finding.evidence_refs
    )


def evaluate_criterion(
    criterion: AssertionCriterion | VisualCriterion,
    request: VerificationRequest,
    policy: VerificationPolicy,
    bindings: Sequence[TrustBinding] = (),
    *,
    visual_finding: BackendFinding | None = None,
) -> CriterionOutcome:
    """Evaluate one criterion: eligibility (steps 2-5) then combination/gating (6-7).

    Raises :class:`EvidenceValidationError` with UNSUPPORTED_CAPABILITY when a
    cited item's kind/channel is incompatible with the criterion scope (step 3
    runs even when model inference is disallowed). ``visual_finding`` is the
    already-validated backend finding for a visual criterion when policy
    allows model inference and eligible images exist.
    """
    eligible, ineligible = eligible_evidence(criterion, request, bindings)
    cited_ids = tuple(criterion.evidence_ids)
    ineligibility_codes = _dedupe(
        [code for evidence_id in cited_ids for code in ineligible.get(evidence_id, ())]
    )

    if not cited_ids:
        return CriterionOutcome(
            state=CriterionState.UNKNOWN,
            basis=Basis.NONE,
            reason_codes=("MISSING_EVIDENCE",),
            cited_ids=(),
            eligible_ids=(),
            ineligible=ineligible,
        )
    if isinstance(criterion, AssertionCriterion):
        evaluations = evaluate_assertion(
            criterion, cast("Sequence[ObservationEvidence | ActionEvidence]", eligible)
        )
        states = [evaluation.state for evaluation in evaluations]
        comparison: tuple[str, ...]
        if CriterionState.SUPPORTED in states and CriterionState.REFUTED in states:
            state, comparison = CriterionState.UNKNOWN, ("CONTRADICTORY_EVIDENCE",)
        elif CriterionState.REFUTED in states:
            state, comparison = CriterionState.REFUTED, ()
        elif CriterionState.SUPPORTED in states:
            state, comparison = CriterionState.SUPPORTED, ()
        elif eligible:
            state, comparison = CriterionState.UNKNOWN, ("MISSING_VALUE",)
        else:
            state, comparison = CriterionState.UNKNOWN, ()
        basis = Basis.DETERMINISTIC if evaluations else Basis.NONE
        return CriterionOutcome(
            state=state,
            basis=basis,
            reason_codes=_dedupe((*ineligibility_codes, *comparison)),
            evaluations=evaluations,
            evidence_refs=tuple(evaluation.evidence_ref for evaluation in evaluations),
            cited_ids=cited_ids,
            eligible_ids=tuple(item.id for item in eligible),
            ineligible=ineligible,
        )

    # visual criterion (step 7)
    if not policy.allow_model_inference:
        return CriterionOutcome(
            state=CriterionState.UNKNOWN,
            basis=Basis.NONE,
            reason_codes=_dedupe((*ineligibility_codes, "MODEL_INFERENCE_DISALLOWED")),
            cited_ids=cited_ids,
            eligible_ids=tuple(item.id for item in eligible),
            ineligible=ineligible,
        )
    if not eligible:
        return CriterionOutcome(
            state=CriterionState.UNKNOWN,
            basis=Basis.NONE,
            reason_codes=ineligibility_codes,
            cited_ids=cited_ids,
            eligible_ids=(),
            ineligible=ineligible,
        )
    if visual_finding is None:
        raise ValueError(
            "model inference is allowed and eligible images exist, but no visual finding was provided"
        )
    if visual_finding.state == CriterionState.UNKNOWN:
        return CriterionOutcome(
            state=CriterionState.UNKNOWN,
            basis=Basis.NONE,
            reason_codes=_dedupe((*ineligibility_codes, "MODEL_UNCERTAIN")),
            cited_ids=cited_ids,
            eligible_ids=tuple(item.id for item in eligible),
            ineligible=ineligible,
        )
    return CriterionOutcome(
        state=visual_finding.state,
        basis=Basis.MODEL_INFERRED,
        reason_codes=ineligibility_codes,
        limitations=("VISUAL_GROUNDING_UNVERIFIED",),
        evidence_refs=_model_inferred_refs(visual_finding),
        cited_ids=cited_ids,
        eligible_ids=tuple(item.id for item in eligible),
        ineligible=ineligible,
    )


# ---------------------------------------------------------------------------
# aggregation
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AggregateResult:
    """Conjunction decision plus result-level reason codes (doc 05 truth table)."""

    decision: Decision
    reason_codes: tuple[str, ...]


def aggregate_decision(outcomes: Sequence[CriterionOutcome]) -> AggregateResult:
    """All supported -> success; any refuted -> failure; otherwise abstained."""
    states = [outcome.state for outcome in outcomes]
    if states and all(state == CriterionState.SUPPORTED for state in states):
        decision, aggregate_code = Decision.SUCCESS, DecisionCode.ALL_CRITERIA_SUPPORTED
    elif any(state == CriterionState.REFUTED for state in states):
        decision, aggregate_code = Decision.FAILURE, DecisionCode.CRITERION_REFUTED
    else:
        decision, aggregate_code = Decision.ABSTAINED, DecisionCode.INSUFFICIENT_EVIDENCE
    criterion_codes = [code for outcome in outcomes for code in outcome.reason_codes]
    return AggregateResult(decision, _dedupe((aggregate_code, *criterion_codes)))


def to_criterion_result(
    criterion: AssertionCriterion | VisualCriterion,
    outcome: CriterionOutcome,
    score: Score | None = None,
) -> CriterionResult:
    """Assemble the public CriterionResult for one criterion outcome."""
    return CriterionResult(
        criterion_id=criterion.id,
        state=outcome.state,
        basis=outcome.basis,
        scope=criterion.scope,
        evidence_refs=outcome.evidence_refs,
        reason_codes=outcome.reason_codes,
        score=score,
        limitations=outcome.limitations,
        evaluations=outcome.evaluations,
    )
