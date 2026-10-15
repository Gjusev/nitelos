"""NIT-008 approved iteration round: D1/D2 diagnostics, then full 11-case runs.

Ruling (decisions.md, NIT-008 G3 iteration ruling): one bounded round, dev smoke
images only, candidates v2 (instruction-last) and v3 (completion suffix) fixed
before any run, D1 (trivially-SUPPORTED) and D2 (trivially-REFUTED) diagnostics
on smoke-01 under each template first, then the better-looking template over
all 11 model cases (both if time permits — CPU cost ~1 min per 11 cases).
Parser, model, preprocessing, max_new_tokens and sampling are untouched.
"""

from __future__ import annotations

import json
import os
import platform
import resource
import time
from pathlib import Path
from typing import Any

from nitelos import Evidence, VerificationPolicy, Verifier, parse_request
from nitelos.backends.smolvlm import (
    PROMPT_HASH_V1,
    PROMPT_HASH_V2,
    PROMPT_HASH_V3,
    SmolVLMBackend,
)

BENCH = Path(__file__).resolve().parent
REPO = BENCH.parent
SMOKE = REPO / "tests" / "fixtures" / "smoke"
OUT = Path(os.environ.get("SMOKE_OUT", BENCH / "iteration-round"))
SUBJECT = {"form": "smoke"}
AS_OF = "2026-06-01T10:00:00Z"
CAPTURED = "2026-06-01T09:59:00Z"
VALID_LABELS = ("SUPPORTED", "REFUTED", "UNKNOWN")
PROMPT_HASHES = {"v1": PROMPT_HASH_V1, "v2": PROMPT_HASH_V2, "v3": PROMPT_HASH_V3}

D1_DESCRIPTION = "The screenshot contains any text at all."
D2_DESCRIPTION = "The screenshot shows a purple dinosaur."


def load_cases() -> list[dict[str, Any]]:
    return json.loads((SMOKE / "cases.json").read_text(encoding="utf-8"))["cases"]


def images_map() -> dict[str, bytes]:
    return {path.name: path.read_bytes() for path in SMOKE.glob("smoke-*.png")}


def build_request(
    case: dict[str, Any], images: dict[str, bytes], description: str | None = None
) -> dict[str, Any]:
    evidence: list[Any] = []
    next_sequence = 0
    for action in case.get("action_context", []):
        evidence.append(
            Evidence.action(
                id=f"act-{next_sequence}",
                sequence=next_sequence,
                captured_at=CAPTURED,
                checkpoint_id="cp-final",
                source_id="smoke-runner",
                subject=dict(SUBJECT),
                phase="final",
                name=action["name"],
                arguments={},
                reported_status=action["reported_status"],
            )
        )
        next_sequence += 1
    for index, image_name in enumerate(case["images"]):
        evidence.append(
            Evidence.screenshot(
                id=f"shot-{index}",
                artifact_id=image_name,
                data=images[image_name],
                sequence=next_sequence,
                captured_at=CAPTURED,
                checkpoint_id="cp-final",
                source_id="smoke-runner",
                subject=dict(SUBJECT),
                phase=case["phase"],
            )
        )
        next_sequence += 1
    criterion = {
        "id": "c-vis",
        "description": description if description is not None else case["criterion"],
        "kind": "visual",
        "scope": "visual",
        "evidence_ids": [f"shot-{i}" for i in range(len(case["images"]))],
        "subject": dict(SUBJECT),
    }
    return {
        "schema_version": "1",
        "request_id": f"smoke-{case['case_id']}",
        "objective": case["objective"],
        "checkpoint_id": "cp-final",
        "as_of": AS_OF,
        "criteria": [criterion],
        "evidence": [item.model_dump(mode="json") for item in evidence],
    }


def run_case(
    verifier: Verifier,
    backend: SmolVLMBackend,
    case: dict[str, Any],
    images: dict[str, bytes],
    description: str | None = None,
) -> dict[str, Any]:
    started = time.monotonic()
    result = verifier.verify(parse_request(build_request(case, images, description)), artifacts=images)
    elapsed_ms = (time.monotonic() - started) * 1000.0
    raw = backend.last_raw_output
    criterion = result.criteria[0] if result.criteria else None
    label = raw.strip() if raw is not None else None
    return {
        "case_id": case["case_id"],
        "status": result.execution_status.value,
        "decision": result.decision.value if result.decision else None,
        "error_code": result.error.code.value if result.error else None,
        "elapsed_ms": round(elapsed_ms, 2),
        "model_invoked": backend.infer_attempts > 0,
        "raw_output": raw,
        "parsed_label": label if label in VALID_LABELS else None,
        "basis": criterion.basis.value if criterion else None,
    }


def main() -> int:
    model_dir = Path(os.environ["NITELOS_MODEL_DIR"])
    cases = load_cases()
    images = images_map()
    smoke01 = next(case for case in cases if case["case_id"] == "SMK-001")
    report: dict[str, Any] = {
        "run": "NIT-008 approved iteration round (one bounded round per decisions.md)",
        "prompt_hashes": PROMPT_HASHES,
        "platform": {
            "os": platform.system(),
            "python": platform.python_version(),
        },
        "diagnostics": {},
        "full_runs": {},
    }
    for version in ("v2", "v3"):
        backend = SmolVLMBackend(model_dir, prompt_version=version)
        verifier = Verifier(backend=backend, policy=VerificationPolicy(allow_model_inference=True))
        report["diagnostics"][version] = {
            "D1_trivially_supported": run_case(verifier, backend, smoke01, images, D1_DESCRIPTION),
            "D2_trivially_refuted": run_case(verifier, backend, smoke01, images, D2_DESCRIPTION),
        }
        verifier.close()
        print(version, "diagnostics:", json.dumps(report["diagnostics"][version]))
    for version in ("v2", "v3"):
        backend = SmolVLMBackend(model_dir, prompt_version=version)
        verifier = Verifier(backend=backend, policy=VerificationPolicy(allow_model_inference=True))
        rows = []
        valid = decisive = 0
        for case in cases:
            row = run_case(verifier, backend, case, images)
            rows.append(row)
            if row["parsed_label"] is not None:
                valid += 1
                if row["parsed_label"] in ("SUPPORTED", "REFUTED"):
                    decisive += 1
        verifier.close()
        report["full_runs"][version] = {
            "cases": rows,
            "model_calls": sum(
                1 for row in rows if row["status"] != "ok" or row["basis"] == "model_inferred"
            ),
            "valid_labels": valid,
            "decisive_labels": decisive,
        }
        print(
            version,
            "full:",
            json.dumps({k: v for k, v in report["full_runs"][version].items() if k != "cases"}),
        )
    report["peak_rss_kb"] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    report["peak_rss_method"] = "resource.getrusage ru_maxrss (Linux, KiB)"
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "iteration-round.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print("written:", OUT / "iteration-round.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
