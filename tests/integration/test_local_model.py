"""Gated real-local-model integration test (NIT-008; marker ``local_model``).

Requires NITELOS_RUN_LOCAL=1 AND NITELOS_MODEL_DIR (a directory holding the
verified pinned weights plus nitelos-manifest.json). Otherwise skips with a
precise reason. Never downloads: loading is local-files-only (the adapter's
offline discipline is asserted by the mocked contract tests); this test proves
the real processor/model pair works through the adapter and produces a
parsable label path. Linux CPU py3.12 is the declared platform (doc 12);
Windows results are labeled unvalidated (design A4).
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from nitelos.backends.base import InferenceContext, PreparedVisualCriterion
from nitelos.backends.smolvlm import (
    DEFAULT_REVISION,
    PROMPT_HASH_V1,
    REQUIRED_MANIFEST_FILES,
    SmolVLMBackend,
)
from nitelos.evidence import PreparedImage
from nitelos.schemas import BackendFinding, CriterionState

pytestmark = pytest.mark.local_model


def _model_dir() -> Path:
    raw = os.environ.get("NITELOS_MODEL_DIR", "")
    return Path(raw)


def _gate() -> None:
    if os.environ.get("NITELOS_RUN_LOCAL") != "1":
        pytest.skip("NITELOS_RUN_LOCAL=1 not set; real local model inference is opt-in")
    model_dir = _model_dir()
    if not model_dir.is_dir():
        pytest.skip(f"NITELOS_MODEL_DIR does not point at a directory: {model_dir!s}")
    manifest = model_dir / "nitelos-manifest.json"
    if not manifest.is_file():
        pytest.skip("model directory lacks nitelos-manifest.json (author it from the verified sidecar)")
    missing = [name for name in REQUIRED_MANIFEST_FILES if not (model_dir / name).is_file()]
    if missing:
        pytest.skip(f"model directory is missing pinned files: {missing}")


def _tiny_image(evidence_id: str = "img-local", width: int = 64, height: int = 48) -> PreparedImage:
    from PIL import Image

    buffer = Image.new("RGB", (width, height), (30, 144, 255))
    return PreparedImage(
        evidence_id=evidence_id,
        sequence=0,
        width=width,
        height=height,
        rgb=buffer.tobytes(),
        source_digest="0" * 64,
        color_conversion="none",
    )


def test_real_local_model_produces_a_valid_label_path() -> None:
    _gate()
    backend = SmolVLMBackend(_model_dir(), DEFAULT_REVISION)
    prepared = PreparedVisualCriterion(
        criterion_id="c-local",
        description="The image is a solid blue rectangle.",
        images=(_tiny_image(),),
    )
    finding = backend.infer(prepared, InferenceContext(objective="Local integration check"))
    assert isinstance(finding, BackendFinding)
    assert finding.criterion_id == "c-local"
    assert finding.state in (CriterionState.SUPPORTED, CriterionState.REFUTED, CriterionState.UNKNOWN)
    assert backend.descriptor.prompt_hash == PROMPT_HASH_V1
    assert backend.descriptor.runtime_lock_hash is not None
    assert backend.model_load_ms is not None
    assert backend.model_load_ms >= 0.0
    (record,) = backend.last_preprocessing
    assert record.processor_longest_edge == 1024
    backend.close()
    from nitelos.backends.base import BackendOutputError

    with pytest.raises(BackendOutputError, match="CLOSED"):
        backend.infer(prepared, InferenceContext(objective="after close"))
