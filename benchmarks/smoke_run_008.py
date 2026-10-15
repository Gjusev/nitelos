"""NIT-008 real CPU smoke run over the 12-case development set (WSL py3.12).

Runs the full Verifier pipeline with the SmolVLM backend and prompt v1 on every
case, records per-case raw outputs/labels/decisions/timings plus aggregates,
and writes a machine-readable report JSON. SMK-005 is pending-phase: policy
resolves it with no model call. Never run inside the main checkout.
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

BENCH = Path(__file__).resolve().parent
REPO = BENCH.parent
SMOKE = REPO / "tests" / "fixtures" / "smoke"
OUT = Path(os.environ.get("SMOKE_OUT", BENCH / "smoke-run-local"))
EVIDENCE_SUBJECT = {"form": "smoke"}
AS_OF = "2026-06-01T10:00:00Z"
CAPTURED = "2026-06-01T09:59:00Z"
VALID_LABELS = ("SUPPORTED", "REFUTED", "UNKNOWN")


def load_cases() -> list[dict[str, Any]]:
    return json.loads((SMOKE / "cases.json").read_text(encoding="utf-8"))["cases"]


def build_request(case: dict[str, Any], images: dict[str, bytes]) -> dict[str, Any]:

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
                subject=dict(EVIDENCE_SUBJECT),
                phase="final",
                name=action["name"],
                arguments={},
                reported_status=action["reported_status"],
            )
        )
        next_sequence += 1
    for index, image_name in enumerate(case["images"]):
        data = images[image_name]
        evidence.append(
            Evidence.screenshot(
                id=f"shot-{index}",
                artifact_id=image_name,
                data=data,
                sequence=next_sequence,
                captured_at=CAPTURED,
                checkpoint_id="cp-final",
                source_id="smoke-runner",
                subject=dict(EVIDENCE_SUBJECT),
                phase=case["phase"],
            )
        )
        next_sequence += 1
    criterion: dict[str, Any] = {
        "id": "c-vis",
        "description": case["criterion"],
        "kind": "visual",
        "scope": "visual",
        "evidence_ids": [f"shot-{i}" for i in range(len(case["images"]))],
        "subject": dict(EVIDENCE_SUBJECT),
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


def main() -> int:
    from nitelos.backends.smolvlm import (  # noqa: PLC0415 - heavy imports stay out of module scope
        PROMPT_HASH_V1,
        SmolVLMBackend,
    )

    model_dir = Path(os.environ["NITELOS_MODEL_DIR"])
    cases = load_cases()
    images = {path.name: path.read_bytes() for path in SMOKE.glob("smoke-*.png")}
    backend = SmolVLMBackend(model_dir)
    verifier = Verifier(backend=backend, policy=VerificationPolicy(allow_model_inference=True))

    per_case: list[dict[str, Any]] = []
    model_calls = 0
    valid_labels = 0
    decisive_labels = 0
    matches_expected = 0
    backend_errors = 0
    warm_times: list[float] = []
    cold_ms: float | None = None
    started = time.monotonic()
    for case in cases:
        case_started = time.monotonic()
        attempts_before = backend.infer_attempts
        request = parse_request(build_request(case, images))
        result = verifier.verify(request, artifacts=images)
        elapsed_ms = (time.monotonic() - case_started) * 1000.0
        criterion = result.criteria[0] if result.criteria else None
        # an invocation happened iff the backend was called for this case: derived
        # from the per-case attempt delta, not from diagnostics fields the
        # verifier does not populate from the adapter
        invoked = backend.infer_attempts > attempts_before
        # record the raw generation even when the strict parser rejected it;
        # policy-only rows carry no generation of their own
        raw = backend.last_raw_output if invoked else None
        label = raw.strip() if raw is not None else None
        if cold_ms is None:
            cold_ms = elapsed_ms
        else:
            warm_times.append(elapsed_ms)
        record: dict[str, Any] = {
            "case_id": case["case_id"],
            "doc04_index": case["doc04_index"],
            "phase": case["phase"],
            "expected_label": case["expected_label"],
            "status": result.execution_status.value,
            "decision": result.decision.value if result.decision else None,
            "basis": criterion.basis.value if criterion else None,
            "reason_codes": list(result.reason_codes),
            "error_code": result.error.code.value if result.error else None,
            "elapsed_ms": round(elapsed_ms, 2),
            "model_invoked": invoked,
            "raw_output": raw,
            "parsed_label": label if label in VALID_LABELS else None,
        }
        if invoked:
            model_calls += 1
        if record["status"] == "backend_error":
            backend_errors += 1
        if record["parsed_label"] is not None:
            valid_labels += 1
            if record["parsed_label"] in ("SUPPORTED", "REFUTED"):
                decisive_labels += 1
            if record["parsed_label"] == case["expected_label"]:
                matches_expected += 1
        per_case.append(record)
    wall_ms = (time.monotonic() - started) * 1000.0
    verifier.close()

    peak_rss_kb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    manifest = json.loads((model_dir / "nitelos-manifest.json").read_text(encoding="utf-8"))
    report = {
        "run": "NIT-008 CPU smoke run (dev-only labels; not an accuracy benchmark)",
        "prompt_version": "smolvlm-criterion-v1",
        "prompt_hash": PROMPT_HASH_V1,
        "backend": {
            "id": backend.descriptor.id,
            "model_id": backend.descriptor.model_id,
            "model_revision": backend.descriptor.model_revision,
            "runtime_lock_hash": backend.descriptor.runtime_lock_hash,
        },
        "model_load_ms": backend.model_load_ms,
        "platform": {
            "os": platform.system(),
            "python": platform.python_version(),
            "cpu": _cpu_model(),
        },
        "peak_rss_kb": peak_rss_kb,
        "peak_rss_method": "resource.getrusage ru_maxrss (Linux, KiB)",
        "model_manifest": manifest,
        "cases": per_case,
        "aggregate": {
            "cases": len(per_case),
            "model_calls": model_calls,
            "backend_errors": backend_errors,
            "policy_only_case": "SMK-005",
            "valid_labels": valid_labels,
            "decisive_labels": decisive_labels,
            "matches_expected_label": matches_expected,
            "valid_label_rate": round(valid_labels / max(model_calls, 1), 4),
            "wall_ms": round(wall_ms, 2),
            "cold_ms": round(cold_ms, 2) if cold_ms is not None else None,
            "warm_mean_ms": round(sum(warm_times) / len(warm_times), 2) if warm_times else None,
        },
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "smoke-run.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report["aggregate"]))
    for record in per_case:
        print(
            f"{record['case_id']}: status={record['status']} decision={record['decision']} "
            f"basis={record['basis']} invoked={record['model_invoked']} "
            f"label={record['parsed_label']} raw={record['raw_output']!r} {record['elapsed_ms']}ms"
        )
    return 0


def _cpu_model() -> str:
    try:
        info = Path("/proc/cpuinfo").read_text(encoding="utf-8")
        for line in info.splitlines():
            if line.startswith("model name"):
                return line.split(":", 1)[1].strip()
    except OSError:
        pass
    return platform.processor() or "unknown"


if __name__ == "__main__":
    raise SystemExit(main())
