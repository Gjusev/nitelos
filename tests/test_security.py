"""Security tests, structured by SEC ID (doc 07 threat table; doc 12 matrix).

Each section is owned by one task and later tasks append new sections. This
file currently contains:

- SEC-05 (NIT-003): image bombs and malformed images.
- SEC-06 (NIT-003): size/depth bounds exercised at the evidence layer.
"""

from __future__ import annotations

from typing import Any

import pytest
from PIL import Image

from _imagekit import (
    apng_bytes,
    cmyk_jpeg,
    gif_bytes,
    grayscale_png,
    jpeg_bytes,
    jpeg_with_orientation,
    pad_png_to_size,
    palette_png,
    patch_png_dims,
    pixel_of,
    png_bytes,
    rgba_png,
)
from nitelos import ArtifactStore, Evidence, parse_request, prepare_evidence
from nitelos.errors import EvidenceValidationError, InputErrorCode, RequestValidationError
from test_contract import _request, _screenshot, _visual_criterion

MIB = 1024 * 1024
PNG_BYTES = png_bytes(2, 3, "RGB", (255, 0, 0))
PNG_SHA = "18d0dcd567c88738923774a8dfaa470edd635d66c16ace15ab0331a6f57e02b5"


def _shot(data: bytes, **over: Any) -> Any:
    kwargs: dict[str, Any] = {
        "id": "shot-1",
        "artifact_id": "art-1",
        "data": data,
        "sequence": 0,
        "captured_at": "2024-06-01T10:00:00Z",
        "checkpoint_id": "cp",
        "source_id": "screen-collector",
        "subject": {"form": "registration-1"},
        "phase": "final",
    }
    kwargs.update(over)
    return Evidence.screenshot(**kwargs)


def _expect_error(action: Any, code: InputErrorCode) -> EvidenceValidationError:
    with pytest.raises(EvidenceValidationError) as excinfo:
        action()
    issue = excinfo.value.issue
    assert issue.code == code, f"expected {code}, got {issue.code} at {issue.field_path}"
    return excinfo.value


def _prepare_doc(artifacts: dict[str, bytes], **shot_over: Any) -> Any:
    doc = _request(
        criteria=[_visual_criterion(evidence_ids=["shot-1"])],
        evidence=[_screenshot(sha256=PNG_SHA, width=2, height=3)],
    )
    doc["evidence"][0].update(shot_over)
    parsed = parse_request(doc)
    return lambda: prepare_evidence(parsed, ArtifactStore(artifacts))


# ==========================================================================
# SEC-05 (NIT-003): image bombs and malformed images
# ==========================================================================


def test_sec05_invalid_signature_rejected() -> None:
    for garbage in (b"", b"RIFF\x00\x00\x00\x00WEBPVP8 ", b"\x89PNG\r\n\x1a\ntruncated"):
        _expect_error(lambda g=garbage: _shot(data=g), InputErrorCode.INVALID_IMAGE)
    # unsupported format with a valid signature of its own
    _expect_error(lambda: _shot(data=gif_bytes()), InputErrorCode.INVALID_IMAGE)


def test_sec05_truncated_images_rejected() -> None:
    # cut deep into the image data: a missing IEND/EOI alone is tolerated by decoders
    truncated_png = PNG_BYTES[:50]
    _expect_error(
        _prepare_doc({"art-1": truncated_png}, sha256=pytest_sha(truncated_png)),
        InputErrorCode.INVALID_IMAGE,
    )
    full_jpeg = jpeg_bytes(4, 2)
    truncated_jpeg = full_jpeg[:-40]
    _expect_error(
        _prepare_doc(
            {"art-1": truncated_jpeg},
            sha256=pytest_sha(truncated_jpeg),
            media_type="image/jpeg",
            width=4,
            height=2,
        ),
        InputErrorCode.INVALID_IMAGE,
    )


def pytest_sha(data: bytes) -> str:
    import hashlib

    return hashlib.sha256(data).hexdigest()


def test_sec05_animated_images_rejected() -> None:
    _expect_error(lambda: _shot(data=apng_bytes()), InputErrorCode.INVALID_IMAGE)
    _expect_error(lambda: _shot(data=gif_bytes()), InputErrorCode.INVALID_IMAGE)


def test_sec05_overlimit_header_dims_rejected_before_decode(monkeypatch: pytest.MonkeyPatch) -> None:
    import nitelos.evidence as evidence_module

    calls: list[int] = []
    real = evidence_module._decode_artifact

    def counting(data: bytes, media_type: str) -> Any:
        calls.append(len(data))
        return real(data, media_type)

    monkeypatch.setattr(evidence_module, "_decode_artifact", counting)
    crafted = patch_png_dims(PNG_BYTES, 4097, 8)
    _expect_error(lambda: _shot(data=crafted), InputErrorCode.LIMIT_EXCEEDED)
    crafted_pixels = patch_png_dims(PNG_BYTES, 3000, 1400)  # 4.2M > 4,194,304 pixels
    _expect_error(lambda: _shot(data=crafted_pixels), InputErrorCode.LIMIT_EXCEEDED)
    assert calls == [], "over-limit headers must be rejected without decoding"


def test_sec05_exif_orientation_rules() -> None:
    rotated = jpeg_with_orientation(4, 2, 6)
    _expect_error(
        _prepare_doc(
            {"art-1": rotated},
            sha256=pytest_sha(rotated),
            media_type="image/jpeg",
            width=4,
            height=2,
        ),
        InputErrorCode.INVALID_IMAGE,
    )
    upright = jpeg_with_orientation(4, 2, 1)
    prepare = _prepare_doc(
        {"art-1": upright},
        sha256=pytest_sha(upright),
        media_type="image/jpeg",
        width=4,
        height=2,
    )
    prepared = prepare()
    assert prepared.images["shot-1"].width == 4
    # absent orientation (plain JPEG) accepted
    plain = jpeg_bytes(4, 2)
    prepare2 = _prepare_doc(
        {"art-1": plain}, sha256=pytest_sha(plain), media_type="image/jpeg", width=4, height=2
    )
    prepare2()


def test_sec05_unsupported_modes_rejected() -> None:
    _expect_error(
        _prepare_doc({"art-1": palette_png(2, 3)}, sha256=pytest_sha(palette_png(2, 3))),
        InputErrorCode.INVALID_IMAGE,
    )
    cmyk = cmyk_jpeg(4, 2)
    _expect_error(
        _prepare_doc({"art-1": cmyk}, sha256=pytest_sha(cmyk), media_type="image/jpeg", width=4, height=2),
        InputErrorCode.INVALID_IMAGE,
    )


def test_sec05_grayscale_converted_to_rgb() -> None:
    gray = grayscale_png(2, 3, value=77)
    prepare = _prepare_doc({"art-1": gray}, sha256=pytest_sha(gray))
    image = prepare().images["shot-1"]
    assert image.color_conversion == "grayscale_to_rgb"
    assert pixel_of(image.rgb, 2, 0, 0) == (77, 77, 77)
    assert len(image.rgb) == 2 * 3 * 3


def test_sec05_rgba_composited_on_white() -> None:
    rgba = rgba_png(1, 1, (255, 0, 0, 128))
    prepare = _prepare_doc({"art-1": rgba}, sha256=pytest_sha(rgba), width=1, height=1)
    image = prepare().images["shot-1"]
    assert image.color_conversion == "rgba_on_white"
    assert pixel_of(image.rgb, 1, 0, 0) == (255, 127, 127)
    opaque = rgba_png(1, 1, (10, 20, 30, 255))
    prepare2 = _prepare_doc({"art-1": opaque}, sha256=pytest_sha(opaque), width=1, height=1)
    assert pixel_of(prepare2().images["shot-1"].rgb, 1, 0, 0) == (10, 20, 30)


def test_sec05_pillow_bomb_warnings_become_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    # Test-local lowering of Pillow's bomb threshold (restored by monkeypatch);
    # library code must never touch Image.MAX_IMAGE_PIXELS globally.
    monkeypatch.setattr(Image, "MAX_IMAGE_PIXELS", 4)
    prepare = _prepare_doc({"art-1": PNG_BYTES})
    _expect_error(prepare, InputErrorCode.LIMIT_EXCEEDED)


# ==========================================================================
# SEC-06 (NIT-003): size and count bounds at the evidence layer
# ==========================================================================


def test_sec06_per_image_bytes_at_max_and_max_plus_one() -> None:
    at_max = pad_png_to_size(png_bytes(2, 2), 8 * MIB)
    assert len(at_max) == 8 * MIB
    prepare = _prepare_doc({"art-1": at_max}, sha256=pytest_sha(at_max), width=2, height=2)
    prepared = prepare()
    assert prepared.images["shot-1"].source_digest == pytest_sha(at_max)
    over = pad_png_to_size(png_bytes(2, 2), 8 * MIB + 1)
    _expect_error(
        lambda: _shot(data=over),
        InputErrorCode.LIMIT_EXCEEDED,
    )


def test_sec06_total_image_bytes_at_max_and_max_plus_one() -> None:
    unit = pad_png_to_size(png_bytes(2, 2), 8 * MIB)
    unit_sha = pytest_sha(unit)
    artifacts = {f"art-{i}": unit for i in range(4)}
    doc = _request(
        criteria=[_visual_criterion(evidence_ids=["s0"])],
        evidence=[
            _screenshot(id=f"s{i}", sequence=i, artifact_id=f"art-{i}", sha256=unit_sha, width=2, height=2)
            for i in range(4)
        ],
    )
    parsed = parse_request(doc)
    prepared = prepare_evidence(parsed, ArtifactStore(artifacts))
    assert len(prepared.images) == 4
    over = dict(artifacts)
    over["art-extra"] = png_bytes(2, 2)
    _expect_error(lambda: prepare_evidence(parsed, ArtifactStore(over)), InputErrorCode.LIMIT_EXCEEDED)


def test_sec06_pixel_and_side_limits() -> None:
    wide = png_bytes(4096, 1)
    prepare = _prepare_doc({"art-1": wide}, sha256=pytest_sha(wide), width=4096, height=1)
    prepare()
    square = png_bytes(2048, 2048)  # 4,194,304 pixels exactly
    prepare2 = _prepare_doc({"art-1": square}, sha256=pytest_sha(square), width=2048, height=2048)
    prepare2()
    crafted = patch_png_dims(png_bytes(4, 1), 4097, 1)
    _expect_error(lambda: _shot(data=crafted), InputErrorCode.LIMIT_EXCEEDED)
    crafted2 = patch_png_dims(png_bytes(4, 1), 2048, 2049)  # 4,198,400 > pixel cap
    _expect_error(lambda: _shot(data=crafted2), InputErrorCode.LIMIT_EXCEEDED)


def test_sec06_screenshot_count_cross_check() -> None:
    unit = png_bytes(2, 2)
    unit_sha = pytest_sha(unit)
    shots = [
        _screenshot(id=f"s{i}", sequence=i, artifact_id=f"art-{i}", sha256=unit_sha, width=2, height=2)
        for i in range(16)
    ]
    doc = _request(
        criteria=[_visual_criterion(evidence_ids=["s0"])],
        evidence=shots,
    )
    parsed = parse_request(doc)
    prepared = prepare_evidence(parsed, ArtifactStore({f"art-{i}": unit for i in range(16)}))
    assert len(prepared.images) == 16
    seventeen = [
        _screenshot(id=f"s{i}", sequence=i, artifact_id=f"art-{i}", sha256=unit_sha, width=2, height=2)
        for i in range(17)
    ]
    doc17 = _request(
        criteria=[_visual_criterion(evidence_ids=["s0"])],
        evidence=seventeen,
    )
    with pytest.raises(RequestValidationError) as excinfo:
        parse_request(doc17)
    assert excinfo.value.issues[0].code == InputErrorCode.LIMIT_EXCEEDED
