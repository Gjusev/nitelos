"""NIT-008 phase B: D3-style sanity caption on smoke-01 with the ADR-012 2.2B
checkpoint, BEFORE the smoke run (same settings as D3: greedy, no sampling,
max_new_tokens 40, decode-new-only, standalone script)."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from d3_diagnostic_008 import D3_PROMPTS, IMAGE, MAX_NEW_TOKENS  # noqa: E402
from nitelos.backends.smolvlm import (  # noqa: E402
    _load_model,
    _load_processor,
    _import_torch,
    _import_transformers,
)
from PIL import Image  # noqa: E402


def main() -> int:
    model_dir = Path(os.environ["NITELOS_MODEL_DIR"])
    torch = _import_torch()
    transformers = _import_transformers()
    processor = _load_processor(model_dir, transformers)
    model = _load_model(model_dir, transformers, torch, "float32")
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
        results[name] = processor.batch_decode(
            sequences[:, inputs["input_ids"].shape[-1] :], skip_special_tokens=True
        )[0]
        print(name, "->", repr(results[name]))
    report = {
        "run": "D3-style sanity caption, ADR-012 SmolVLM2-2.2B checkpoint, BEFORE smoke",
        "settings": {
            "greedy": True,
            "sampling_params": None,
            "max_new_tokens": MAX_NEW_TOKENS,
            "image": IMAGE.name,
            "image_sha256": hashlib.sha256(IMAGE.read_bytes()).hexdigest(),
        },
        "outputs": results,
        "platform": {"os": platform.system(), "python": platform.python_version()},
    }
    out = Path(__file__).resolve().parent / "d3-2.2B-sanity.json"
    out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print("written:", out.name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
