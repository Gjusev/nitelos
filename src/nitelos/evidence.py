"""Evidence bytes, hashes, references and bounds (NIT-003).

Authority: docs/planning/03-domain-model-and-api.md ("Evidence", "Artifact
store and trusted context", "Limits"), 05-evidence-and-policies.md
("Provenance without false authenticity claims"; algorithm step 1),
07-security-and-privacy.md (image bomb / oversized payload rows),
04-verification-backends.md (PreparedImage).

Digest bases (document 03 "compute observation/action hashes over canonical
payload"):

- screenshots: SHA-256 over the exact artifact bytes supplied to the factory;
- observations: SHA-256 over Nitelos canonical JSON v1 of the ``data`` object;
- actions: SHA-256 over canonical JSON v1 of exactly
  ``{name, arguments, reported_status, tool_result_id}`` (the object action
  assertions view; ``tool_result_id`` is included as null when absent).
  Canonical JSON keeps ``1`` and ``1.0`` textually distinct, so those payloads
  digest differently.

Validation layering: the factories perform the cheap header-level checks
(byte ceiling, signature, header dimensions, single-frame) because they need
that metadata anyway; full decode-time safety (EXIF orientation, pixel mode,
bounded decode, conversion) happens in :func:`prepare_evidence` and in
artifact validation. Pillow is imported lazily inside decode paths only, so
``import nitelos`` and even ``import nitelos.evidence`` stay light.

Field paths for store-level failures use the ``$.artifacts[<artifact-id>]``
namespace (artifacts are host-supplied and not part of request JSON).

Interpretations (conservative):

- mode ``LA`` is accepted (grayscale with alpha per the task brief) and
  recorded as ``rgba_on_white``: alpha is composited on white, then the
  grayscale result is converted to RGB;
- a bbox/pointer kind mismatch or an out-of-bounds bbox is INVALID_IMAGE,
  a pointer on a screenshot is INVALID_POINTER (doc 05 step 1 groups box
  validation with structural input errors);
- the factories validate header-level limits but do not decode, so a
  truncated or exotic-mode image can pass a factory and is rejected during
  preparation, which is the gate the verifier runs.
"""

from __future__ import annotations

import hashlib
import io
import struct
import warnings
from collections.abc import Iterator, Mapping, ValuesView
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

from pydantic import TypeAdapter, ValidationError

from nitelos.errors import EvidenceValidationError, InputErrorCode, Issue
from nitelos.schemas import (
    ActionEvidence,
    ColorConversion,
    EvidenceRef,
    IDType,
    ObservationEvidence,
    ScreenshotEvidence,
    VerificationRequest,
    canonical_json,
)

__all__ = [
    "ArtifactStore",
    "PreparedEvidence",
    "PreparedImage",
    "prepare_evidence",
    "validate_evidence_ref",
]

MAX_IMAGE_BYTES = 8 * 1024 * 1024
MAX_TOTAL_IMAGE_BYTES = 32 * 1024 * 1024
MAX_IMAGE_PIXELS = 4_194_304
MAX_IMAGE_SIDE = 4096

_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
_TA_ID = TypeAdapter(IDType)


def _ev(code: InputErrorCode, path: str, message: str) -> EvidenceValidationError:
    return EvidenceValidationError(Issue(code, path, message))


def _check_artifact_id(artifact_id: object) -> None:
    try:
        _TA_ID.validate_python(artifact_id)
    except ValidationError:
        raise ValueError("artifact ids must be ID strings") from None


# ---------------------------------------------------------------------------
# artifact store
# ---------------------------------------------------------------------------


class ArtifactStore:
    """Immutable artifact-ID → bytes mapping for one invocation.

    Bytes are copied on construction (bytearray/memoryview inputs become
    immutable ``bytes``); the store performs no file, path or URL resolution
    anywhere. The repr shows IDs and sizes only.
    """

    __slots__ = ("_artifacts",)

    def __init__(self, artifacts: Mapping[str, bytes | bytearray | memoryview] | None = None) -> None:
        copied: dict[str, bytes] = {}
        for artifact_id, data in (artifacts or {}).items():
            _check_artifact_id(artifact_id)
            copied[artifact_id] = bytes(data)
        self._artifacts = MappingProxyType(copied)

    @classmethod
    def from_bytes(cls, artifact_id: str, data: bytes | bytearray | memoryview) -> ArtifactStore:
        """Convenience constructor for a single artifact (document 03)."""
        return cls({artifact_id: data})

    def __getitem__(self, artifact_id: str) -> bytes:
        return self._artifacts[artifact_id]

    def __contains__(self, artifact_id: object) -> bool:
        return artifact_id in self._artifacts

    def __len__(self) -> int:
        return len(self._artifacts)

    def __iter__(self) -> Iterator[str]:
        return iter(self._artifacts)

    def values(self) -> ValuesView[bytes]:
        return self._artifacts.values()

    def __repr__(self) -> str:
        entries = ", ".join(f"{key!r}: {len(value)} bytes" for key, value in self._artifacts.items())
        return f"ArtifactStore({{{entries}}})"


# ---------------------------------------------------------------------------
# digest helpers
# ---------------------------------------------------------------------------


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _payload_digest(payload: Mapping[str, object], field: str) -> str:
    try:
        text = canonical_json(payload)
    except ValueError:
        raise _ev(InputErrorCode.INVALID_SCHEMA, field, "payload must contain only JSON values") from None
    return _digest(text.encode("utf-8"))


# ---------------------------------------------------------------------------
# header-level image inspection (no decode)
# ---------------------------------------------------------------------------


def _check_dimensions(width: int, height: int) -> None:
    if width < 1 or height < 1:
        raise _ev(InputErrorCode.INVALID_IMAGE, "$", "image dimensions must be positive")
    if width > MAX_IMAGE_SIDE or height > MAX_IMAGE_SIDE:
        raise _ev(InputErrorCode.LIMIT_EXCEEDED, "$", "image side exceeds the pixel limit")
    if width * height > MAX_IMAGE_PIXELS:
        raise _ev(InputErrorCode.LIMIT_EXCEEDED, "$", "image exceeds the total pixel limit")


def _inspect_png(data: bytes) -> tuple[str, int, int]:
    if len(data) < 24:
        raise _ev(InputErrorCode.INVALID_IMAGE, "$", "truncated PNG header")
    width, height = struct.unpack(">II", data[16:24])
    _check_dimensions(width, height)
    offset = 8
    end = len(data)
    while offset + 8 <= end:
        chunk_length = struct.unpack(">I", data[offset : offset + 4])[0]
        chunk_type = data[offset + 4 : offset + 8]
        if chunk_type == b"acTL":
            raise _ev(InputErrorCode.INVALID_IMAGE, "$", "animated PNG is not supported")
        if chunk_type == b"IEND":
            break
        offset += 12 + chunk_length
    return "image/png", width, height


def _inspect_jpeg(data: bytes) -> tuple[str, int, int]:
    index = 2
    end = len(data)
    while index + 4 < end:
        if data[index] != 0xFF:
            index += 1
            continue
        marker = data[index + 1]
        if marker == 0xFF:
            index += 1
            continue
        if marker in {0x01, 0xD8} or 0xD0 <= marker <= 0xD7:
            index += 2
            continue
        if marker == 0xD9:
            break
        segment_length = struct.unpack(">H", data[index + 2 : index + 4])[0]
        if segment_length < 2:
            raise _ev(InputErrorCode.INVALID_IMAGE, "$", "invalid JPEG segment")
        if (marker & 0xF0) == 0xC0 and marker not in (0xC4, 0xC8, 0xCC):
            if index + 9 > end:
                raise _ev(InputErrorCode.INVALID_IMAGE, "$", "truncated JPEG header")
            height = struct.unpack(">H", data[index + 5 : index + 7])[0]
            width = struct.unpack(">H", data[index + 7 : index + 9])[0]
            _check_dimensions(width, height)
            return "image/jpeg", width, height
        index += 2 + segment_length
    raise _ev(InputErrorCode.INVALID_IMAGE, "$", "no JPEG frame header found")


def _inspect_image(data: bytes) -> tuple[str, int, int]:
    """Header-level checks in the documented order; never decodes."""
    if len(data) > MAX_IMAGE_BYTES:
        raise _ev(InputErrorCode.LIMIT_EXCEEDED, "$", "image exceeds the per-image byte limit")
    if data[:8] == _PNG_SIGNATURE:
        return _inspect_png(data)
    if data[:2] == b"\xff\xd8":
        return _inspect_jpeg(data)
    raise _ev(InputErrorCode.INVALID_IMAGE, "$", "unrecognized image signature")


# ---------------------------------------------------------------------------
# bounded decode (Pillow, lazy)
# ---------------------------------------------------------------------------


def _decode_artifact(data: bytes) -> tuple[bytes, int, int, ColorConversion]:
    """Full decode with EXIF/mode/frame checks; returns RGB bytes.

    Pillow's decompression-bomb warning/error are turned into coded failures
    inside a local warnings context; the global MAX_IMAGE_PIXELS setting is
    never modified.
    """
    from PIL import Image  # noqa: PLC0415 - lazy so importing nitelos stays light

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            image = Image.open(io.BytesIO(data))
            orientation = image.getexif().get(274)
            if orientation is not None and orientation != 1:
                raise _ev(InputErrorCode.INVALID_IMAGE, "$", "EXIF orientation must be absent or 1")
            if getattr(image, "n_frames", 1) != 1:
                raise _ev(InputErrorCode.INVALID_IMAGE, "$", "multi-frame images are not supported")
            mode = image.mode
            converted: Image.Image
            if mode == "RGB":
                converted = image
                conversion = ColorConversion.NONE
            elif mode == "RGBA":
                background = Image.new("RGBA", image.size, (255, 255, 255, 255))
                converted = Image.alpha_composite(background, image).convert("RGB")
                conversion = ColorConversion.RGBA_ON_WHITE
            elif mode == "L":
                converted = image.convert("RGB")
                conversion = ColorConversion.GRAYSCALE_TO_RGB
            elif mode == "LA":
                background = Image.new("RGBA", image.size, (255, 255, 255, 255))
                converted = Image.alpha_composite(background, image.convert("RGBA")).convert("RGB")
                conversion = ColorConversion.RGBA_ON_WHITE
            else:
                raise _ev(
                    InputErrorCode.INVALID_IMAGE, "$", "unsupported image mode; use RGB, RGBA or grayscale"
                )
            converted.load()
            rgb = converted.tobytes()
            size = converted.size
    except EvidenceValidationError:
        raise
    except Image.DecompressionBombWarning:
        raise _ev(InputErrorCode.LIMIT_EXCEEDED, "$", "image exceeds the pixel safety limit") from None
    except Image.DecompressionBombError:
        raise _ev(InputErrorCode.LIMIT_EXCEEDED, "$", "image exceeds the pixel safety limit") from None
    except Exception:  # noqa: BLE001 - Pillow decode failures span several stdlib types;
        # converted to a coded error below, never swallowed
        raise _ev(InputErrorCode.INVALID_IMAGE, "$", "image decoding failed") from None
    return rgb, size[0], size[1], conversion


# ---------------------------------------------------------------------------
# evidence factories (attached to Evidence in schemas.py)
# ---------------------------------------------------------------------------


def build_screenshot(
    *,
    id: str,
    artifact_id: str,
    data: bytes | bytearray | memoryview,
    sequence: int,
    captured_at: Any,
    checkpoint_id: str,
    source_id: str,
    subject: Mapping[str, str],
    phase: Any,
) -> ScreenshotEvidence:
    payload = bytes(data)
    media_type, width, height = _inspect_image(payload)
    return ScreenshotEvidence.model_validate(
        {
            "id": id,
            "kind": "screenshot",
            "sequence": sequence,
            "captured_at": captured_at,
            "checkpoint_id": checkpoint_id,
            "source_id": source_id,
            "subject": subject,
            "phase": phase,
            "sha256": _digest(payload),
            "artifact_id": artifact_id,
            "media_type": media_type,
            "width": width,
            "height": height,
        }
    )


def build_observation(
    *,
    id: str,
    sequence: int,
    captured_at: Any,
    checkpoint_id: str,
    source_id: str,
    subject: Mapping[str, str],
    phase: Any,
    channel: Any,
    data: Mapping[str, object],
) -> ObservationEvidence:
    return ObservationEvidence.model_validate(
        {
            "id": id,
            "kind": "observation",
            "sequence": sequence,
            "captured_at": captured_at,
            "checkpoint_id": checkpoint_id,
            "source_id": source_id,
            "subject": subject,
            "phase": phase,
            "sha256": _payload_digest(data, "data"),
            "channel": channel,
            "data": data,
        }
    )


def build_action(
    *,
    id: str,
    sequence: int,
    captured_at: Any,
    checkpoint_id: str,
    source_id: str,
    subject: Mapping[str, str],
    phase: Any,
    name: str,
    arguments: Mapping[str, object],
    reported_status: Any,
    tool_result_id: str | None = None,
) -> ActionEvidence:
    payload = {
        "name": name,
        "arguments": arguments,
        "reported_status": reported_status,
        "tool_result_id": tool_result_id,
    }
    return ActionEvidence.model_validate(
        {
            "id": id,
            "kind": "action",
            "sequence": sequence,
            "captured_at": captured_at,
            "checkpoint_id": checkpoint_id,
            "source_id": source_id,
            "subject": subject,
            "phase": phase,
            "sha256": _payload_digest(payload, "arguments"),
            "name": name,
            "arguments": arguments,
            "reported_status": reported_status,
            "tool_result_id": tool_result_id,
        }
    )


# ---------------------------------------------------------------------------
# prepared evidence
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PreparedImage:
    """Decoded image for one evidence event (document 04); no file path."""

    evidence_id: str
    sequence: int
    width: int
    height: int
    rgb: bytes
    source_digest: str
    color_conversion: ColorConversion

    def __repr__(self) -> str:
        return (
            f"PreparedImage(evidence_id={self.evidence_id!r}, sequence={self.sequence}, "
            f"width={self.width}, height={self.height}, rgb={len(self.rgb)} bytes)"
        )


@dataclass(frozen=True)
class PreparedEvidence:
    """Validated, decoded evidence for one request; images keyed by evidence ID."""

    images: Mapping[str, PreparedImage]

    def __repr__(self) -> str:
        return f"PreparedEvidence(images={sorted(self.images)})"


def prepare_evidence(request: VerificationRequest, store: ArtifactStore) -> PreparedEvidence:
    """Validate artifacts and evidence, decode images once per distinct digest.

    Raises :class:`EvidenceValidationError` with a safe code and field path:
    total/per-image byte ceilings and header pixel limits (LIMIT_EXCEEDED),
    corrupt artifacts including unused ones (INVALID_IMAGE), missing artifact
    references (MISSING_ARTIFACT), digest mismatches (HASH_MISMATCH) and
    false declarations (INVALID_IMAGE). Source bytes are never modified.
    """
    total = sum(len(data) for data in store.values())
    if total > MAX_TOTAL_IMAGE_BYTES:
        raise _ev(InputErrorCode.LIMIT_EXCEEDED, "$.artifacts", "total image bytes exceed the limit")
    decoded: dict[str, tuple[bytes, int, int, ColorConversion]] = {}
    headers: dict[str, tuple[str, int, int, str]] = {}
    for artifact_id in store:
        data = store[artifact_id]
        path = f"$.artifacts[{artifact_id}]"
        try:
            media_type, width, height = _inspect_image(data)
            digest = _digest(data)
            headers[artifact_id] = (media_type, width, height, digest)
            if digest not in decoded:
                rgb, decoded_width, decoded_height, conversion = _decode_artifact(data)
                if (decoded_width, decoded_height) != (width, height):
                    raise _ev(
                        InputErrorCode.INVALID_IMAGE, path, "decoded dimensions do not match the header"
                    )
                if len(rgb) != decoded_width * decoded_height * 3:
                    raise _ev(
                        InputErrorCode.INVALID_IMAGE, path, "decoded pixel buffer has an unexpected size"
                    )
                decoded[digest] = (rgb, decoded_width, decoded_height, conversion)
        except EvidenceValidationError as error:
            raise _ev(error.issue.code, path, error.issue.safe_message) from None
    images: dict[str, PreparedImage] = {}
    for index, item in enumerate(request.evidence):
        path = f"$.evidence[{index}]"
        if isinstance(item, ScreenshotEvidence):
            if item.artifact_id not in store:
                raise _ev(
                    InputErrorCode.MISSING_ARTIFACT, f"{path}.artifact_id", "artifact is not in the store"
                )
            media_type, width, height, digest = headers[item.artifact_id]
            if item.sha256 != digest:
                raise _ev(InputErrorCode.HASH_MISMATCH, f"{path}.sha256", "artifact digest does not match")
            if item.media_type != media_type:
                raise _ev(
                    InputErrorCode.INVALID_IMAGE, f"{path}.media_type", "declared media type does not match"
                )
            if item.width != width:
                raise _ev(InputErrorCode.INVALID_IMAGE, f"{path}.width", "declared width does not match")
            if item.height != height:
                raise _ev(InputErrorCode.INVALID_IMAGE, f"{path}.height", "declared height does not match")
            rgb, _, _, conversion = decoded[digest]
            images[item.id] = PreparedImage(
                evidence_id=item.id,
                sequence=item.sequence,
                width=width,
                height=height,
                rgb=rgb,
                source_digest=digest,
                color_conversion=conversion,
            )
        elif isinstance(item, ObservationEvidence):
            actual = _payload_digest(item.data, f"{path}.data")
            if item.sha256 != actual:
                raise _ev(InputErrorCode.HASH_MISMATCH, f"{path}.sha256", "payload digest does not match")
        elif isinstance(item, ActionEvidence):
            payload = {
                "name": item.name,
                "arguments": item.arguments,
                "reported_status": item.reported_status,
                "tool_result_id": item.tool_result_id,
            }
            actual = _payload_digest(payload, f"{path}.arguments")
            if item.sha256 != actual:
                raise _ev(InputErrorCode.HASH_MISMATCH, f"{path}.sha256", "payload digest does not match")
    return PreparedEvidence(images=MappingProxyType(images))


# ---------------------------------------------------------------------------
# evidence reference validation
# ---------------------------------------------------------------------------


def validate_evidence_ref(
    ref: EvidenceRef,
    evidence_by_id: Mapping[str, Any],
    images: Mapping[str, PreparedImage],
) -> None:
    """Validate one EvidenceRef against prepared evidence (document 03).

    bbox is only valid on screenshots and must lie within the decoded
    dimensions (half-open); pointer is only valid on observation/action
    evidence. Schema-level checks already enforce the internal bbox ordering.
    """
    item = evidence_by_id.get(ref.evidence_id)
    if item is None:
        raise _ev(
            InputErrorCode.UNKNOWN_REFERENCE, "$.evidence_refs", "referenced evidence id is not declared"
        )
    if isinstance(item, ScreenshotEvidence):
        if ref.pointer is not None:
            raise _ev(
                InputErrorCode.INVALID_POINTER, "$.evidence_refs", "pointers are not allowed on screenshots"
            )
        if ref.bbox is not None:
            image = images.get(ref.evidence_id)
            if image is None:
                raise _ev(
                    InputErrorCode.UNKNOWN_REFERENCE,
                    "$.evidence_refs",
                    "referenced evidence was not prepared",
                )
            _, _, x1, y1 = ref.bbox
            if x1 > image.width or y1 > image.height:
                raise _ev(
                    InputErrorCode.INVALID_IMAGE, "$.evidence_refs", "bbox exceeds the image dimensions"
                )
    elif ref.bbox is not None:
        raise _ev(
            InputErrorCode.INVALID_IMAGE, "$.evidence_refs", "bounding boxes are only allowed on screenshots"
        )
