"""Shared in-memory image fixtures for evidence/security tests (not collected).

All images are generated deterministically with Pillow; no binary files are
committed. PNG byte-length padding uses tEXt chunks and JPEG padding uses
comment segments, both valid per their format specifications.
"""

from __future__ import annotations

import io
import struct
import zlib
from typing import Any

from PIL import Image


def png_bytes(
    width: int,
    height: int,
    mode: str = "RGB",
    color: Any = (255, 0, 0),
) -> bytes:
    buffer = io.BytesIO()
    Image.new(mode, (width, height), color).save(buffer, format="PNG")
    return buffer.getvalue()


def jpeg_bytes(width: int, height: int, color: Any = (0, 128, 255), quality: int = 80) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), color).save(buffer, format="JPEG", quality=quality)
    return buffer.getvalue()


def rgba_png(width: int, height: int, color: Any) -> bytes:
    return png_bytes(width, height, "RGBA", color)


def grayscale_png(width: int, height: int, value: int = 77) -> bytes:
    return png_bytes(width, height, "L", value)


def palette_png(width: int, height: int, color: Any = (255, 0, 0)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), color).convert("P").save(buffer, format="PNG")
    return buffer.getvalue()


def cmyk_jpeg(width: int, height: int) -> bytes:
    buffer = io.BytesIO()
    Image.new("CMYK", (width, height), (0, 128, 128, 5)).save(buffer, format="JPEG")
    return buffer.getvalue()


def apng_bytes(width: int = 2, height: int = 2) -> bytes:
    first = Image.new("RGB", (width, height), (255, 0, 0))
    second = Image.new("RGB", (width, height), (0, 0, 255))
    buffer = io.BytesIO()
    first.save(buffer, format="PNG", save_all=True, append_images=[second], duration=100, loop=0)
    return buffer.getvalue()


def gif_bytes(width: int = 2, height: int = 2) -> bytes:
    buffer = io.BytesIO()
    Image.new("P", (width, height), (255, 0, 0)).save(buffer, format="GIF")
    return buffer.getvalue()


def jpeg_with_orientation(width: int, height: int, orientation: int) -> bytes:
    exif = Image.Exif()
    exif[274] = orientation
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), (10, 200, 30)).save(buffer, format="JPEG", exif=exif)
    return buffer.getvalue()


def patch_png_dims(data: bytes, width: int, height: int) -> bytes:
    """Craft an IHDR with the given dimensions (CRC left stale on purpose).

    Header-level checks must reject over-limit dimensions before any decode,
    so a stale CRC is acceptable for these negative fixtures.
    """
    return data[:16] + struct.pack(">II", width, height) + data[24:]


def _png_chunk(chunk_type: bytes, payload: bytes) -> bytes:
    return (
        struct.pack(">I", len(payload))
        + chunk_type
        + payload
        + struct.pack(">I", zlib.crc32(chunk_type + payload) & 0xFFFFFFFF)
    )


def pad_png_to_size(data: bytes, total_size: int) -> bytes:
    """Extend a PNG to exactly ``total_size`` bytes with a tEXt chunk before IEND."""
    assert data.endswith(b"IEND\xaeB`\x82"), "expected a PNG ending in IEND"
    body = data[:-12]
    iend = data[-12:]
    added = total_size - len(data)
    assert added >= 15, "target size must exceed the original"
    text_len = added - 12 - 2  # chunk overhead plus 'f\\0' keyword prefix
    return body + _png_chunk(b"tEXt", b"f\x00" + b"x" * text_len) + iend


def pad_jpeg_to_size(data: bytes, total_size: int) -> bytes:
    """Extend a JPEG to exactly ``total_size`` bytes with comment segments."""
    remaining = total_size - len(data)
    assert remaining >= 4, "target size must exceed the original"
    chunks: list[bytes] = []
    while remaining > 0:
        segment = min(remaining - 4, 65_529)
        chunks.append(b"\xff\xfe" + struct.pack(">H", segment + 2) + b"x" * segment)
        remaining -= 4 + segment
    return data + b"".join(chunks)


def pixel_of(rgb: bytes, width: int, x: int, y: int) -> tuple[int, int, int]:
    offset = (y * width + x) * 3
    return (rgb[offset], rgb[offset + 1], rgb[offset + 2])
