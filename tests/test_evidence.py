"""EVD-01..04: evidence bytes, hashes, references and bounds (NIT-003).

Authority: docs/planning/03-domain-model-and-api.md ("Evidence", "Artifact
store and trusted context", "Limits", the EvidenceRef paragraph),
05-evidence-and-policies.md (provenance; algorithm step 1),
04-verification-backends.md (PreparedImage). Fixture literals were computed
independently with hashlib/canonical JSON and pasted as hex.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from subprocess import run
from sys import executable
from typing import Any

import pytest
from pydantic import ValidationError

from _imagekit import patch_png_dims, png_bytes
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

# Known-byte fixtures are embedded as hex literals so no encoder runs at test
# time: Pillow's PNG output differs across platforms (zlib vs zlib-ng), which
# would make byte-level digests platform-dependent. The digests below are
# literals of exactly these bytes, independent of the code under test.
LITERAL_PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000002000000030802000000368849"
    "d60000001149444154789c63fccf00024c60124601001440010550d52e380000"
    "000049454e44ae426082"
)
LITERAL_PNG_SHA = "18d0dcd567c88738923774a8dfaa470edd635d66c16ace15ab0331a6f57e02b5"
LITERAL_JPEG = bytes.fromhex(
    "ffd8ffe000104a46494600010100000100010000ffdb00430006040506050406"
    "060506070706080a100a0a09090a140e0f0c1017141818171416161a1d251f1a"
    "1b231c1616202c20232627292a29191f2d302d283025282928ffdb0043010707"
    "070a080a130a0a13281a161a2828282828282828282828282828282828282828"
    "282828282828282828282828282828282828282828282828282828282828ffc0"
    "0011080002000403012200021101031101ffc4001f0000010501010101010100"
    "000000000000000102030405060708090a0bffc400b510000201030302040305"
    "0504040000017d01020300041105122131410613516107227114328191a10823"
    "42b1c11552d1f02433627282090a161718191a25262728292a3435363738393a"
    "434445464748494a535455565758595a636465666768696a737475767778797a"
    "838485868788898a92939495969798999aa2a3a4a5a6a7a8a9aab2b3b4b5b6b7"
    "b8b9bac2c3c4c5c6c7c8c9cad2d3d4d5d6d7d8d9dae1e2e3e4e5e6e7e8e9eaf1"
    "f2f3f4f5f6f7f8f9faffc4001f01000301010101010101010100000000000001"
    "02030405060708090a0bffc400b5110002010204040304070504040001027700"
    "0102031104052131061241510761711322328108144291a1b1c109233352f015"
    "6272d10a162434e125f11718191a262728292a35363738393a43444546474849"
    "4a535455565758595a636465666768696a737475767778797a82838485868788"
    "898a92939495969798999aa2a3a4a5a6a7a8a9aab2b3b4b5b6b7b8b9bac2c3c4"
    "c5c6c7c8c9cad2d3d4d5d6d7d8d9dae2e3e4e5e6e7e8e9eaf2f3f4f5f6f7f8f9"
    "faffda000c03010002110311003f00e7e8a28afd84fca8ffd9"
)
LITERAL_JPEG_SHA = "b83dbe31c68034f2e8ea4f62c97b4990f8295ee661efa44199d637225b2fc46b"
# Runtime-generated images exercise the decode path; their declared digests are
# always computed from the bytes actually built, never from a fixed constant.
PNG_BYTES = png_bytes(2, 3, "RGB", (255, 0, 0))
PNG_SHA = hashlib.sha256(PNG_BYTES).hexdigest()
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
    shot = _shot(data=LITERAL_PNG)
    assert type(shot) is ScreenshotEvidence
    assert shot.sha256 == LITERAL_PNG_SHA
    assert shot.media_type == "image/png"
    assert (shot.width, shot.height) == (2, 3)
    jpeg = _shot(data=LITERAL_JPEG, artifact_id="art-j")
    assert jpeg.sha256 == LITERAL_JPEG_SHA
    assert jpeg.media_type == "image/jpeg"
    assert (jpeg.width, jpeg.height) == (4, 2)
    # runtime-encoded images digest their own exact bytes on every platform
    assert _shot().sha256 == PNG_SHA


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

    def counting(data: bytes) -> Any:
        calls.append(len(data))
        return real(data)

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


def test_prepare_rejects_decoded_dimension_mismatch(monkeypatch: pytest.MonkeyPatch) -> None:
    # A decoder (or a dual-SOF file) disagreeing with the header must fail closed
    # instead of producing a PreparedImage with inconsistent geometry.
    import nitelos.evidence as evidence_module

    def lying_decoder(data: bytes) -> Any:
        return (b"\x00" * (7 * 8 * 3), 7, 8, evidence_module.ColorConversion.NONE)

    monkeypatch.setattr(evidence_module, "_decode_artifact", lying_decoder)
    parsed = parse_request(_visual_doc([_shot_doc()], evidence_ids=["shot-1"]))
    _expect_error(
        lambda: prepare_evidence(parsed, ArtifactStore.from_bytes("art-1", PNG_BYTES)),
        InputErrorCode.INVALID_IMAGE,
    )


def test_prepare_rejects_inconsistent_pixel_buffer(monkeypatch: pytest.MonkeyPatch) -> None:
    import nitelos.evidence as evidence_module

    def short_buffer(data: bytes) -> Any:
        return (b"\x00" * 5, 2, 3, evidence_module.ColorConversion.NONE)

    monkeypatch.setattr(evidence_module, "_decode_artifact", short_buffer)
    parsed = parse_request(_visual_doc([_shot_doc()], evidence_ids=["shot-1"]))
    _expect_error(
        lambda: prepare_evidence(parsed, ArtifactStore.from_bytes("art-1", PNG_BYTES)),
        InputErrorCode.INVALID_IMAGE,
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
