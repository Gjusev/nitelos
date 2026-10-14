"""SDK-01/02: end-to-end verifier SDK (NIT-006).

Authority: docs/planning/02-system-architecture.md (invocation lifecycle,
sync/async/resources, diagnostics), 03 (VerificationResult, exact Diagnostics
shape, error discipline), 05 (truth table), 11 (demonstration definition,
error handling discipline). All timing assertions tolerate any nonnegative
real measurement; no sleeps.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from typing import Any

import pytest

import nitelos
import nitelos.verifier as verifier_module
from _imagekit import png_bytes
from nitelos import (
    Decision,
    DeterministicBackend,
    ExecutionStatus,
    TrustBinding,
    VerificationPolicy,
    Verifier,
    canonical_json,
    parse_request,
)
from test_contract import SHA, _criterion, _observation, _request, _screenshot, _visual_criterion

SUBJECT = {"form": "registration-1"}
SENTINEL = "SECRET-SENTINEL-3f9a"


def _digest(data: Any) -> str:
    return hashlib.sha256(canonical_json(data).encode("utf-8")).hexdigest()


def _obs(**over: Any) -> dict[str, Any]:
    """Observation fixture whose sha256 matches its canonical payload digest."""
    over.setdefault("data", {"validation_error": True})
    over.setdefault("sha256", _digest(over["data"]))
    return _observation(**over)


def _binding(evidence_id: str, **over: Any) -> TrustBinding:
    values: dict[str, Any] = {
        "evidence_id": evidence_id,
        "sha256": SHA,
        "source_id": "ledger",
        "subject": dict(SUBJECT),
        "checkpoint_id": "cp",
    }
    values.update(over)
    return TrustBinding(**values)


def _obs_ext(evidence_id: str, data: dict[str, Any], **over: Any) -> dict[str, Any]:
    item = _obs(id=evidence_id, channel="external_api", source_id="ledger", data=data, subject=dict(SUBJECT))
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


# --------------------------------------------------------------------------
# SDK-01: the demonstration definition (doc 11), end to end
# --------------------------------------------------------------------------


def test_sdk01_validation_error_with_agent_success_claim_is_failure() -> None:
    request = parse_request(
        _request(
            objective="Agent summary claims registration succeeded",
            criteria=[_criterion(operator="equals", expected=False)],
            evidence=[_obs()],
        )
    )
    result = Verifier().verify(request)
    assert result.execution_status == ExecutionStatus.OK
    assert result.decision == Decision.FAILURE
    (criterion_result,) = result.criteria
    assert criterion_result.criterion_id == "no-errors"
    assert criterion_result.state == "refuted"
    (ref,) = criterion_result.evidence_refs
    assert ref.evidence_id == "obs-1"
    assert ref.pointer == "/validation_error"
    assert ref.grounding == "assertion_checked"
    assert result.reason_codes[0] == "CRITERION_REFUTED"


def test_sdk01_confirmed_final_state_with_trusted_binding_is_success() -> None:
    request = parse_request(
        _request(
            criteria=[_ext_crit(["ledger-1"])],
            evidence=[_obs_ext("ledger-1", {"status": "paid"})],
        )
    )
    result = Verifier(trust_bindings=(_binding("ledger-1", sha256=_digest({"status": "paid"})),)).verify(
        request
    )
    assert result.execution_status == ExecutionStatus.OK
    assert result.decision == Decision.SUCCESS
    assert result.criteria[0].state == "supported"
    assert result.reason_codes[0] == "ALL_CRITERIA_SUPPORTED"


def test_sdk01_tool_success_only_abstains_for_external_criterion() -> None:
    request = parse_request(
        _request(
            criteria=[_ext_crit([])],
            evidence=[_obs(id="tool-1", channel="tool", data={"upload": "ok"})],
        )
    )
    result = Verifier().verify(request)
    assert result.execution_status == ExecutionStatus.OK
    assert result.decision == Decision.ABSTAINED
    assert result.criteria[0].reason_codes == ("MISSING_EVIDENCE",)


def test_sdk01_one_result_per_criterion_in_order() -> None:
    request = parse_request(
        _request(
            criteria=[
                _criterion(id="a", operator="equals", expected=True),
                _criterion(id="b", evidence_ids=[], operator="equals", expected=True),
                _criterion(id="c", operator="equals", expected=False),
            ],
            evidence=[_obs()],
        )
    )
    result = Verifier().verify(request)
    assert result.execution_status == ExecutionStatus.OK
    assert result.decision == Decision.FAILURE  # c refuted dominates
    assert [c.criterion_id for c in result.criteria] == ["a", "b", "c"]
    assert [c.state for c in result.criteria] == ["supported", "unknown", "refuted"]


def test_sdk01_mapping_string_and_typed_inputs_agree() -> None:
    mapping = _request(criteria=[_criterion(operator="equals", expected=True)], evidence=[_obs()])
    from_mapping = Verifier().verify(mapping)
    from_typed = Verifier().verify(parse_request(json.loads(json.dumps(mapping))))
    from_string = Verifier().verify(json.dumps(mapping))
    assert from_mapping.execution_status == ExecutionStatus.OK
    assert from_mapping.decision == from_typed.decision == from_string.decision
    assert [c.state for c in from_mapping.criteria] == ["supported"]


# --------------------------------------------------------------------------
# SDK-02: input errors and validation gates
# --------------------------------------------------------------------------


def test_sdk02_invalid_mapping_is_input_error_without_evaluation(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []
    real_prepare = verifier_module.prepare_evidence
    real_evaluate = verifier_module.evaluate_criterion

    def recording_prepare(request: Any, store: Any) -> Any:
        calls.append("prepare")
        return real_prepare(request, store)

    def recording_evaluate(*args: Any, **kwargs: Any) -> Any:
        calls.append("evaluate")
        return real_evaluate(*args, **kwargs)

    monkeypatch.setattr(verifier_module, "prepare_evidence", recording_prepare)
    monkeypatch.setattr(verifier_module, "evaluate_criterion", recording_evaluate)
    bad = _request()
    bad["criteria"][0]["scope"] = "nonsense"
    result = Verifier().verify(bad)
    assert result.execution_status == ExecutionStatus.INPUT_ERROR
    assert result.decision is None
    assert result.criteria == ()
    assert result.error is not None
    assert result.error.code == "INVALID_SCHEMA"
    assert result.error.retryable is False
    assert result.error.field_path == "$.criteria[0].scope"
    assert calls == [], "no evaluation may run for an invalid mapping"


def test_sdk02_visual_criteria_rejected_by_deterministic_backend() -> None:
    png = png_bytes(2, 3, "RGB", (255, 0, 0))
    request = parse_request(
        _request(
            criteria=[_visual_criterion(evidence_ids=["shot-1"])],
            evidence=[_screenshot(sha256=hashlib.sha256(png).hexdigest(), width=2, height=3)],
        )
    )
    result = Verifier().verify(request, artifacts={"art-1": png})
    assert result.execution_status == ExecutionStatus.INPUT_ERROR
    assert result.error is not None
    assert result.error.code == "UNSUPPORTED_CAPABILITY"
    assert result.error.field_path == "$.criteria[0]"
    # empty-citation visual criteria are rejected identically, before any work
    empty = parse_request(_request(criteria=[_visual_criterion(evidence_ids=[])], evidence=[]))
    rejected = Verifier().verify(empty)
    assert rejected.error is not None
    assert rejected.error.code == "UNSUPPORTED_CAPABILITY"


def test_sdk02_typed_request_over_ceiling_is_limit_exceeded() -> None:
    request = parse_request(_request(criteria=[_criterion(operator="equals", expected=True)]))
    oversized = request.model_copy(update={"metadata": {"filler": "x" * 9000}})
    result = Verifier().verify(oversized)
    assert result.execution_status == ExecutionStatus.INPUT_ERROR
    assert result.error is not None
    assert result.error.code == "LIMIT_EXCEEDED"
    assert result.error.field_path == "$.metadata"


def test_sdk02_generic_policy_paths_are_repathed_to_criterion_positions() -> None:
    # criterion 1 cites a screenshot with an observed_state scope: the policy's
    # generic $.evidence capability path must surface at the criterion position
    png = png_bytes(2, 2)
    request = parse_request(
        _request(
            criteria=[
                _criterion(id="ok", operator="equals", expected=True),
                _criterion(id="bad", evidence_ids=["shot-1"]),
            ],
            evidence=[
                _obs(),
                _screenshot(sequence=1, width=2, height=2, sha256=hashlib.sha256(png).hexdigest()),
            ],
        )
    )
    result = Verifier().verify(request, artifacts={"art-1": png})
    assert result.execution_status == ExecutionStatus.INPUT_ERROR
    assert result.error is not None
    assert result.error.field_path == "$.criteria[1].evidence"
    # the re-path helper covers the other generic roots
    from nitelos.errors import InputErrorCode, Issue
    from nitelos.verifier import _repath_issue

    assert (
        _repath_issue(Issue(InputErrorCode.INVALID_POINTER, "$.pointer", "m"), 3).field_path
        == "$.criteria[3].pointer"
    )
    assert (
        _repath_issue(Issue(InputErrorCode.INVALID_IMAGE, "$.evidence_refs", "m"), 0).field_path
        == "$.criteria[0].evidence_refs"
    )
    assert _repath_issue(
        Issue(InputErrorCode.MISSING_ARTIFACT, "$.evidence[2].artifact_id", "m"), 1
    ).field_path == ("$.evidence[2].artifact_id")


def test_sdk02_prepare_evidence_gates_are_input_errors() -> None:
    png = png_bytes(2, 3)
    request = parse_request(
        _request(
            criteria=[_criterion(operator="equals", expected=True, evidence_ids=[])],
            evidence=[_screenshot(sha256=hashlib.sha256(png).hexdigest(), width=2, height=3)],
        )
    )
    result = Verifier().verify(request)  # no artifacts supplied
    assert result.execution_status == ExecutionStatus.INPUT_ERROR
    assert result.error is not None
    assert result.error.code == "MISSING_ARTIFACT"


def test_sdk02_unreadable_request_id_uses_documented_placeholder() -> None:
    result = Verifier().verify(42)  # type: ignore[arg-type]
    assert result.execution_status == ExecutionStatus.INPUT_ERROR
    assert result.request_id == "unknown-request"
    # a salvageable request_id is preserved on input errors
    bad = _request(objective="")
    salvaged = Verifier().verify(bad)
    assert salvaged.execution_status == ExecutionStatus.INPUT_ERROR
    assert salvaged.request_id == "demo-1"


def test_sdk02_verification_id_is_uuid4() -> None:
    request = parse_request(_request(criteria=[_criterion(operator="equals", expected=True)]))
    result = Verifier().verify(request)
    assert uuid.UUID(result.verification_id).version == 4
    assert result.request_id == "demo-1"


def test_sdk02_configuration_errors() -> None:
    with pytest.raises(nitelos.ConfigurationError):
        Verifier(backend="deterministic")  # type: ignore[arg-type]
    with pytest.raises(nitelos.ConfigurationError):
        Verifier(backend=object())  # type: ignore[arg-type]
    with pytest.raises(nitelos.ConfigurationError):
        Verifier(policy={"id": "strict"})  # type: ignore[arg-type]
    with pytest.raises(nitelos.ConfigurationError):
        Verifier(trust_bindings=("binding",))  # type: ignore[arg-type]
    with pytest.raises(nitelos.ConfigurationError, match="duplicate"):
        Verifier(trust_bindings=(_binding("e-1"), _binding("e-1")))
    Verifier(
        backend=DeterministicBackend(),
        policy=VerificationPolicy(id="custom"),
        trust_bindings=(_binding("e-1"), _binding("e-2")),
    )  # valid configuration constructs fine


# --------------------------------------------------------------------------
# backend errors, partial results and the development re-raise
# --------------------------------------------------------------------------


def test_backend_exception_is_safe_and_partial_results_survive(monkeypatch: pytest.MonkeyPatch) -> None:
    real_evaluate = verifier_module.evaluate_criterion

    def failing(criterion: Any, *args: Any, **kwargs: Any) -> Any:
        if criterion.id == "boom":
            raise RuntimeError(f"internal detail with {SENTINEL}")
        return real_evaluate(criterion, *args, **kwargs)

    monkeypatch.setattr(verifier_module, "evaluate_criterion", failing)
    request = parse_request(
        _request(
            criteria=[
                _criterion(id="fine", operator="equals", expected=True),
                _criterion(id="boom", operator="equals", expected=True),
                _criterion(id="after", operator="equals", expected=True),
            ],
            evidence=[_obs()],
        )
    )
    result = Verifier().verify(request)
    assert result.execution_status == ExecutionStatus.BACKEND_ERROR
    assert result.decision is None
    assert result.error is not None
    assert result.error.code == "BACKEND_EXCEPTION"
    assert result.error.retryable is False
    assert SENTINEL not in result.model_dump_json()
    assert [c.criterion_id for c in result.criteria] == ["fine"]  # partial, non-authoritative
    assert "PARTIAL_RESULTS_NONAUTHORITATIVE" in result.diagnostics.limitations


def test_dev_reraise_setting_propagates_exceptions(monkeypatch: pytest.MonkeyPatch) -> None:
    def failing(criterion: Any, *args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("dev detail")

    monkeypatch.setattr(verifier_module, "evaluate_criterion", failing)
    request = parse_request(
        _request(criteria=[_criterion(operator="equals", expected=True)], evidence=[_obs()])
    )
    with pytest.raises(RuntimeError, match="dev detail"):
        Verifier(dev_reraise=True).verify(request)
    # off by default: the normal verifier converts instead
    assert Verifier().verify(request).execution_status == ExecutionStatus.BACKEND_ERROR


def test_keyboard_interrupt_and_system_exit_propagate(monkeypatch: pytest.MonkeyPatch) -> None:
    request = parse_request(
        _request(criteria=[_criterion(operator="equals", expected=True)], evidence=[_obs()])
    )

    def interrupted(criterion: Any, *args: Any, **kwargs: Any) -> Any:
        raise KeyboardInterrupt()

    monkeypatch.setattr(verifier_module, "evaluate_criterion", interrupted)
    with pytest.raises(KeyboardInterrupt):
        Verifier().verify(request)

    def exiting(criterion: Any, *args: Any, **kwargs: Any) -> Any:
        raise SystemExit(3)

    monkeypatch.setattr(verifier_module, "evaluate_criterion", exiting)
    with pytest.raises(SystemExit):
        Verifier().verify(request)


# --------------------------------------------------------------------------
# diagnostics: exact doc-03 shape with real measurements
# --------------------------------------------------------------------------


def test_diagnostics_exact_shape_and_real_measurements() -> None:
    request = parse_request(
        _request(
            criteria=[_criterion(id="no-errors", operator="equals", expected=True)],
            evidence=[_obs()],
            metadata={"k": "v"},
        )
    )
    result = Verifier(policy=VerificationPolicy(id="custom")).verify(request)
    diagnostics = result.diagnostics
    assert diagnostics.package_version == nitelos.__version__
    assert diagnostics.schema_version == "1"
    assert diagnostics.policy_id == "custom"
    assert diagnostics.policy_version == "1"
    from nitelos.policy import policy_hash

    assert diagnostics.policy_hash == policy_hash(VerificationPolicy(id="custom"))
    assert diagnostics.backend.id == "deterministic"
    assert diagnostics.backend.version == nitelos.__version__
    assert diagnostics.backend.model_id is None
    # fingerprints via canonical JSON v1, independently recomputed here
    expected_request_hash = hashlib.sha256(
        canonical_json(request.model_dump(mode="json")).encode("utf-8")
    ).hexdigest()
    assert diagnostics.request_hash == expected_request_hash
    expected_manifest = _digest([{"evidence_id": "obs-1", "sha256": _digest({"validation_error": True})}])
    assert diagnostics.evidence_manifest_hash == expected_manifest
    # real timing measurements
    assert isinstance(diagnostics.elapsed_ms, float)
    assert diagnostics.elapsed_ms >= 0.0
    assert set(diagnostics.criterion_durations_ms) == {"no-errors"}
    assert all(value >= 0.0 for value in diagnostics.criterion_durations_ms.values())
    assert diagnostics.model_load_ms is None
    assert diagnostics.omitted_context_ids == ()
    assert diagnostics.preprocessing == ()
    measurements = diagnostics.measurements
    assert measurements.input_tokens is None
    assert measurements.cost_amount is None
    assert measurements.unavailable_reasons  # nulls carry reasons
    assert diagnostics.limitations == ()


def test_diagnostics_null_fingerprints_on_input_error() -> None:
    result = Verifier().verify(42)  # type: ignore[arg-type]
    assert result.execution_status == ExecutionStatus.INPUT_ERROR
    assert result.diagnostics.request_hash is None
    assert result.diagnostics.evidence_manifest_hash is None
    assert result.diagnostics.policy_id == "strict"  # configured identity remains
    assert result.diagnostics.elapsed_ms >= 0.0


def test_verifier_is_reusable_across_calls() -> None:
    verifier = Verifier()
    request = parse_request(
        _request(criteria=[_criterion(operator="equals", expected=True)], evidence=[_obs()])
    )
    first = verifier.verify(request)
    second = verifier.verify(request)
    assert first.execution_status == second.execution_status == ExecutionStatus.OK
    assert first.verification_id != second.verification_id
