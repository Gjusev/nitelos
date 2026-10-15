"""NIT-008 D3 final pure diagnostic: caption + QA on the dev smoke-01 image.

NOT a prompt candidate (the iteration list is closed and the gate decision
stands); this exists only to make the G3 escalation report precise. Standalone
script, NOT the verifier path: direct processor/model calls, greedy, no
sampling, max_new_tokens 40 (the 8-token cap is the criterion protocol, not a
library limit), decode only new tokens. Two prompts, verbatim raw output.
"""

from __future__ import annotations

import json
import os
import platform
from pathlib import Path

BENCH = Path(__file__).resolve().parent
REPO = BENCH.parent
SMOKE = REPO / "tests" / "fixtures" / "smoke"
OUT = Path(os.environ.get("SMOKE_OUT", BENCH / "d3-diagnostic"))
IMAGE = SMOKE / "smoke-01.png"
MAX_NEW_TOKENS = 40

D3_PROMPTS = {
    "D3_caption": "Describe this image briefly.",
    "D3_qa": "What is shown in the image? Answer in one sentence.",
}


def main() -> int:
    import hashlib

    from nitelos.backends.smolvlm import _load_model, _load_processor, _import_torch, _import_transformers

    model_dir = Path(os.environ["NITELOS_MODEL_DIR"])
    torch = _import_torch()
    transformers = _import_transformers()
    processor = _load_processor(model_dir, transformers)
    model = _load_model(model_dir, transformers, torch, "float32")

    from PIL import Image

    image = Image.open(IMAGE).convert("RGB")
    results: dict[str, str] = {}
    for name, prompt in D3_PROMPTS.items():
        chat_text = processor.apply_chat_template(
            [{"role": "user", "content": [{"type": "image"}, {"type": "text", "text": prompt}]}],
            add_generation_prompt=True,
        )
        inputs = processor(text=chat_text, images=[image], return_tensors="pt", size={"longest_edge": 1024})
        model.eval()
        with torch.inference_mode():
            outputs = model.generate(**inputs, max_new_tokens=MAX_NEW_TOKENS)
        sequences = getattr(outputs, "sequences", outputs)
        new_tokens = sequences[:, inputs["input_ids"].shape[-1] :]
        results[name] = processor.batch_decode(new_tokens, skip_special_tokens=True)[0]
        print(name, "->", repr(results[name]))

    report = {
        "run": "NIT-008 D3 final pure diagnostic (post-decision; escalation evidence only)",
        "settings": {
            "greedy": True,
            "sampling_params": None,
            "max_new_tokens": MAX_NEW_TOKENS,
            "decode": "new tokens only, skip_special_tokens=True",
            "image": IMAGE.name,
            "image_sha256": hashlib.sha256(IMAGE.read_bytes()).hexdigest(),
        },
        "outputs": results,
        "platform": {"os": platform.system(), "python": platform.python_version()},
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "d3-diagnostic.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print("written:", OUT / "d3-diagnostic.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
