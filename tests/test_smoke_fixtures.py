"""SMK: the 12-case development smoke set fixtures (NIT-008, doc 04 "Executability gate").

The smoke set exists for interface/hardware testing only: it is not an accuracy benchmark and
never enters the final-test split (docs/planning/06). These tests pin the fixture artifacts
themselves: doc-04 case order, per-file digests, renderer-scoped byte-identical regeneration
(doc 06 DATA-04: deterministic generator hashes for the declared renderer platform), hard
image limits, single-frame metadata-free PNGs, and label-neutral filenames. Committed files
and their digests are the source of truth on every platform; only byte-regeneration is
scoped to the declared renderer.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import platform
import re
from pathlib import Path
from typing import Any

import PIL
import pytest
from PIL import Image, features

SMOKE_DIR = Path(__file__).resolve().parent / "fixtures" / "smoke"
GENERATOR = SMOKE_DIR / "generate_smoke.py"
CASES_JSON = SMOKE_DIR / "cases.json"
README = SMOKE_DIR / "README.md"

ALLOWED_LABELS = {"SUPPORTED", "REFUTED", "UNKNOWN"}
LABEL_WORDS = (
    "supported",
    "refuted",
    "unknown",
    "success",
    "succeed",
    "successful",
    "fail",
    "failed",
    "failure",
    "pending",
    "abstain",
    "abstained",
    "expected",
    "label",
)
MAX_PIXELS = 4_194_304
MAX_SIDE = 4096
MAX_BYTES = 8 * 1024 * 1024
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
# Renderer facts that must match the README declaration before byte-identity is asserted.
_RENDERER_KEYS = ("os", "python", "pillow", "freetype", "zlib")
# Chunks that would carry text metadata, EXIF, or extra animation frames (doc 03 limits).
FORBIDDEN_CHUNKS = {"tEXt", "zTXt", "iTXt", "eXIf", "acTL", "fcTL", "fdAT"}
# Doc-04 "Executability gate" slots in order; each case table row must mention its keyword.
DOC04_KEYWORDS = (
    "completion banner",
    "rejection banner",
    "required field",
    "confirmation",
    "spinner",
    "conflicting",
    "wrong-id",
    "tiny",
    "injected",
    "misleading",
    "before/after",
    "blank",
)


def _cases() -> list[dict[str, Any]]:
    data = json.loads(CASES_JSON.read_text(encoding="utf-8"))
    cases = data["cases"]
    assert isinstance(cases, list)
    return cases


def _pngs() -> list[Path]:
    return sorted(SMOKE_DIR.glob("smoke-*.png"))


def _recorded_digests() -> dict[str, str]:
    rows = re.findall(
        r"\|\s*(smoke-[0-9]+[ab]?\.png)\s*\|\s*([0-9a-f]{64})\s*\|",
        README.read_text(encoding="utf-8"),
    )
    return dict(rows)


def _declared_renderer() -> dict[str, str]:
    """Renderer environment recorded in the README data card (doc 06 DATA-04 contract)."""
    text = README.read_text(encoding="utf-8")
    section = re.search(r"## Declared renderer platform.*?(?=\n## |\Z)", text, re.DOTALL)
    assert section is not None, "README must declare the renderer platform"
    rows = re.findall(r"^\|\s*([a-z]+)\s*\|\s*([^|\n]+?)\s*\|\s*$", section.group(0), re.MULTILINE)
    declared = dict(rows)
    for key in _RENDERER_KEYS:
        assert key in declared, key
    return declared


def _running_renderer() -> dict[str, str]:
    return {
        "os": platform.system(),
        "python": ".".join(platform.python_version_tuple()[:2]),
        "pillow": PIL.__version__,
        "freetype": features.version("freetype2") or "unavailable",
        "zlib": features.version("zlib") or "unavailable",
    }


def _png_chunks(path: Path) -> list[str]:
    data = path.read_bytes()
    assert data.startswith(PNG_SIGNATURE), path.name
    chunks: list[str] = []
    offset = len(PNG_SIGNATURE)
    while offset < len(data):
        length = int.from_bytes(data[offset : offset + 4], "big")
        chunks.append(data[offset + 4 : offset + 8].decode("ascii"))
        offset += 12 + length  # 4 length + 4 type + payload + 4 CRC
    return chunks


def test_case_table_follows_doc04_gate_order() -> None:
    cases = _cases()
    assert len(cases) == 12
    assert [case["doc04_index"] for case in cases] == list(range(1, 13))
    assert len({case["case_id"] for case in cases}) == 12
    for case, keyword in zip(cases, DOC04_KEYWORDS, strict=True):
        assert case["expected_label"] in ALLOWED_LABELS, case["case_id"]
        assert case["phase"] in {"final", "pending"}, case["case_id"]
        assert 0 < len(case["criterion"]) <= 1024, case["case_id"]
        assert 0 < len(case["objective"]) <= 4096, case["case_id"]
        assert case["rationale"].strip(), case["case_id"]
        assert isinstance(case["images"], list)
        assert case["images"], case["case_id"]
        assert all(isinstance(n, str) and n.endswith(".png") for n in case["images"])
        haystack = f"{case['criterion']} {case['rationale']}".lower()
        assert keyword in haystack, (case["case_id"], keyword)


def test_case_images_exist_with_recorded_digests() -> None:
    recorded = _recorded_digests()
    referenced = {name for case in _cases() for name in case["images"]}
    on_disk = {path.name for path in _pngs()}
    assert referenced == on_disk == set(recorded)
    for path in _pngs():
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        assert digest == recorded[path.name], path.name


def test_regeneration_is_byte_identical_on_declared_renderer(tmp_path: Path) -> None:
    declared = _declared_renderer()
    running = _running_renderer()
    mismatches = [
        f"{key}: running {running[key]!r}, declared {declared[key]!r}"
        for key in _RENDERER_KEYS
        if running[key] != declared[key]
    ]
    if mismatches:
        pytest.skip(
            "byte-identity is declared only for the recorded renderer platform "
            f"(doc 06 DATA-04): {'; '.join(mismatches)}"
        )
    spec = importlib.util.spec_from_file_location("generate_smoke", GENERATOR)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.render_all(tmp_path)
    regenerated = {p.name for p in tmp_path.glob("smoke-*.png")}
    assert regenerated == {p.name for p in _pngs()}
    for path in _pngs():
        assert (tmp_path / path.name).read_bytes() == path.read_bytes(), path.name


def test_images_respect_limits_and_carry_no_metadata() -> None:
    pngs = _pngs()
    assert len(pngs) == 14, "12 cases plus a second image for slots 6 and 11"
    for path in pngs:
        assert path.stat().st_size < MAX_BYTES, path.name
        assert not (FORBIDDEN_CHUNKS & set(_png_chunks(path))), path.name
        with Image.open(path) as img:
            img.load()
            assert img.format == "PNG", path.name
            assert img.mode == "RGB", path.name
            assert img.n_frames == 1, path.name
            width, height = img.size
            assert width <= MAX_SIDE, path.name
            assert height <= MAX_SIDE, path.name
            assert width * height <= MAX_PIXELS, path.name
            assert not img.getexif(), path.name
            assert not img.text, path.name


def test_filenames_are_label_neutral() -> None:
    pngs = _pngs()
    assert len(pngs) == 14
    for path in pngs:
        lowered = path.name.lower()
        assert not [word for word in LABEL_WORDS if word in lowered], path.name


def test_multi_image_cases_match_doc04() -> None:
    counts = {case["doc04_index"]: len(case["images"]) for case in _cases()}
    assert counts[6] == 2, "doc-04 slot 6 uses two final screenshots"
    assert counts[11] == 2, "doc-04 slot 11 uses a before/after pair"
    assert all(n == 1 for i, n in counts.items() if i not in {6, 11})
    assert all(n <= 2 for n in counts.values()), "built-in adapter takes at most 2 images"


def test_phase_and_action_context_contract() -> None:
    cases = {case["doc04_index"]: case for case in _cases()}
    assert cases[5]["phase"] == "pending", "doc-04 slot 5 is the pending-phase case"
    assert all(case["phase"] == "final" for i, case in cases.items() if i != 5)
    for index, case in cases.items():
        items = case["action_context"]
        if index == 10:
            assert len(items) >= 1, "doc-04 slot 10 carries the misleading action context"
            for item in items:
                assert set(item) == {"name", "reported_status"}, item
                assert item["reported_status"] in {"completed", "failed", "unknown"}, item
        else:
            assert items == [], (index, items)


def test_doc04_slot12_image_is_blank() -> None:
    case12 = next(case for case in _cases() if case["doc04_index"] == 12)
    path = SMOKE_DIR / case12["images"][0]
    with Image.open(path) as img:
        extrema = img.getextrema()
    assert all(low == high for low, high in extrema), extrema
