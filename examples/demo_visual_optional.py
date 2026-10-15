"""Optional visual demo: requires a pre-provisioned local model (doc 11 case 3).

Ordinary tests NEVER run this: it is gated on NITELOS_RUN_LOCAL=1 and
NITELOS_MODEL_DIR pointing at the pinned checkpoint directory (see the
installation guide). The result is always labeled model_inferred with the
VISUAL_GROUNDING_UNVERIFIED limitation — visual inference is experimental
and cannot prove external state.

Windows is unsupported for the local extra (design A4). The development
smoke record (12 cases) shows the model is format-compliant but
over-claiming; no accuracy claim is made here.
"""

from __future__ import annotations

import os
import sys


def run() -> int:
    if os.environ.get("NITELOS_RUN_LOCAL") != "1":
        print("skipped: set NITELOS_RUN_LOCAL=1 and NITELOS_MODEL_DIR to run the visual demo")
        return 0
    model_dir = os.environ.get("NITELOS_MODEL_DIR")
    if not model_dir:
        print("error: NITELOS_MODEL_DIR must point at the pinned model directory")
        return 1
    try:
        from nitelos.backends.smolvlm import (  # noqa: PLC0415 - optional local-extra module
            DEFAULT_REVISION,
            SmolVLMBackend,
        )
    except ImportError:
        print(
            "error: the smolvlm backend is not available in this installation "
            "(install the 'local' extra: uv sync --extra local); no model run is faked"
        )
        return 1
    if sys.platform == "win32":
        print("note: Windows is unvalidated for the local extra (Linux CPU is the validated path)")

    import hashlib  # noqa: PLC0415 - demo-only, imported after the gates
    import io  # noqa: PLC0415 - demo-only, after the gates

    from PIL import Image  # noqa: PLC0415 - optional dep, after the gates

    from nitelos import (  # noqa: PLC0415 - after the gates
        VerificationPolicy,
        Verifier,
        parse_trace,
    )

    # A minimal synthetic visual trace: one screenshot, one visual criterion.
    buffer = io.BytesIO()
    Image.new("RGB", (64, 32), (30, 140, 60)).save(buffer, format="PNG")
    png = buffer.getvalue()
    sha = hashlib.sha256(png).hexdigest()
    trace = parse_trace(
        {
            "schema_version": "1",
            "evidence": [
                {
                    "id": "shot-demo",
                    "kind": "screenshot",
                    "sequence": 0,
                    "captured_at": "2026-10-20T10:00:00Z",
                    "checkpoint_id": "cp-demo",
                    "source_id": "demo-runner",
                    "subject": {"demo": "visual-1"},
                    "phase": "final",
                    "sha256": sha,
                    "artifact_id": "art-demo",
                    "media_type": "image/png",
                    "width": 64,
                    "height": 32,
                }
            ],
        }
    )
    request = trace.to_request(
        objective="Demo: judge one visual criterion with the local model",
        criteria=[
            {
                "id": "appearance",
                "description": "The screenshot is predominantly green",
                "kind": "visual",
                "scope": "visual",
                "evidence_ids": ["shot-demo"],
                "subject": {"demo": "visual-1"},
            }
        ],
        request_id="demo-visual-1",
        checkpoint_id="cp-demo",
        as_of="2026-10-20T10:01:00Z",
    )
    backend = SmolVLMBackend(model_dir, DEFAULT_REVISION, device="cpu", dtype="float32")
    verifier = Verifier(
        backend=backend,
        policy=VerificationPolicy(allow_model_inference=True),
    )
    try:
        result = verifier.verify(request, artifacts={"art-demo": png})
    finally:
        verifier.close()
    print(f"execution_status: {result.execution_status.value}")
    print(f"decision:         {result.decision.value if result.decision else None}")
    for criterion in result.criteria:
        print(f"criterion {criterion.criterion_id}: {criterion.state.value} (basis: {criterion.basis.value})")
        for limitation in criterion.limitations:
            print(f"  limitation: {limitation.value}")
    print("note: model_inferred results are experimental and never prove external state")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
