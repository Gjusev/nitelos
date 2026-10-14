"""EVD-01..04: evidence bytes, hashes, references and bounds (NIT-003).

Authority: docs/planning/03-domain-model-and-api.md ("Evidence", "Artifact
store and trusted context", "Limits", the EvidenceRef paragraph),
05-evidence-and-policies.md (provenance; algorithm step 1),
04-verification-backends.md (PreparedImage). Fixture literals were computed
independently with hashlib/canonical JSON and pasted as hex.
"""

from __future__ import annotations

from datetime import UTC, datetime
from subprocess import run
from sys import executable
from typing import Any

import pytest
from pydantic import ValidationError

from _imagekit import jpeg_bytes, patch_png_dims, png_bytes
from nitelos import (
    ArtifactStore,
    Evidence,
    EvidenceRef,
    PreparedImage,
    parse_request,
    prepare_evidence,
    validate_evidence_ref,
)
from nitelos.errors import EvidenceValidationError, InputErrorCode
from nitelos.schemas import ActionEvidence, ObservationEvidence, ScreenshotEvidence, VerificationRequest
from test_contract import _observation, _request, _screenshot, _visual_criterion

PNG_BYTES = png_bytes(2, 3, "RGB", (255, 0, 0))
JPEG_BYTES = jpeg_bytes(4, 2)
PNG_SHA = "18d0dcd567c88738923774a8dfaa470edd635d66c16ace15ab0331a6f57e02b5"
JPEG_SHA = "b83dbe31c68034f2e8ea4f62c97b4990f8295ee661efa44199d637225b2fc46b"
OBS_SHA = "87993d0e64bfaa5251deb84357195a6568e45d5c3424778f1c433b56927f6a7b"
ACT_SHA = "fffb81389f29c40a9a90c78c7ca4a4ae40b67827d04d8ebd5a4cc30f47268181"
CAPTURED = datetime(2024, 6, 1, 10, 0, tzinfo=UTC)


def _shot(data: bytes = PNG_BYTES, **over: Any) -> ScreenshotEvidence:
    kwargs: dict[str, Any] = {
        "id": "shot-1",
        "artifact_id": "art-1",
        "data": data,
        "sequence": 0,
        "captured_at": CAPTURED,
        "checkpoint_id": "cp",
        "source_id": "screen-collector",
        "subject": {"form": "registration-1"},
        "phase": "final",
    }
    kwargs.update(over)
    return Evidence.screenshot(**kwargs)


def _shot_doc(**over: Any) -> dict[str, Any]:
    """Screenshot evidence mapping consistent with PNG_BYTES (overridable)."""
    item = _screenshot(sha256=PNG_SHA, width=2, height=3)
    item.update(over)
    return item


def _visual_doc(evidence: list[dict[str, Any]], evidence_ids: list[str] | None = None) -> dict[str, Any]:
    doc = _request(
        criteria=[_visual_criterion(evidence_ids=evidence_ids or [])],
        evidence=evidence,
    )
    return doc


def _expect_error(action: Any, code: InputErrorCode, path: str | None = None) -> EvidenceValidationError:
    with pytest.raises(EvidenceValidationError) as excinfo:
        action()
    issue = excinfo.value.issue
    assert issue.code == code, f"expected {code}, got {issue.code} at {issue.field_path}"
    if path is not None:
        assert issue.field_path == path, f"expected path {path}, got {issue.field_path}"
    return excinfo.value


# --------------------------------------------------------------------------
# EVD-01: exact hashes
# --------------------------------------------------------------------------


def test_evd01_screenshot_digest_is_known_byte_sha() -> None:
    shot = _shot()
    assert type(shot) is ScreenshotEvidence
    assert shot.sha256 == PNG_SHA
    assert shot.media_type == "image/png"
    assert (shot.width, shot.height) == (2, 3)
    jpeg = _shot(data=JPEG_BYTES, artifact_id="art-j")
    assert jpeg.sha256 == JPEG_SHA
    assert jpeg.media_type == "image/jpeg"
    assert (jpeg.width, jpeg.height) == (4, 2)


def test_evd01_observation_digest_is_canonical_json_sha() -> None:
    obs = Evidence.observation(
        id="obs-1",
        sequence=0,
        captured_at=CAPTURED,
        checkpoint_id="cp",
        source_id="app-collector",
        subject={"form": "registration-1"},
        phase="final",
        channel="dom",
        data={"validation_error": True},
    )
    assert type(obs) is ObservationEvidence
    assert obs.sha256 == OBS_SHA


def test_evd01_action_digest_basis_is_the_viewed_object() -> None:
    act = Evidence.action(
        id="act-1",
        sequence=1,
        captured_at=CAPTURED,
        checkpoint_id="cp",
        source_id="agent",
        subject={"form": "registration-1"},
        phase="final",
        name="submit-form",
        arguments={"email": "x@example.test"},
        reported_status="completed",
    )
    assert type(act) is ActionEvidence
    # digest over canonical JSON v1 of {name, arguments, reported_status, tool_result_id},
    # with a null tool_result_id included in the canonical object.
    assert act.sha256 == ACT_SHA


def test_evd01_integer_and_float_payloads_digest_differ() -> None:
    def digest(data: dict[str, Any]) -> str:
        return Evidence.observation(
            id="o",
            sequence=0,
            captured_at=CAPTURED,
            checkpoint_id="cp",
            source_id="s",
            subject={"form": "f"},
            phase="final",
            channel="dom",
            data=data,
        ).sha256

    assert digest({"v": 1}) != digest({"v": 1.0})


# --------------------------------------------------------------------------
# EVD-02: missing store entry vs empty evidence
# --------------------------------------------------------------------------


def test_evd02_missing_store_entry_is_missing_artifact() -> None:
    parsed = parse_request(_visual_doc([_shot_doc()]))
    _expect_error(
        lambda: prepare_evidence(parsed, ArtifactStore()),
        InputErrorCode.MISSING_ARTIFACT,
        "$.evidence[0].artifact_id",
    )


def test_evd02_empty_evidence_list_is_valid() -> None:
    parsed = parse_request(_visual_doc([]))
    prepared = prepare_evidence(parsed, ArtifactStore())
    assert dict(prepared.images) == {}


# --------------------------------------------------------------------------
# EVD-03: identical bytes, separate events, decoded once
# --------------------------------------------------------------------------


def test_evd03_identical_bytes_preserve_events_and_decode_once(monkeypatch: pytest.MonkeyPatch) -> None:
    import nitelos.evidence as evidence_module

    calls: list[int] = []
    real = evidence_module._decode_artifact

    def counting(data: bytes, media_type: str) -> Any:
        calls.append(len(data))
        return real(data, media_type)

    monkeypatch.setattr(evidence_module, "_decode_artifact", counting)
    doc = _visual_doc(
        [
            _shot_doc(id="s0", sequence=0, artifact_id="art-a"),
            _shot_doc(id="s1", sequence=1, artifact_id="art-b"),
        ],
        evidence_ids=["s0", "s1"],
    )
    parsed = parse_request(doc)
    store = ArtifactStore({"art-a": PNG_BYTES, "art-b": PNG_BYTES})
    prepared = prepare_evidence(parsed, store)
    assert calls == [len(PNG_BYTES)], "identical bytes must be decoded exactly once"
    assert set(prepared.images) == {"s0", "s1"}
    assert prepared.images["s0"].sequence == 0
    assert prepared.images["s1"].sequence == 1
    assert prepared.images["s0"].source_digest == PNG_SHA == prepared.images["s1"].source_digest


# --------------------------------------------------------------------------
# EVD-04: reference bounds and kind rules
# --------------------------------------------------------------------------


def _ref_fixture() -> tuple[VerificationRequest, Any]:
    doc = _visual_doc([_shot_doc()], evidence_ids=["shot-1"])
    doc["evidence"].append(_observation(id="obs-1", sequence=1, sha256=OBS_SHA))
    parsed = parse_request(doc)
    prepared = prepare_evidence(parsed, ArtifactStore.from_bytes("art-1", PNG_BYTES))
    return parsed, prepared


def test_evd04_bbox_at_exact_bounds_accepted() -> None:
    parsed, prepared = _ref_fixture()
    evidence_by_id = {item.id: item for item in parsed.evidence}
    validate_evidence_ref(
        EvidenceRef(evidence_id="shot-1", bbox=(0, 0, 2, 3)), evidence_by_id, prepared.images
    )
    validate_evidence_ref(
        EvidenceRef(evidence_id="shot-1", bbox=(1, 1, 2, 3)), evidence_by_id, prepared.images
    )


def test_evd04_bbox_beyond_dimensions_rejected() -> None:
    parsed, prepared = _ref_fixture()
    evidence_by_id = {item.id: item for item in parsed.evidence}
    _expect_error(
        lambda: validate_evidence_ref(
            EvidenceRef(evidence_id="shot-1", bbox=(0, 0, 3, 3)), evidence_by_id, prepared.images
        ),
        InputErrorCode.INVALID_IMAGE,
    )
    _expect_error(
        lambda: validate_evidence_ref(
            EvidenceRef(evidence_id="shot-1", bbox=(0, 0, 2, 4)), evidence_by_id, prepared.images
        ),
        InputErrorCode.INVALID_IMAGE,
    )
    # zero-area boxes are already rejected at schema level (half-open bounds)
    with pytest.raises(ValidationError):
        EvidenceRef(evidence_id="shot-1", bbox=(1, 0, 1, 3))


def test_evd04_reference_kind_rules() -> None:
    parsed, prepared = _ref_fixture()
    evidence_by_id = {item.id: item for item in parsed.evidence}
    validate_evidence_ref(EvidenceRef(evidence_id="obs-1", pointer="/x"), evidence_by_id, prepared.images)
    _expect_error(
        lambda: validate_evidence_ref(
            EvidenceRef(evidence_id="shot-1", pointer="/x"), evidence_by_id, prepared.images
        ),
        InputErrorCode.INVALID_POINTER,
    )
    _expect_error(
        lambda: validate_evidence_ref(
            EvidenceRef(evidence_id="obs-1", bbox=(0, 0, 1, 1)), evidence_by_id, prepared.images
        ),
        InputErrorCode.INVALID_IMAGE,
    )
    _expect_error(
        lambda: validate_evidence_ref(
            EvidenceRef(evidence_id="ghost", bbox=(0, 0, 1, 1)), evidence_by_id, prepared.images
        ),
        InputErrorCode.UNKNOWN_REFERENCE,
    )


# --------------------------------------------------------------------------
# ArtifactStore and factory behavior
# --------------------------------------------------------------------------


def test_artifact_store_copies_input_and_stays_immutable() -> None:
    mutable = bytearray(b"abc")
    store = ArtifactStore({"a": mutable})
    mutable.extend(b"DEF")  # caller mutates after construction
    assert store["a"] == b"abc"
    store2 = ArtifactStore.from_bytes("b", memoryview(b"xyz"))
    assert store2["b"] == b"xyz"
    assert len(store) == 1
    assert "a" in store
    assert "a" not in store2
    with pytest.raises(ValueError, match="artifact ids"):
        ArtifactStore({"not an id!": b"x"})
    text = repr(store) + repr(store2)
    assert "abc" not in text
    assert "xyz" not in text
    assert "'a'" in text


def test_factories_accept_no_trusted_flag() -> None:
    with pytest.raises(TypeError):
        _shot(trusted=True)  # type: ignore[call-arg]


def test_factory_rejects_bad_signatures_and_oversize() -> None:
    _expect_error(lambda: _shot(data=b"GIF89a-not-a-real-gif-anyway"), InputErrorCode.INVALID_IMAGE)
    _expect_error(lambda: _shot(data=b"\x00" * 64), InputErrorCode.INVALID_IMAGE)
    _expect_error(lambda: _shot(data=b"x" * (8 * 1024 * 1024 + 1)), InputErrorCode.LIMIT_EXCEEDED)
    _expect_error(lambda: _shot(data=patch_png_dims(PNG_BYTES, 5000, 3)), InputErrorCode.LIMIT_EXCEEDED)


def test_prepare_leaves_source_bytes_unchanged() -> None:
    parsed = parse_request(_visual_doc([_shot_doc()], evidence_ids=["shot-1"]))
    store = ArtifactStore.from_bytes("art-1", PNG_BYTES)
    before = store["art-1"]
    prepare_evidence(parsed, store)
    assert store["art-1"] == before == PNG_BYTES


def test_prepare_hash_and_declaration_mismatches() -> None:
    def prepared_doc(**over: Any) -> Any:
        return parse_request(_visual_doc([_shot_doc(**over)]))

    store = ArtifactStore.from_bytes("art-1", PNG_BYTES)
    _expect_error(
        lambda: prepare_evidence(prepared_doc(sha256="b" * 64), store),
        InputErrorCode.HASH_MISMATCH,
        "$.evidence[0].sha256",
    )
    _expect_error(
        lambda: prepare_evidence(prepared_doc(width=9), store),
        InputErrorCode.INVALID_IMAGE,
        "$.evidence[0].width",
    )
    _expect_error(
        lambda: prepare_evidence(prepared_doc(media_type="image/jpeg"), store),
        InputErrorCode.INVALID_IMAGE,
        "$.evidence[0].media_type",
    )
    doc = _request(evidence=[_observation(sha256="c" * 64)])
    _expect_error(
        lambda: prepare_evidence(parse_request(doc), ArtifactStore()),
        InputErrorCode.HASH_MISMATCH,
        "$.evidence[0].sha256",
    )


def test_prepare_validates_every_store_artifact_even_unused() -> None:
    parsed = parse_request(_visual_doc([_shot_doc()], evidence_ids=["shot-1"]))
    store = ArtifactStore({"art-1": PNG_BYTES, "art-unused": b"corrupt-but-unused"})
    _expect_error(lambda: prepare_evidence(parsed, store), InputErrorCode.INVALID_IMAGE)


def test_prepare_output_fields() -> None:
    parsed = parse_request(_visual_doc([_shot_doc()], evidence_ids=["shot-1"]))
    prepared = prepare_evidence(parsed, ArtifactStore.from_bytes("art-1", PNG_BYTES))
    image = prepared.images["shot-1"]
    assert isinstance(image, PreparedImage)
    assert (image.width, image.height) == (2, 3)
    assert len(image.rgb) == 2 * 3 * 3
    assert image.source_digest == PNG_SHA
    assert image.color_conversion == "none"
    assert isinstance(image.rgb, bytes)
    assert "255" not in repr(image)  # safe repr: no pixel contents


def test_import_evidence_module_stays_light() -> None:
    code = (
        "import sys\n"
        "import nitelos, nitelos.evidence\n"
        "heavy = [m for m in ('PIL', 'numpy', 'scipy') if m in sys.modules]\n"
        "assert not heavy, heavy\n"
    )
    proc = run([executable, "-c", code], check=False, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout == ""
