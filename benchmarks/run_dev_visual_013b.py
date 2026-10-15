"""NIT-013 part B driver: dev-visual.json via SmolVLM2-2.2B (clearly labeled).

TEMPORARY DRIVER — replaced by `--backend smolvlm --model-dir` once the NIT-012
smolvlm CLI wiring merges (review finding 1). Until then this script runs the
dev visual manifest through the SAME evaluate() pipeline the CLI uses, with a
factory that constructs one shared SmolVLMBackend over the pinned, manifest-
verified checkpoint (lazy single load; the model is NOT reloaded per case).
Report shapes are the runner's own, so the RUN-01/02 validator applies as-is.

Usage (WSL, nothing else heavy running):
  NITELOS_MODEL_DIR=~/nitelos-models/SmolVLM2-2.2B-Instruct@482adb5 \
  uv run python benchmarks/run_dev_visual_013b.py \
      --manifest benchmarks/synthetic_v1/dev-visual.json \
      --artifacts benchmarks/synthetic_v1 \
      --output reports/dev-split/dev-visual-smolvlm
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from nitelos import Verifier
from nitelos.backends.smolvlm import SmolVLMBackend
from nitelos.evaluation.runner import evaluate, load_evaluation_manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--artifacts", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)

    model_dir = os.environ.get("NITELOS_MODEL_DIR")
    if not model_dir:
        print("error: NITELOS_MODEL_DIR must point at the pinned model directory", file=sys.stderr)
        return 2
    manifest = load_evaluation_manifest(Path(args.manifest), Path(args.artifacts))
    backend = SmolVLMBackend(Path(model_dir))  # lazy load on first infer; one instance

    def factory(case_id: str, request: object, artifacts: object, bindings: object) -> Verifier:
        del case_id  # one shared sequential verifier; the runner invokes it per case
        return Verifier(backend=backend, policy=manifest.policy, trust_bindings=bindings)

    summary = evaluate(manifest, factory, Path(args.output))
    backend.close()
    print(
        f"run complete: {summary.scheduled} scheduled, {summary.ok_count} ok, "
        f"{summary.error_count} errors -> {summary.output_dir}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
