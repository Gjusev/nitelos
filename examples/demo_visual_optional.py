"""Optional visual demo: requires a pre-provisioned local model (doc 11 case 3).

Ordinary tests NEVER run this: it is gated on NITELOS_RUN_LOCAL=1 and
NITELOS_MODEL_DIR pointing at the pinned checkpoint directory (see the
installation guide). The result is always labeled model_inferred with the
VISUAL_GROUNDING_UNVERIFIED limitation — visual inference is experimental
and cannot prove external state. The adapter ships with NIT-008; until it
lands this script exits with a documented error rather than mocking success.
"""

from __future__ import annotations

import os


def run() -> int:
    if os.environ.get("NITELOS_RUN_LOCAL") != "1":
        print("skipped: set NITELOS_RUN_LOCAL=1 and NITELOS_MODEL_DIR to run the visual demo")
        return 0
    model_dir = os.environ.get("NITELOS_MODEL_DIR")
    if not model_dir:
        print("error: NITELOS_MODEL_DIR must point at the pinned model directory")
        return 1
    try:
        from nitelos.backends.smolvlm import (  # noqa: PLC0415 - optional NIT-008 probe
            SmolVLMBackend,
        )

        del SmolVLMBackend  # availability probe only
    except ImportError:
        print(
            "error: the smolvlm backend is not available in this installation "
            "(arrives with NIT-008 and the 'local' extra); no model run is faked"
        )
        return 1
    # Full wiring lands with NIT-008: build PreparedVisualCriterion images from the
    # caller's screenshot, construct SmolVLMBackend(model_dir, revision), verify with
    # VerificationPolicy(allow_model_inference=True), and print the model_inferred
    # basis with its VISUAL_GROUNDING_UNVERIFIED limitation.
    print("error: the visual demo wiring arrives with NIT-008; nothing was faked")
    return 1


if __name__ == "__main__":
    raise SystemExit(run())
