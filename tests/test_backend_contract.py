"""BAK-01..05: custom visual backend boundary and capability validation (NIT-007).

Authority: docs/planning/04-verification-backends.md (protocol, capabilities,
prepared interface, preflight rules), 03 (finding/ref/score rules), 05 step 7,
07 (untrusted backend output), 12 (BAK family, mocking principles: fakes emit
valid and malformed structures and the ENGINE's reaction is asserted). The
action context arrives with NIT-009; contexts are built with actions=() here.
"""

from __future__ import annotations

import hashlib
from typing import Any

import pytest

from _imagekit import png_bytes
from nitelos import (
    BackendFinding,
    CriterionState,
    Decision,
    EvidenceRef,
    ExecutionStatus,
    Grounding,
    Score,
    ScoreKind,
    VerificationPolicy,
    Verifier,
    parse_request,
)
from nitelos.backends import BackendCapabilities, InferenceContext, PreparedVisualCriterion
from nitelos.backends.base import BackendOutputError
from nitelos.schemas import BackendDescriptor
from test_contract import _criterion, _screenshot, _visual_criterion

PNG = png_bytes(4, 4, "RGB", (10, 20, 30))
PNG_SHA = hashlib.sha256(PNG).hexdigest()
ALLOW_MODEL = VerificationPolicy(allow_model_inference=True)


def _shot_doc(evidence_id: str, sequence: int) -> dict[str, Any]:
    return _screenshot(
        id=evidence_id,
        sequence=sequence,
        artifact_id=f"art-{evidence_id}",
        width=4,
        height=4,
        sha256=PNG_SHA,
    )


def _visual_doc(
    shots: list[dict[str, Any]],
    *,
    evidence_ids: list[str] | None = None,
    criteria: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    from test_contract import _request

    if criteria is None:
        criteria = [_visual_criterion(evidence_ids=evidence_ids or [shot["id"] for shot in shots])]
    return _request(criteria=criteria, evidence=shots)


def _visual_request(shots: int, **kwargs: Any) -> Any:
    shot_docs = [_shot_doc(f"s{i}", i) for i in range(shots)]
    return parse_request(_visual_doc(shot_docs, **kwargs))


def _store(shots: int) -> dict[str, bytes]:
    return {f"art-s{i}": PNG for i in range(shots)}


class FakeVisualBackend:
    """Recording fake; findings may be a finding, a callable, None or an exception."""

    def __init__(
        self,
        findings: Any = None,
        *,
        max_images: int = 2,
        raise_exc: BaseException | None = None,
        criterion_kinds: tuple[str, ...] = ("visual",),
        evidence_kinds: tuple[str, ...] = ("screenshot",),
    ) -> None:
        self.findings = findings
        self.raise_exc = raise_exc
        self.max_images = max_images
        self.criterion_kinds = criterion_kinds
        self.evidence_kinds = evidence_kinds
        self.calls: list[tuple[PreparedVisualCriterion, InferenceContext]] = []
        self.closed = 0

    @property
    def descriptor(self) -> BackendDescriptor:
        return BackendDescriptor(id="fake-visual", version="1.0")

    @property
    def capabilities(self) -> BackendCapabilities:
        return BackendCapabilities(
            evidence_kinds=self.evidence_kinds,
            criterion_kinds=self.criterion_kinds,
            supports_images=True,
            supports_evidence_references=True,
            max_images_per_criterion=self.max_images,
        )

    def infer(self, prepared: PreparedVisualCriterion, context: InferenceContext) -> Any:
        self.calls.append((prepared, context))
        if self.raise_exc is not None:
            raise self.raise_exc
        if callable(self.findings):
            return self.findings(prepared, context)
        if self.findings is None:
            return self._default_finding(prepared)
        return self.findings

    def close(self) -> None:
        self.closed += 1

    def _default_finding(self, prepared: PreparedVisualCriterion) -> BackendFinding:
        return BackendFinding(
            criterion_id=prepared.criterion_id,
            state=CriterionState.SUPPORTED,
            evidence_refs=(EvidenceRef(evidence_id=prepared.images[0].evidence_id, bbox=(0, 0, 2, 2)),),
        )


def _supported_finding(criterion_id: str, evidence_id: str = "s0") -> BackendFinding:
    return BackendFinding(
        criterion_id=criterion_id,
        state=CriterionState.SUPPORTED,
        evidence_refs=(EvidenceRef(evidence_id=evidence_id, bbox=(0, 0, 2, 2)),),
    )


def _error(result: Any) -> Any:
    assert result.error is not None, result
    return result.error


# --------------------------------------------------------------------------
# end-to-end instance injection
# --------------------------------------------------------------------------


def test_fake_backend_supported_end_to_end() -> None:
    fake = FakeVisualBackend()
    result = Verifier(backend=fake, policy=ALLOW_MODEL).verify(_visual_request(1), artifacts=_store(1))
    assert result.execution_status == ExecutionStatus.OK
    assert result.decision == Decision.SUCCESS
    (criterion_result,) = result.criteria
    assert criterion_result.basis == "model_inferred"
    assert criterion_result.limitations == ("VISUAL_GROUNDING_UNVERIFIED",)
    (ref,) = criterion_result.evidence_refs
    assert ref.evidence_id == "s0"
    assert ref.grounding == "model_inferred"
    assert ref.bbox == (0, 0, 2, 2)
    assert len(fake.calls) == 1


def test_fake_backend_unknown_abstains_and_refuted_fails() -> None:
    unknown = FakeVisualBackend(
        findings=BackendFinding(criterion_id="appearance", state=CriterionState.UNKNOWN)
    )
    result = Verifier(backend=unknown, policy=ALLOW_MODEL).verify(_visual_request(1), artifacts=_store(1))
    assert result.decision == Decision.ABSTAINED
    assert result.criteria[0].reason_codes == ("MODEL_UNCERTAIN",)
    refuted = FakeVisualBackend(
        findings=BackendFinding(
            criterion_id="appearance",
            state=CriterionState.REFUTED,
            evidence_refs=(EvidenceRef(evidence_id="s0", bbox=(0, 0, 1, 1)),),
        )
    )
    result = Verifier(backend=refuted, policy=ALLOW_MODEL).verify(_visual_request(1), artifacts=_store(1))
    assert result.decision == Decision.FAILURE
    assert result.criteria[0].state == "refuted"


def test_images_passed_in_declared_reference_order() -> None:
    fake = FakeVisualBackend()
    request = _visual_request(2, evidence_ids=["s1", "s0"])
    Verifier(backend=fake, policy=ALLOW_MODEL).verify(request, artifacts=_store(2))
    (prepared, _context) = fake.calls[0]
    assert [image.evidence_id for image in prepared.images] == ["s1", "s0"]
    assert prepared.criterion_id == "appearance"
    assert prepared.description  # criterion description forwarded


def test_multiple_visual_criteria_invoke_per_criterion() -> None:
    fake = FakeVisualBackend(
        findings=lambda prepared, context: _supported_finding(
            prepared.criterion_id, prepared.images[0].evidence_id
        )
    )
    shots = [_shot_doc("s0", 0), _shot_doc("s1", 1)]
    criteria = [
        _visual_criterion(id="v1", evidence_ids=["s0"]),
        _visual_criterion(id="v2", evidence_ids=["s1"]),
    ]
    request = parse_request(_visual_doc(shots, criteria=criteria))
    result = Verifier(backend=fake, policy=ALLOW_MODEL).verify(request, artifacts=_store(2))
    assert result.decision == Decision.SUCCESS
    assert [call[0].criterion_id for call in fake.calls] == ["v1", "v2"]


# --------------------------------------------------------------------------
# BAK-01 / BAK-05: preflight, before any infer and regardless of policy
# --------------------------------------------------------------------------


def test_bak01_too_many_images_rejected_without_infer() -> None:
    fake = FakeVisualBackend(max_images=2)
    result = Verifier(backend=fake, policy=ALLOW_MODEL).verify(_visual_request(3), artifacts=_store(3))
    assert result.execution_status == ExecutionStatus.INPUT_ERROR
    assert _error(result).code == "UNSUPPORTED_CAPABILITY"
    assert _error(result).field_path == "$.criteria[0]"
    assert fake.calls == []


def test_bak01_unsupported_evidence_kind_rejected() -> None:
    from test_contract import _action
    from test_verifier import _digest, _obs

    fake = FakeVisualBackend(evidence_kinds=("screenshot",))
    action = _action(id="act-1", sequence=1)
    action["sha256"] = _digest(
        {
            "name": action["name"],
            "arguments": action["arguments"],
            "reported_status": action["reported_status"],
            "tool_result_id": None,
        }
    )
    doc = _visual_doc([_shot_doc("s0", 0), action], evidence_ids=["s0", "act-1"])
    result = Verifier(backend=fake, policy=ALLOW_MODEL).verify(parse_request(doc), artifacts=_store(1))
    assert result.execution_status == ExecutionStatus.INPUT_ERROR
    assert _error(result).code == "UNSUPPORTED_CAPABILITY"
    assert fake.calls == []
    # an assertion criterion on a visual-only backend is equally unsupported
    doc = _visual_doc([_obs()], criteria=[_criterion(operator="equals", expected=True)])
    result = Verifier(backend=fake, policy=ALLOW_MODEL).verify(parse_request(doc))
    assert _error(result).code == "UNSUPPORTED_CAPABILITY"


def test_bak05_wrong_kind_unsupported_even_with_inference_disallowed() -> None:
    fake = FakeVisualBackend(criterion_kinds=("visual",))
    verifier = Verifier(backend=fake)  # default strict policy
    # a visual criterion on a backend that does support visuals but with the
    # policy disallowing inference: preflight passes, no invocation
    result = verifier.verify(_visual_request(1), artifacts=_store(1))
    assert result.decision is None or result.decision == Decision.ABSTAINED
    assert result.criteria[0].reason_codes == ("MODEL_INFERENCE_DISALLOWED",)
    assert fake.calls == []
    # but an unsupported criterion KIND is an input error even when disallowed
    from test_verifier import _obs

    doc = _visual_doc([_obs()], criteria=[_criterion(operator="equals", expected=True)])
    wrong = verifier.verify(parse_request(doc))
    assert wrong.execution_status == ExecutionStatus.INPUT_ERROR
    assert _error(wrong).code == "UNSUPPORTED_CAPABILITY"


def test_disallowed_policy_never_invokes_the_backend() -> None:
    fake = FakeVisualBackend()
    result = Verifier(backend=fake).verify(_visual_request(1), artifacts=_store(1))
    assert result.execution_status == ExecutionStatus.OK
    assert result.decision == Decision.ABSTAINED
    assert fake.calls == []


# --------------------------------------------------------------------------
# BAK-02 / BAK-03 / BAK-04: finding validation
# --------------------------------------------------------------------------


def _backend_error_for(fake_findings: Any, *, shots: int = 1) -> Any:
    fake = FakeVisualBackend(findings=fake_findings)
    result = Verifier(backend=fake, policy=ALLOW_MODEL).verify(
        _visual_request(shots), artifacts=_store(shots)
    )
    assert result.execution_status == ExecutionStatus.BACKEND_ERROR, (
        f"expected backend_error, got {result.execution_status}: {result.error}"
    )
    assert result.decision is None
    assert "PARTIAL_RESULTS_NONAUTHORITATIVE" not in result.diagnostics.limitations or result.criteria
    return result.error


def test_bak02_missing_finding_is_invalid_output() -> None:
    error = _backend_error_for(lambda prepared, context: None)
    assert error.code == "INVALID_OUTPUT"


def test_bak02_non_finding_object_is_invalid_output() -> None:
    error = _backend_error_for(lambda prepared, context: {"state": "supported"})
    assert error.code == "INVALID_OUTPUT"


def test_bak02_foreign_criterion_id_is_invalid_output() -> None:
    error = _backend_error_for(lambda prepared, context: _supported_finding("some-other-criterion"))
    assert error.code == "INVALID_OUTPUT"


def test_bak02_invented_reference_is_invalid_evidence_reference() -> None:
    error = _backend_error_for(lambda prepared, context: _supported_finding("appearance", "ghost-image"))
    assert error.code == "INVALID_EVIDENCE_REFERENCE"


def test_bak02_decisive_finding_without_refs_is_invalid_evidence_reference() -> None:
    error = _backend_error_for(BackendFinding(criterion_id="appearance", state=CriterionState.SUPPORTED))
    assert error.code == "INVALID_EVIDENCE_REFERENCE"


def test_bak02_pointer_on_screenshot_and_out_of_bounds_bbox() -> None:
    pointer_ref = BackendFinding(
        criterion_id="appearance",
        state=CriterionState.SUPPORTED,
        evidence_refs=(EvidenceRef(evidence_id="s0", pointer="/x"),),
    )
    error = _backend_error_for(pointer_ref)
    assert error.code == "INVALID_EVIDENCE_REFERENCE"
    oob = BackendFinding(
        criterion_id="appearance",
        state=CriterionState.SUPPORTED,
        evidence_refs=(EvidenceRef(evidence_id="s0", bbox=(0, 0, 99, 99)),),
    )
    error = _backend_error_for(oob)
    assert error.code == "INVALID_EVIDENCE_REFERENCE"


def test_bak04_self_asserted_assertion_checked_grounding_rejected() -> None:
    forged = BackendFinding(
        criterion_id="appearance",
        state=CriterionState.SUPPORTED,
        evidence_refs=(
            EvidenceRef(evidence_id="s0", bbox=(0, 0, 2, 2), grounding=Grounding.ASSERTION_CHECKED),
        ),
    )
    error = _backend_error_for(forged)
    assert error.code == "INVALID_EVIDENCE_REFERENCE"


def test_bak03_calibrated_score_rejected() -> None:
    calibrated = BackendFinding(
        criterion_id="appearance",
        state=CriterionState.SUPPORTED,
        evidence_refs=(EvidenceRef(evidence_id="s0", bbox=(0, 0, 2, 2)),),
        score=Score(kind=ScoreKind.CALIBRATED_PROBABILITY, value=0.9, target="criterion_satisfied"),
    )
    error = _backend_error_for(calibrated)
    assert error.code == "UNSUPPORTED_CALIBRATION"


def test_bak03_null_and_uncalibrated_scores_retained_without_decision_effect() -> None:
    uncalibrated = BackendFinding(
        criterion_id="appearance",
        state=CriterionState.SUPPORTED,
        evidence_refs=(EvidenceRef(evidence_id="s0", bbox=(0, 0, 2, 2)),),
        score=Score(kind=ScoreKind.UNCALIBRATED_SCORE, value=4.5, target="criterion_satisfied", scale="0-5"),
    )
    fake = FakeVisualBackend(findings=uncalibrated)
    result = Verifier(backend=fake, policy=ALLOW_MODEL).verify(_visual_request(1), artifacts=_store(1))
    assert result.decision == Decision.SUCCESS  # from the state, not the score
    assert result.criteria[0].score is not None
    assert result.criteria[0].score.kind == "uncalibrated_score"
    unknown_with_null = BackendFinding(criterion_id="appearance", state=CriterionState.UNKNOWN)
    fake = FakeVisualBackend(findings=unknown_with_null)
    result = Verifier(backend=fake, policy=ALLOW_MODEL).verify(_visual_request(1), artifacts=_store(1))
    assert result.decision == Decision.ABSTAINED
    assert result.criteria[0].score is None


def test_infer_exception_becomes_safe_backend_exception() -> None:
    fake = FakeVisualBackend(raise_exc=RuntimeError("SECRET internal model detail"))
    result = Verifier(backend=fake, policy=ALLOW_MODEL).verify(_visual_request(1), artifacts=_store(1))
    assert result.execution_status == ExecutionStatus.BACKEND_ERROR
    assert _error(result).code == "BACKEND_EXCEPTION"
    assert "SECRET" not in result.model_dump_json()


# --------------------------------------------------------------------------
# isolation: no labels, trust or metadata enter prepared/context
# --------------------------------------------------------------------------


def test_context_and_prepared_carry_no_labels_trust_or_metadata() -> None:
    fake = FakeVisualBackend()
    doc = _visual_doc([_shot_doc("s0", 0)], evidence_ids=["s0"])
    doc["metadata"] = {"oracle_label": "success", "secret": "leak-me"}
    request = parse_request(doc)
    result = Verifier(backend=fake, policy=ALLOW_MODEL).verify(request, artifacts=_store(1))
    assert result.execution_status == ExecutionStatus.OK
    (prepared, context) = fake.calls[0]
    import dataclasses

    assert {field.name for field in dataclasses.fields(prepared)} == {"criterion_id", "description", "images"}
    assert {field.name for field in dataclasses.fields(context)} == {"objective", "actions", "deadline"}
    assert not hasattr(context, "metadata")
    assert not hasattr(context, "trust_bindings")
    assert not hasattr(context, "labels")
    image = prepared.images[0]
    assert {field.name for field in dataclasses.fields(image)} == {
        "evidence_id",
        "sequence",
        "width",
        "height",
        "rgb",
        "source_digest",
        "color_conversion",
    }
    assert "leak-me" not in result.model_dump_json()
    assert context.actions == ()


# --------------------------------------------------------------------------
# lifecycle and configuration
# --------------------------------------------------------------------------


def test_backend_closed_exactly_once_by_verifier_close() -> None:
    fake = FakeVisualBackend()
    verifier = Verifier(backend=fake)
    verifier.verify(_visual_request(1), artifacts=_store(1))
    verifier.close()
    verifier.close()  # idempotent: the backend sees exactly one close
    assert fake.closed == 1
    with Verifier(backend=FakeVisualBackend()) as managed:
        pass
    # context manager closes its own backend once


def test_non_backend_object_is_a_configuration_error() -> None:
    from nitelos.errors import ConfigurationError

    with pytest.raises(ConfigurationError):
        Verifier(backend=object())  # type: ignore[arg-type]
    with pytest.raises(ConfigurationError):
        Verifier(backend="nitelos.backends.smolvlm")  # type: ignore[arg-type]


def test_deterministic_backend_declares_no_visual_support() -> None:
    from nitelos import DeterministicBackend

    capabilities = DeterministicBackend().capabilities
    assert capabilities.criterion_kinds == ("assertion",)
    assert "visual" not in capabilities.criterion_kinds
    assert capabilities.max_images_per_criterion == 0
    assert not capabilities.supports_images
    assert not capabilities.supports_probabilities
    assert not capabilities.supports_calibrated_probabilities


def test_validate_backend_finding_is_reusable_by_backend_authors() -> None:
    from nitelos.backends import validate_backend_finding
    from nitelos.evidence import PreparedImage

    images = {
        "s0": PreparedImage(
            evidence_id="s0",
            sequence=0,
            width=4,
            height=4,
            rgb=bytes(4 * 4 * 3),
            source_digest="0" * 64,
            color_conversion="none",
        )
    }
    good = _supported_finding("appearance")
    validate_backend_finding(good, criterion_id="appearance", images=images)
    with pytest.raises(BackendOutputError) as forged:
        validate_backend_finding(
            BackendFinding(
                criterion_id="appearance",
                state=CriterionState.SUPPORTED,
                evidence_refs=(
                    EvidenceRef(evidence_id="s0", bbox=(0, 0, 2, 2), grounding=Grounding.ASSERTION_CHECKED),
                ),
            ),
            criterion_id="appearance",
            images=images,
        )
    assert forged.value.code == "INVALID_EVIDENCE_REFERENCE"
