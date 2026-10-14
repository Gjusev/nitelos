"""POL-01..05: evidence eligibility and pure policy aggregation (NIT-005).

Authority: docs/planning/05-evidence-and-policies.md in full (policy
configuration, eligibility steps 1-7, reason ordering, truth table, required
examples), 03-domain-model-and-api.md (TrustBinding, result reason
semantics), 07 (SEC-02 boundaries). All expected decisions come from literal
hand-written tables. Functions are pure: no I/O, no model calls.
"""

from __future__ import annotations

from typing import Any

import pytest

from nitelos import TrustBinding, VerificationPolicy
from nitelos.errors import EvidenceValidationError, InputErrorCode, RequestValidationError
from nitelos.policy import (
    aggregate_decision,
    evaluate_criterion,
    parse_policy,
    policy_hash,
    to_criterion_result,
)
from nitelos.schemas import (
    BackendFinding,
    Basis,
    CriterionState,
    Decision,
    EvidenceRef,
    Grounding,
    parse_request,
)
from test_contract import SHA, _action, _criterion, _observation, _request, _screenshot, _visual_criterion

SUBJECT = {"form": "registration-1"}
STRICT = VerificationPolicy()
ALLOW_MODEL = VerificationPolicy(allow_model_inference=True)

STRICT_HASH = "ade7d024af1a4c58f7cf49730d5789c28c74155d8a067fa44d42e73ba0440f9e"
ALLOW_MODEL_HASH = "5160a8cbe0450933fcc0ba68f4983ad3b23e28110453e9c084fda5b99dc21ddb"


def _obs_ext(evidence_id: str, data: dict[str, Any], **over: Any) -> dict[str, Any]:
    item = _observation(
        id=evidence_id,
        channel="external_api",
        source_id="ledger",
        data=data,
        subject=dict(SUBJECT),
    )
    item.update(over)
    return item


def _ext_crit(evidence_ids: list[str], expected: Any = "paid", **over: Any) -> dict[str, Any]:
    item = _criterion(
        id="c-ext",
        scope="external",
        pointer="/status",
        operator="equals",
        expected=expected,
        evidence_ids=list(evidence_ids),
        subject=dict(SUBJECT),
    )
    item.update(over)
    return item


def _binding(evidence_id: str = "ledger-1", /, **over: Any) -> TrustBinding:
    values: dict[str, Any] = {
        "evidence_id": evidence_id,
        "sha256": SHA,
        "source_id": "ledger",
        "subject": dict(SUBJECT),
        "checkpoint_id": "cp",
    }
    values.update(over)
    return TrustBinding(**values)


def _visual_finding(state: CriterionState, criterion_id: str = "c-vis") -> BackendFinding:
    return BackendFinding(
        criterion_id=criterion_id,
        state=state,
        evidence_refs=(EvidenceRef(evidence_id="shot-1", bbox=(0, 0, 2, 3)),),
    )


def _first_outcome(request: Any, bindings: tuple[TrustBinding, ...] = (), **kwargs: Any) -> Any:
    return evaluate_criterion(request.criteria[0], request, STRICT, bindings, **kwargs)


# --------------------------------------------------------------------------
# POL-01: the 27 three-criterion conjunction table
# --------------------------------------------------------------------------


def _pol01_request(states: tuple[str, str, str]) -> Any:
    criteria: list[dict[str, Any]] = []
    evidence: list[dict[str, Any]] = []
    for index, letter in enumerate(states):
        data = {"v": True} if letter in ("S", "R") else {"other": 1}
        evidence.append(_observation(id=f"o{index}", sequence=index, data=data))
        criteria.append(
            _criterion(
                id=f"c{index}",
                evidence_ids=[f"o{index}"],
                pointer="/v",
                operator="equals",
                expected=letter == "S",
            )
        )
    return parse_request(_request(criteria=criteria, evidence=evidence))


# hand-written literal truth table: any refuted -> failure; all supported ->
# success; otherwise abstained
POL01_TABLE = [
    (("S", "S", "S"), Decision.SUCCESS),
    (("S", "S", "U"), Decision.ABSTAINED),
    (("S", "S", "R"), Decision.FAILURE),
    (("S", "U", "S"), Decision.ABSTAINED),
    (("S", "U", "U"), Decision.ABSTAINED),
    (("S", "U", "R"), Decision.FAILURE),
    (("S", "R", "S"), Decision.FAILURE),
    (("S", "R", "U"), Decision.FAILURE),
    (("S", "R", "R"), Decision.FAILURE),
    (("U", "S", "S"), Decision.ABSTAINED),
    (("U", "S", "U"), Decision.ABSTAINED),
    (("U", "S", "R"), Decision.FAILURE),
    (("U", "U", "S"), Decision.ABSTAINED),
    (("U", "U", "U"), Decision.ABSTAINED),
    (("U", "U", "R"), Decision.FAILURE),
    (("U", "R", "S"), Decision.FAILURE),
    (("U", "R", "U"), Decision.FAILURE),
    (("U", "R", "R"), Decision.FAILURE),
    (("R", "S", "S"), Decision.FAILURE),
    (("R", "S", "U"), Decision.FAILURE),
    (("R", "S", "R"), Decision.FAILURE),
    (("R", "U", "S"), Decision.FAILURE),
    (("R", "U", "U"), Decision.FAILURE),
    (("R", "U", "R"), Decision.FAILURE),
    (("R", "R", "S"), Decision.FAILURE),
    (("R", "R", "U"), Decision.FAILURE),
    (("R", "R", "R"), Decision.FAILURE),
]


@pytest.mark.parametrize(("states", "decision"), POL01_TABLE)
def test_pol01_conjunction_table(states: tuple[str, str, str], decision: Decision) -> None:
    request = _pol01_request(states)
    outcomes = tuple(evaluate_criterion(criterion, request, STRICT) for criterion in request.criteria)
    assert [outcome.state for outcome in outcomes] == [
        {"S": CriterionState.SUPPORTED, "R": CriterionState.REFUTED, "U": CriterionState.UNKNOWN}[letter]
        for letter in states
    ]
    assert aggregate_decision(outcomes).decision == decision


def test_pol01_result_reason_codes_start_with_aggregate() -> None:
    request = _pol01_request(("R", "U", "S"))
    outcomes = tuple(evaluate_criterion(c, request, STRICT) for c in request.criteria)
    aggregate = aggregate_decision(outcomes)
    assert aggregate.decision == Decision.FAILURE
    assert aggregate.reason_codes[0] == "CRITERION_REFUTED"
    # criterion reasons follow in criterion order, deduplicated
    assert aggregate.reason_codes == ("CRITERION_REFUTED", "MISSING_VALUE")


# --------------------------------------------------------------------------
# POL-02: same-criterion contradiction vs separate refutation
# --------------------------------------------------------------------------


def test_pol02_contradiction_within_one_criterion_is_unknown() -> None:
    doc = _request(
        criteria=[
            _criterion(id="c", evidence_ids=["yes", "no"], pointer="/v", operator="equals", expected=True)
        ],
        evidence=[
            _observation(id="yes", data={"v": True}),
            _observation(id="no", sequence=1, data={"v": False}),
        ],
    )
    request = parse_request(doc)
    outcome = _first_outcome(request)
    assert outcome.state == CriterionState.UNKNOWN
    assert outcome.reason_codes == ("CONTRADICTORY_EVIDENCE",)
    assert outcome.basis == Basis.DETERMINISTIC
    assert len(outcome.evaluations) == 2  # both examined references retained


def test_pol02_separate_refuted_criterion_still_fails() -> None:
    doc = _request(
        criteria=[
            _criterion(
                id="contra", evidence_ids=["yes", "no"], pointer="/v", operator="equals", expected=True
            ),
            _criterion(id="refuted", evidence_ids=["no2"], pointer="/v", operator="equals", expected=True),
        ],
        evidence=[
            _observation(id="yes", data={"v": True}),
            _observation(id="no", sequence=1, data={"v": False}),
            _observation(id="no2", sequence=2, data={"v": False}),
        ],
    )
    request = parse_request(doc)
    outcomes = tuple(evaluate_criterion(c, request, STRICT) for c in request.criteria)
    assert outcomes[0].state == CriterionState.UNKNOWN
    assert outcomes[1].state == CriterionState.REFUTED
    assert aggregate_decision(outcomes).decision == Decision.FAILURE


def test_pol02_unknown_evaluations_do_not_negate_decisive_ones() -> None:
    doc = _request(
        criteria=[
            _criterion(id="c", evidence_ids=["hit", "miss"], pointer="/v", operator="equals", expected=True)
        ],
        evidence=[
            _observation(id="hit", data={"v": True}),
            _observation(id="miss", sequence=1, data={"other": 2}),
        ],
    )
    request = parse_request(doc)
    outcome = _first_outcome(request)
    assert outcome.state == CriterionState.SUPPORTED  # decisive + unknown => supported
    assert outcome.reason_codes == ()


# --------------------------------------------------------------------------
# POL-03: eligibility boundaries
# --------------------------------------------------------------------------


def test_pol03_empty_citations_are_missing_evidence() -> None:
    doc = _request(criteria=[_criterion(evidence_ids=[])], evidence=[_observation()])
    request = parse_request(doc)
    outcome = _first_outcome(request)
    assert outcome.state == CriterionState.UNKNOWN
    assert outcome.reason_codes == ("MISSING_EVIDENCE",)
    assert outcome.basis == Basis.NONE
    assert outcome.evaluations == ()


def test_pol03_pending_phase_is_ineligible_not_failure() -> None:
    doc = _request(
        criteria=[_criterion(operator="equals", expected=False)],
        evidence=[_observation(data={"validation_error": False}, phase="pending")],
    )
    request = parse_request(doc)
    outcome = _first_outcome(request)
    assert outcome.state == CriterionState.UNKNOWN
    assert outcome.reason_codes == ("PENDING_STATE",)


def test_pol03_freshness_boundary() -> None:
    # exactly max_age (300s) old is eligible; one second more is stale
    boundary = _request(
        criteria=[_criterion(operator="equals", expected=True)],
        evidence=[_observation(data={"validation_error": True}, captured_at="2024-06-01T09:55:00Z")],
    )
    outcome = _first_outcome(parse_request(boundary))
    assert outcome.state == CriterionState.SUPPORTED
    stale = _request(
        criteria=[_criterion(operator="equals", expected=True)],
        evidence=[_observation(data={"validation_error": True}, captured_at="2024-06-01T09:54:59Z")],
    )
    outcome = _first_outcome(parse_request(stale))
    assert outcome.state == CriterionState.UNKNOWN
    assert outcome.reason_codes == ("STALE_EVIDENCE",)
    # a larger max_age makes the same capture eligible again
    relaxed = _request(
        criteria=[_criterion(operator="equals", expected=True, max_age_seconds=1000)],
        evidence=[_observation(data={"validation_error": True}, captured_at="2024-06-01T09:54:59Z")],
    )
    assert _first_outcome(parse_request(relaxed)).state == CriterionState.SUPPORTED


def test_pol03_future_dated_evidence_is_an_input_error() -> None:
    doc = _request(
        evidence=[_observation(captured_at="2024-06-01T10:00:01Z")],
    )
    with pytest.raises(RequestValidationError) as excinfo:
        parse_request(doc)
    assert excinfo.value.issues[0].code == InputErrorCode.INVALID_TIMESTAMP


def test_pol03_subject_and_checkpoint_mismatches() -> None:
    doc = _request(
        criteria=[_criterion()],
        evidence=[_observation(subject={"form": "other-form"})],
    )
    outcome = _first_outcome(parse_request(doc))
    assert outcome.reason_codes == ("SUBJECT_MISMATCH",)
    doc = _request(
        criteria=[_criterion()],
        evidence=[_observation(checkpoint_id="earlier")],
    )
    outcome = _first_outcome(parse_request(doc))
    assert outcome.reason_codes == ("CHECKPOINT_MISMATCH",)


def test_pol03_reason_order_within_one_item_and_across_items() -> None:
    # one item collecting several reasons, in the documented check order
    doc = _request(
        criteria=[_criterion()],
        evidence=[
            _observation(
                subject={"form": "other"},
                checkpoint_id="earlier",
                captured_at="2024-06-01T09:00:00Z",
                phase="pending",
            )
        ],
    )
    outcome = _first_outcome(parse_request(doc))
    assert outcome.reason_codes == (
        "SUBJECT_MISMATCH",
        "CHECKPOINT_MISMATCH",
        "STALE_EVIDENCE",
        "PENDING_STATE",
    )
    # deduplication preserves first occurrence across cited items (citation
    # order drives eligibility; the evidence list only obeys the timestamp rule)
    doc = _request(
        criteria=[_criterion(evidence_ids=["a", "b", "c"])],
        evidence=[
            _observation(id="b", captured_at="2024-06-01T09:00:00Z"),
            _observation(id="a", sequence=1, subject={"form": "other"}),
            _observation(id="c", sequence=2, subject={"form": "another"}, phase="pending"),
        ],
    )
    outcome = _first_outcome(parse_request(doc))
    assert outcome.reason_codes == ("SUBJECT_MISMATCH", "STALE_EVIDENCE", "PENDING_STATE")


def test_pol03_ineligible_extras_stay_in_reasons_without_changing_state() -> None:
    doc = _request(
        criteria=[_criterion(evidence_ids=["good", "stale-one"])],
        evidence=[
            _observation(id="stale-one", captured_at="2024-06-01T09:00:00Z"),
            _observation(id="good", sequence=1, data={"validation_error": False}),
        ],
    )
    outcome = _first_outcome(parse_request(doc))
    assert outcome.state == CriterionState.SUPPORTED  # decisive eligible evidence
    assert outcome.reason_codes == ("STALE_EVIDENCE",)  # ineligible extra remains visible
    assert outcome.eligible_ids == ("good",)


# --------------------------------------------------------------------------
# POL-04: trust bindings
# --------------------------------------------------------------------------


def _pol04_request(evidence: list[dict[str, Any]], criterion: dict[str, Any] | None = None) -> Any:
    doc = _request(
        criteria=[criterion or _ext_crit(["ledger-1"])],
        evidence=evidence,
    )
    return parse_request(doc)


def test_pol04_exact_binding_admits_external_evidence() -> None:
    request = _pol04_request([_obs_ext("ledger-1", {"status": "paid"})])
    outcome = _first_outcome(request, (_binding("ledger-1"),))
    assert outcome.state == CriterionState.SUPPORTED
    assert outcome.reason_codes == ()


@pytest.mark.parametrize(
    "substitution",
    [
        {"sha256": "b" * 64},  # digest substitution
        {"source_id": "allowlisted-ledger"},  # spoofed source name
        {"subject": {"form": "other-form"}},
        {"checkpoint_id": "earlier"},
        {"evidence_id": "ledger-2"},  # binding for a different item
    ],
)
def test_pol04_binding_substitutions_are_untrusted(substitution: dict[str, Any]) -> None:
    request = _pol04_request([_obs_ext("ledger-1", {"status": "paid"})])
    outcome = _first_outcome(request, (_binding("ledger-1", **substitution),))
    assert outcome.state == CriterionState.UNKNOWN
    assert outcome.reason_codes == ("UNTRUSTED_EXTERNAL",)


def test_pol04_no_binding_is_untrusted() -> None:
    request = _pol04_request([_obs_ext("ledger-1", {"status": "paid"})])
    outcome = _first_outcome(request)
    assert outcome.reason_codes == ("UNTRUSTED_EXTERNAL",)


def test_pol04_stale_bound_item_stays_ineligible() -> None:
    request = _pol04_request([_obs_ext("ledger-1", {"status": "paid"}, captured_at="2024-06-01T09:00:00Z")])
    outcome = _first_outcome(request, (_binding("ledger-1"),))
    assert outcome.state == CriterionState.UNKNOWN
    assert outcome.reason_codes == ("STALE_EVIDENCE",)


# --------------------------------------------------------------------------
# POL-05: visual gating never enables external acceptance
# --------------------------------------------------------------------------


def _pol05_visual_request(evidence: list[dict[str, Any]] | None = None) -> Any:
    doc = _request(
        criteria=[_visual_criterion(evidence_ids=["shot-1"])],
        evidence=evidence or [_screenshot()],
    )
    return parse_request(doc)


def test_pol05_disallowed_model_inference_is_unknown_without_invocation() -> None:
    request = _pol05_visual_request()
    outcome = evaluate_criterion(request.criteria[0], request, STRICT)
    assert outcome.state == CriterionState.UNKNOWN
    assert outcome.reason_codes == ("MODEL_INFERENCE_DISALLOWED",)
    assert outcome.basis == Basis.NONE
    assert outcome.limitations == ()
    assert outcome.evaluations == ()


def test_pol05_allowed_inference_accepts_validated_finding() -> None:
    request = _pol05_visual_request()
    outcome = evaluate_criterion(
        request.criteria[0], request, ALLOW_MODEL, visual_finding=_visual_finding(CriterionState.SUPPORTED)
    )
    assert outcome.state == CriterionState.SUPPORTED
    assert outcome.basis == Basis.MODEL_INFERRED
    assert outcome.limitations == ("VISUAL_GROUNDING_UNVERIFIED",)
    assert outcome.evaluations == ()
    uncertain = evaluate_criterion(
        request.criteria[0], request, ALLOW_MODEL, visual_finding=_visual_finding(CriterionState.UNKNOWN)
    )
    assert uncertain.state == CriterionState.UNKNOWN
    assert uncertain.reason_codes == ("MODEL_UNCERTAIN",)
    assert uncertain.basis == Basis.NONE
    assert uncertain.limitations == ()


def test_pol05_visual_opt_in_cannot_enable_external_acceptance() -> None:
    request = _pol04_request([_obs_ext("ledger-1", {"status": "paid"})])
    outcome = evaluate_criterion(request.criteria[0], request, ALLOW_MODEL)
    assert outcome.state == CriterionState.UNKNOWN
    assert outcome.reason_codes == ("UNTRUSTED_EXTERNAL",)


def test_pol05_visual_eligibility_still_applies_with_finding() -> None:
    request = _pol05_visual_request(
        [_screenshot(subject={"form": "other-form"}, captured_at="2024-06-01T09:00:00Z")]
    )
    outcome = evaluate_criterion(
        request.criteria[0], request, ALLOW_MODEL, visual_finding=_visual_finding(CriterionState.SUPPORTED)
    )
    assert outcome.state == CriterionState.UNKNOWN
    assert outcome.reason_codes == ("SUBJECT_MISMATCH", "STALE_EVIDENCE")


def test_pol05_allowed_inference_without_finding_is_a_caller_error() -> None:
    request = _pol05_visual_request()
    with pytest.raises(ValueError, match="visual finding"):
        evaluate_criterion(request.criteria[0], request, ALLOW_MODEL)


# --------------------------------------------------------------------------
# scope / kind / channel compatibility (doc 05 step 3)
# --------------------------------------------------------------------------


def _capability_error(request: Any, criterion_index: int = 0) -> EvidenceValidationError:
    with pytest.raises(EvidenceValidationError) as excinfo:
        evaluate_criterion(request.criteria[criterion_index], request, STRICT)
    assert excinfo.value.issue.code == InputErrorCode.UNSUPPORTED_CAPABILITY
    return excinfo.value


def test_capability_matrix() -> None:
    # visual accepts screenshots only
    _capability_error(parse_request(_request(criteria=[_visual_criterion(evidence_ids=["obs-1"])])))
    # observed_state accepts dom/accessibility/tool observations
    for channel in ("dom", "accessibility", "tool"):
        request = parse_request(
            _request(evidence=[_observation(channel=channel, data={"validation_error": False})])
        )
        assert _first_outcome(request).state == CriterionState.SUPPORTED
    for bad in ("human", "external_api", "database"):
        _capability_error(
            parse_request(_request(evidence=[_observation(channel=bad, data={"validation_error": False})]))
        )
    _capability_error(
        parse_request(_request(criteria=[_criterion(evidence_ids=["shot-1"])], evidence=[_screenshot()]))
    )
    _capability_error(
        parse_request(
            _request(
                criteria=[_criterion(evidence_ids=["obs-1"], scope="behavioral")], evidence=[_observation()]
            )
        )
    )
    # behavioral accepts actions and tool observations
    request = parse_request(
        _request(
            criteria=[
                _criterion(
                    scope="behavioral",
                    pointer="/reported_status",
                    operator="equals",
                    expected="completed",
                    evidence_ids=["act-1"],
                )
            ],
            evidence=[_action()],
        )
    )
    assert _first_outcome(request).state == CriterionState.SUPPORTED
    request = parse_request(
        _request(
            criteria=[_criterion(scope="behavioral", pointer="/validation_error", evidence_ids=["tool-obs"])],
            evidence=[_observation(id="tool-obs", channel="tool", data={"validation_error": False})],
        )
    )
    assert _first_outcome(request).state == CriterionState.SUPPORTED
    # external accepts external_api/database observations only
    for channel in ("external_api", "database"):
        request = parse_request(
            _request(
                criteria=[_ext_crit(["x-1"])],
                evidence=[_obs_ext("x-1", {"status": "paid"}, channel=channel)],
            )
        )
        assert _first_outcome(request, (_binding("x-1"),)).state == CriterionState.SUPPORTED
    _capability_error(parse_request(_request(criteria=[_ext_crit(["obs-1"])], evidence=[_observation()])))
    _capability_error(parse_request(_request(criteria=[_ext_crit(["act-1"])], evidence=[_action()])))
    # a human-channel observation is unsupported for every scope
    _capability_error(
        parse_request(
            _request(
                criteria=[_criterion(scope="behavioral", pointer="/v", evidence_ids=["h"])],
                evidence=[_observation(id="h", channel="human", data={"v": 1})],
            )
        )
    )


# --------------------------------------------------------------------------
# doc 05 "Required examples", as far as they apply without the verifier
# --------------------------------------------------------------------------


def test_example_tool_success_without_external_snapshot_abstains() -> None:
    request = parse_request(
        _request(
            criteria=[_ext_crit([])],
            evidence=[_observation(id="tool-1", channel="tool", data={"upload": "ok"})],
        )
    )
    outcome = _first_outcome(request)
    assert outcome.state == CriterionState.UNKNOWN
    assert outcome.reason_codes == ("MISSING_EVIDENCE",)
    assert aggregate_decision((outcome,)).decision == Decision.ABSTAINED


def test_example_pending_ledger_abstains_even_with_visual_support() -> None:
    request = parse_request(
        _request(
            criteria=[
                _ext_crit(["ledger-1"]),
                _visual_criterion(id="c-vis", evidence_ids=["shot-1"]),
            ],
            evidence=[
                _obs_ext("ledger-1", {"status": "paid"}, phase="pending"),
                _screenshot(sequence=1),
            ],
        )
    )
    outcomes = tuple(
        evaluate_criterion(
            criterion,
            request,
            ALLOW_MODEL if criterion.id == "c-vis" else STRICT,
            (_binding("ledger-1"),),
            visual_finding=_visual_finding(CriterionState.SUPPORTED) if criterion.id == "c-vis" else None,
        )
        for criterion in request.criteria
    )
    assert outcomes[0].state == CriterionState.UNKNOWN
    assert outcomes[0].reason_codes == ("PENDING_STATE",)
    assert outcomes[1].state == CriterionState.SUPPORTED
    assert aggregate_decision(outcomes).decision == Decision.ABSTAINED


def test_example_failed_ledger_refutes_despite_visual_success() -> None:
    request = parse_request(
        _request(
            criteria=[
                _ext_crit(["ledger-1"]),
                _visual_criterion(id="c-vis", evidence_ids=["shot-1"]),
            ],
            evidence=[
                _obs_ext("ledger-1", {"status": "failed"}),
                _screenshot(sequence=1),
            ],
        )
    )
    outcomes = tuple(
        evaluate_criterion(
            criterion,
            request,
            ALLOW_MODEL if criterion.id == "c-vis" else STRICT,
            (_binding("ledger-1"),),
            visual_finding=_visual_finding(CriterionState.SUPPORTED) if criterion.id == "c-vis" else None,
        )
        for criterion in request.criteria
    )
    assert outcomes[0].state == CriterionState.REFUTED
    assert outcomes[1].state == CriterionState.SUPPORTED
    assert aggregate_decision(outcomes).decision == Decision.FAILURE


def test_example_wrong_customer_vs_explicit_unequal_id() -> None:
    request = parse_request(
        _request(
            criteria=[
                _visual_criterion(evidence_ids=["shot-1"]),
                _ext_crit(["ledger-1"], pointer="/customer_id", expected="customer-A"),
            ],
            evidence=[
                _screenshot(subject={"form": "other-form"}),
                _obs_ext("ledger-1", {"customer_id": "customer-B"}, sequence=1),
            ],
        )
    )
    outcomes = tuple(
        evaluate_criterion(
            criterion,
            request,
            ALLOW_MODEL if criterion.kind == "visual" else STRICT,
            (_binding("ledger-1"),),
            visual_finding=_visual_finding(CriterionState.SUPPORTED) if criterion.kind == "visual" else None,
        )
        for criterion in request.criteria
    )
    assert outcomes[0].state == CriterionState.UNKNOWN
    assert "SUBJECT_MISMATCH" in outcomes[0].reason_codes
    assert outcomes[1].state == CriterionState.REFUTED
    assert aggregate_decision(outcomes).decision == Decision.FAILURE


def test_example_history_is_not_automatically_contradictory() -> None:
    request = parse_request(
        _request(
            criteria=[_criterion(evidence_ids=["new"], pointer="/v", operator="equals", expected=True)],
            evidence=[
                _observation(id="old", data={"v": False}),
                _observation(id="new", sequence=1, data={"v": True}),
            ],
        )
    )
    outcome = _first_outcome(request)
    assert outcome.state == CriterionState.SUPPORTED  # only the cited final item counts


def test_example_agent_summary_cannot_override_final_state() -> None:
    request = parse_request(
        _request(
            criteria=[_criterion(operator="equals", expected=False)],  # no-error assertion
            evidence=[_observation(data={"validation_error": True})],
        )
    )
    outcome = _first_outcome(request)
    assert outcome.state == CriterionState.REFUTED
    assert aggregate_decision((outcome,)).decision == Decision.FAILURE


def test_example_dangling_reference_is_input_error_missing_is_unknown() -> None:
    with pytest.raises(RequestValidationError) as excinfo:
        parse_request(_request(criteria=[_criterion(evidence_ids=["ghost"])]))
    assert excinfo.value.issues[0].code == InputErrorCode.UNKNOWN_REFERENCE
    outcome = _first_outcome(parse_request(_request(criteria=[_criterion(evidence_ids=[])])))
    assert outcome.state == CriterionState.UNKNOWN


def test_example_behavioral_tool_completion_supports() -> None:
    request = parse_request(
        _request(
            criteria=[
                _criterion(
                    scope="behavioral",
                    pointer="/reported_status",
                    operator="equals",
                    expected="completed",
                    evidence_ids=["act-1"],
                )
            ],
            evidence=[_action(reported_status="completed")],
        )
    )
    outcome = _first_outcome(request)
    assert outcome.state == CriterionState.SUPPORTED
    assert outcome.basis == Basis.DETERMINISTIC


# --------------------------------------------------------------------------
# policy configuration, parsing and hashing
# --------------------------------------------------------------------------


def test_policy_model_defaults_and_freeze() -> None:
    policy = VerificationPolicy()
    assert (policy.id, policy.version, policy.allow_model_inference) == ("strict", "1", False)
    custom = VerificationPolicy(id="custom", allow_model_inference=True)
    assert (custom.id, custom.allow_model_inference) == ("custom", True)
    from pydantic import ValidationError

    with pytest.raises(ValidationError, match="unknown"):
        VerificationPolicy(unknown=True)  # type: ignore[call-arg]
    with pytest.raises(ValidationError, match="frozen"):
        custom.allow_model_inference = False  # type: ignore[misc]


def test_parse_policy_accepts_valid_and_rejects_invalid() -> None:
    assert parse_policy({}) == VerificationPolicy()
    assert parse_policy('{"id": "custom", "allow_model_inference": true}') == VerificationPolicy(
        id="custom", allow_model_inference=True
    )
    assert parse_policy(b'{"id": "b"}').id == "b"
    with pytest.raises(RequestValidationError) as unknown_key:
        parse_policy({"id": "x", "threshold": 0.5})
    assert unknown_key.value.issues[0].code == InputErrorCode.INVALID_POLICY
    with pytest.raises(RequestValidationError) as bad_version:
        parse_policy({"version": "2"})
    assert bad_version.value.issues[0].code == InputErrorCode.INVALID_POLICY
    with pytest.raises(RequestValidationError) as bad_type:
        parse_policy({"allow_model_inference": "true"})
    assert bad_type.value.issues[0].code == InputErrorCode.INVALID_POLICY
    with pytest.raises(RequestValidationError) as duplicate:
        parse_policy('{"id": "a", "id": "b"}')
    assert duplicate.value.issues[0].code == InputErrorCode.INVALID_POLICY


def test_policy_hash_covers_every_effective_value() -> None:
    assert policy_hash(VerificationPolicy()) == STRICT_HASH
    assert policy_hash(VerificationPolicy(allow_model_inference=True)) == ALLOW_MODEL_HASH
    assert policy_hash(VerificationPolicy(id="custom")) != STRICT_HASH
    assert policy_hash(VerificationPolicy()) == policy_hash(VerificationPolicy())


def test_to_criterion_result_assembly() -> None:
    request = parse_request(_request())
    outcome = _first_outcome(request)
    result = to_criterion_result(request.criteria[0], outcome)
    assert result.criterion_id == "no-errors"
    assert result.state == CriterionState.REFUTED
    assert result.basis == Basis.DETERMINISTIC
    assert result.scope == "observed_state"
    assert [ref.evidence_id for ref in result.evidence_refs] == ["obs-1"]
    assert result.evidence_refs[0].grounding == Grounding.ASSERTION_CHECKED
    assert result.evaluations == outcome.evaluations
    assert result.reason_codes == outcome.reason_codes
    visual_request = _pol05_visual_request()
    visual_outcome = evaluate_criterion(
        visual_request.criteria[0],
        visual_request,
        ALLOW_MODEL,
        visual_finding=_visual_finding(CriterionState.REFUTED),
    )
    visual_result = to_criterion_result(visual_request.criteria[0], visual_outcome)
    assert visual_result.basis == Basis.MODEL_INFERRED
    assert visual_result.limitations == ("VISUAL_GROUNDING_UNVERIFIED",)
    assert visual_result.evaluations == ()
