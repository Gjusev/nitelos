"""EVAL-01..04: reproducible sequential evaluation runner (NIT-012).

Authority: docs/implementation/nit-012-runner-design.md (readings A1-A7), doc 06
(manifest/runner contract, metrics, reporting), doc 07 (SEC-07, new-directory data
lifecycle), doc 12 (commands, EVAL family, exit codes), decisions.md (oracle-triple
validation; run-level cost/RAM/throughput). The mini benchmark builders here are the
"real" fixtures shrunk: strict manifests, per-case oracles, a fixture collector.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, ClassVar

import pytest

from nitelos import VerificationPolicy, Verifier, canonical_json
from nitelos.evaluation.runner import (
    RunnerError,
    compare_reports,
    evaluate,
    load_evaluation_manifest,
    safe_relative_path,
)

SUBJECT = {"form": "registration-1"}
SENTINEL = "ORACLE-SENTINEL-4c1f"
AS_OF = "2026-10-20T10:01:00Z"


def _digest(payload: Any) -> str:
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def _obs_doc(eid: str, sequence: int, data: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": eid,
        "kind": "observation",
        "sequence": sequence,
        "captured_at": f"2026-10-20T10:00:{sequence:02d}Z",
        "checkpoint_id": "cp-final",
        "source_id": "fixture-ui",
        "subject": dict(SUBJECT),
        "phase": "final",
        "sha256": _digest(data),
        "channel": "dom",
        "data": data,
    }


def _ok_request_doc(case_id: str, eid: str) -> dict[str, Any]:
    return {
        "schema_version": "1",
        "request_id": f"{case_id}-a",
        "objective": "Complete the synthetic registration task",
        "checkpoint_id": "cp-final",
        "as_of": AS_OF,
        "criteria": [
            {
                "id": "no-errors",
                "description": "No validation error remains",
                "kind": "assertion",
                "scope": "observed_state",
                "evidence_ids": [eid],
                "subject": dict(SUBJECT),
                "pointer": "/validation_error",
                "operator": "equals",
                "expected": False,
            }
        ],
        "evidence": [_obs_doc(eid, 0, {"validation_error": False})],
        "metadata": {},
    }


def _ext_request_doc(case_id: str, eid: str) -> dict[str, Any]:
    doc = _ok_request_doc(case_id, eid)
    doc["criteria"] = [
        {
            "id": "stored",
            "description": "Backend record reports the item stored",
            "kind": "assertion",
            "scope": "external",
            "evidence_ids": [eid],
            "subject": dict(SUBJECT),
            "pointer": "/status",
            "operator": "equals",
            "expected": "stored",
        }
    ]
    doc["evidence"] = [
        {
            **_obs_doc(eid, 0, {"status": "stored"}),
            "channel": "external_api",
            "source_id": "fixture-collector-v1",
        }
    ]
    return doc


def _oracle_doc(case_id: str, expected_decision: str = "success") -> dict[str, Any]:
    return {
        "case_id": case_id,
        "group_id": "s99:L1",
        "primary_family": "S99",
        "secondary_tags": [],
        "split": "dev",
        "state": {"final_status": "completed"},
        "outcome_truth": "success",
        "evidence_sufficiency": "sufficient",
        "expected": {
            "assertion": {"decision": expected_decision, "reason_codes": ["ALL_CRITERIA_SUPPORTED"]},
            "visual": {"decision": expected_decision, "reason_codes": ["ALL_CRITERIA_SUPPORTED"]},
        },
        "oracle_source_id": "state-machine:test:v1",
        "pair": None,
        "rationale": "test fixture",
        "scope": ["observed_state"],
        "annotators": [],
        "annotation_status": "pending_human_review",
        "sign_off": None,
    }


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


@dataclass
class MiniBenchmark:
    root: Path
    manifest_path: Path
    case_ids: list[str]

    def manifest(self) -> dict[str, Any]:
        return json.loads(self.manifest_path.read_text(encoding="utf-8"))


def build_mini_benchmark(
    root: Path,
    *,
    cases: list[str] | None = None,
    bad_request: bool = False,
    view: str = "assertion",
    policy: dict[str, Any] | None = None,
) -> MiniBenchmark:
    """Build a tiny valid benchmark: one ok case by default, plus optional extras.

    case id suffixes: '-in' writes an invalid request (input error), '-ext' writes an
    external-criterion case (needs collector bindings), '-back' is valid but the test
    factory makes its verifier raise (backend error).
    """
    root.mkdir(parents=True, exist_ok=True)
    (root / "artifacts").mkdir(exist_ok=True)
    entries = []
    collector = []
    for case_id in cases or ["c-ok"]:
        if case_id.endswith("-in"):
            (root / "requests" / f"{case_id}-assertion.json").write_text("{ not json", encoding="utf-8")
            _write_json(root / "oracle" / f"{case_id}.json", _oracle_doc(case_id))
        elif case_id.endswith("-ext"):
            doc = _ext_request_doc(case_id, f"{case_id}-obs")
            _write_json(root / "requests" / f"{case_id}-assertion.json", doc)
            oracle = _oracle_doc(case_id)
            oracle["scope"] = ["external"]
            _write_json(root / "oracle" / f"{case_id}.json", oracle)
            item = doc["evidence"][0]
            collector.append(
                {
                    "evidence_id": item["id"],
                    "sha256": item["sha256"],
                    "source_id": item["source_id"],
                    "subject": item["subject"],
                    "checkpoint_id": item["checkpoint_id"],
                }
            )
        else:
            doc = _ok_request_doc(case_id, f"{case_id}-obs")
            if view == "visual":
                doc["criteria"] = [
                    {
                        "id": "appearance",
                        "description": "The synthetic window shows a completion banner",
                        "kind": "visual",
                        "scope": "visual",
                        "evidence_ids": [f"{case_id}-obs"],
                        "subject": dict(SUBJECT),
                    }
                ]
            _write_json(root / "requests" / f"{case_id}-assertion.json", doc)
            _write_json(root / "oracle" / f"{case_id}.json", _oracle_doc(case_id))
        entries.append(
            {
                "case_id": case_id,
                "group_id": "s99:L1",
                "primary_scenario": "S99",
                "request": f"requests/{case_id}-assertion.json",
                "artifacts": [],
                "oracle": f"oracle/{case_id}.json",
            }
        )
    effective_policy = policy or {"id": "strict", "version": "1", "allow_model_inference": False}
    effective_policy = {**effective_policy}
    effective_policy.setdefault("allow_model_inference", False)
    effective_policy.setdefault("hash", _digest({k: v for k, v in effective_policy.items() if k != "hash"}))
    manifest = {
        "schema_version": "1",
        "benchmark_id": "nitelos-test-mini",
        "benchmark_version": 1,
        "split": "dev",
        "evidence_view": view,
        "seed": None,
        "policy": effective_policy,
        "cases": entries,
        "provenance": {"license": "Apache-2.0", "synthetic": True, "data_card": "DATA_CARD.md"},
        "configuration_fingerprint": _digest("test-configuration"),
        "expected_count": len(entries),
    }
    manifest_path = root / "dev.json" if view == "assertion" else root / "dev-visual.json"
    _write_json(manifest_path, manifest)
    _write_json(
        root / "fixture-collector.json", {"collector_id": "fixture-collector-v1", "bindings": collector}
    )
    return MiniBenchmark(root, manifest_path, list(cases or ["c-ok"]))


def _factory(recorder: list[Any] | None = None, failing: set[str] | None = None):
    failing = failing or set()

    class RaisingVerifier:
        def verify(self, request: Any, *, artifacts: Any = None) -> Any:
            raise RuntimeError("SECRET model internals")

    class Factory:
        def __call__(self, case_id: str, request: Any, artifacts: Any, bindings: Any) -> Any:
            if recorder is not None:
                recorder.append((case_id, request, artifacts, bindings))
            if case_id in failing:
                return RaisingVerifier()
            return Verifier(policy=VerificationPolicy(), trust_bindings=bindings)

    return Factory()


def _load(root: Path) -> Any:
    mini = build_mini_benchmark(root / "bench")
    return load_evaluation_manifest(mini.manifest_path, mini.root), mini


def _read_cases(output: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in (output / "cases.jsonl").read_text(encoding="utf-8").splitlines()]


# --------------------------------------------------------------------------
# EVAL-01: every scheduled case has an output; identity holds
# --------------------------------------------------------------------------


def test_eval01_every_scheduled_case_has_output(tmp_path: Path) -> None:
    mini = build_mini_benchmark(tmp_path / "bench3", cases=["c-ok", "c-in", "c-back", "c-ext"])
    manifest = load_evaluation_manifest(mini.manifest_path, mini.root)
    summary = evaluate(manifest, _factory(failing={"c-back"}), tmp_path / "out3")
    assert summary.status == "complete"
    assert summary.scheduled == 4
    assert summary.ok_count == 2
    assert summary.error_count == 2
    assert summary.scheduled == summary.ok_count + summary.error_count
    rows = _read_cases(tmp_path / "out3")
    assert len(rows) == 4
    by_id = {row["case_id"]: row for row in rows}
    assert by_id["c-ok"]["execution_status"] == "ok"
    assert by_id["c-ok"]["decision"] == "success"
    assert by_id["c-in"]["execution_status"] == "input_error"
    assert by_id["c-in"]["decision"] is None
    assert by_id["c-back"]["execution_status"] == "backend_error"
    assert by_id["c-back"]["error_code"] == "BACKEND_EXCEPTION"
    assert by_id["c-ext"]["execution_status"] == "ok"
    assert by_id["c-ext"]["decision"] == "success"
    assert (tmp_path / "out3" / "COMPLETE").exists()
    assert (tmp_path / "out3" / "metrics.json").exists()
    metrics = json.loads((tmp_path / "out3" / "metrics.json").read_text(encoding="utf-8"))
    assert metrics["counts"]["n"] == 4


# --------------------------------------------------------------------------
# EVAL-02: refuse overwrite; interrupted run incomplete; no resume
# --------------------------------------------------------------------------


def test_eval02_refuses_existing_output_directory(tmp_path: Path) -> None:
    (manifest, _mini) = _load(tmp_path / "a")
    existing = tmp_path / "out"
    existing.mkdir()
    with pytest.raises(RunnerError, match="exists"):
        evaluate(manifest, _factory(), existing)
    (existing / "sentinel.txt").write_text("untouched", encoding="utf-8")
    with pytest.raises(RunnerError):
        evaluate(manifest, _factory(), existing)
    assert (existing / "sentinel.txt").read_text(encoding="utf-8") == "untouched"


def test_eval02_interrupted_run_is_explicitly_incomplete(tmp_path: Path) -> None:
    mini = build_mini_benchmark(tmp_path / "bench", cases=["c-ok", "c-in", "c-back"])
    manifest = load_evaluation_manifest(mini.manifest_path, mini.root)

    class InfraFactory:
        def __call__(self, case_id: str, request: Any, artifacts: Any, bindings: Any) -> Any:
            if case_id == "c-back":  # the third scheduled case (valid request)
                raise OSError("disk exploded")  # infrastructure failure mid-run
            return Verifier(policy=VerificationPolicy(), trust_bindings=bindings)

    # infrastructure failure: an explicit incomplete report is written and the
    # runner raises (the CLI turns this into exit 3); results so far survive
    with pytest.raises(RunnerError, match="infrastructure"):
        evaluate(manifest, InfraFactory(), tmp_path / "out")
    assert not (tmp_path / "out" / "COMPLETE").exists()
    run = json.loads((tmp_path / "out" / "run.json").read_text(encoding="utf-8"))
    assert run["status"] == "incomplete"
    assert run["scheduled"] == 3
    assert run["completed"] == 2  # c-ok and the c-in input-error row
    assert run["incomplete_reason"]
    assert len(_read_cases(tmp_path / "out")) == 2
    with pytest.raises(RunnerError, match="exists"):
        evaluate(manifest, _factory(), tmp_path / "out")  # no resume: refusal


# --------------------------------------------------------------------------
# EVAL-03: compare_reports fingerprint matching
# --------------------------------------------------------------------------


def _run_into(tmp_path: Path, name: str, bench: MiniBenchmark) -> Path:
    manifest = load_evaluation_manifest(bench.manifest_path, bench.root)
    summary = evaluate(manifest, _factory(), tmp_path / name)
    assert summary.status == "complete"
    return tmp_path / name


def test_eval03_compare_matches_identical_and_rejects_differences(tmp_path: Path) -> None:
    bench_a = build_mini_benchmark(tmp_path / "bench-a", cases=["c-ok", "c-ext"])
    run_a = _run_into(tmp_path, "run-a", bench_a)
    bench_b = build_mini_benchmark(tmp_path / "bench-b", cases=["c-ok", "c-ext"])
    run_b = _run_into(tmp_path, "run-b", bench_b)
    comparison = compare_reports(run_a, run_b)
    assert comparison["compatible"] is True
    assert comparison["preprocessing"]["matched"] is True

    # changed policy
    bench_c = build_mini_benchmark(
        tmp_path / "bench-c", cases=["c-ok", "c-ext"], policy={"id": "custom", "version": "1"}
    )
    run_c = _run_into(tmp_path, "run-c", bench_c)
    with pytest.raises(RunnerError, match="policy"):
        compare_reports(run_a, run_c)

    # different evidence view
    bench_d = build_mini_benchmark(tmp_path / "bench-d", cases=["c-ok"], view="visual")
    run_d = _run_into(tmp_path, "run-d", bench_d)
    with pytest.raises(RunnerError, match="view"):
        compare_reports(run_a, run_d)

    # changed evidence bytes: rewrite one request with a different objective
    target = bench_b.root / "requests" / "c-ok-assertion.json"
    doc = json.loads(target.read_text(encoding="utf-8"))
    doc["objective"] = "A different objective entirely"
    _write_json(target, doc)
    run_e = _run_into(tmp_path, "run-e", bench_b)
    with pytest.raises(RunnerError, match="evidence"):
        compare_reports(run_a, run_e)


# --------------------------------------------------------------------------
# EVAL-04: oracle isolation and report determinism
# --------------------------------------------------------------------------


def test_eval04_oracle_never_reaches_verifier_or_reports(tmp_path: Path) -> None:
    mini = build_mini_benchmark(tmp_path / "bench", cases=["c-ok"])
    oracle_path = mini.root / "oracle" / "c-ok.json"
    oracle = json.loads(oracle_path.read_text(encoding="utf-8"))
    oracle["secret_marker"] = SENTINEL
    oracle["rationale"] = f"reasoning {SENTINEL}"
    _write_json(oracle_path, oracle)
    manifest = load_evaluation_manifest(mini.manifest_path, mini.root)
    recorded: list[Any] = []

    class RecordingFactory:
        def __call__(self, case_id: str, request: Any, artifacts: Any, bindings: Any) -> Any:
            if case_id.startswith("#preprocessing-probe"):
                return Verifier(policy=VerificationPolicy(), trust_bindings=())
            recorded.append((case_id, request, artifacts, bindings))
            return Verifier(policy=VerificationPolicy(), trust_bindings=bindings)

    summary = evaluate(manifest, RecordingFactory(), tmp_path / "out")
    assert summary.status == "complete"
    for _case_id, request, _artifacts, _bindings in recorded:
        assert SENTINEL not in canonical_json({"id": request.request_id, "objective": request.objective})
        assert not hasattr(request, "secret_marker")
        assert not hasattr(request, "outcome_truth")
    report_text = (tmp_path / "out" / "cases.jsonl").read_text(encoding="utf-8") + (
        tmp_path / "out" / "metrics.json"
    ).read_text(encoding="utf-8")
    assert SENTINEL not in report_text


def test_eval04_reports_stable_except_ids_and_timing(tmp_path: Path) -> None:
    bench = build_mini_benchmark(tmp_path / "bench", cases=["c-ok", "c-ext"])
    run_a = _run_into(tmp_path, "stable-a", bench)
    run_b = _run_into(tmp_path, "stable-b", bench)
    whitelist = {
        "run_id",
        "started_at",
        "finished_at",
        "elapsed_ms",
        "throughput_cases_per_second",
        "peak_rss_bytes",
    }

    def normalize(path: Path) -> Any:
        doc = json.loads(path.read_text(encoding="utf-8"))
        return {k: v for k, v in doc.items() if k not in whitelist}

    assert normalize(run_a / "run.json") == normalize(run_b / "run.json")
    rows_a = [
        {k: v for k, v in row.items() if k not in whitelist | {"duration_ms"}} for row in _read_cases(run_a)
    ]
    rows_b = [
        {k: v for k, v in row.items() if k not in whitelist | {"duration_ms"}} for row in _read_cases(run_b)
    ]
    assert rows_a == rows_b
    metrics_a = json.loads((run_a / "metrics.json").read_text(encoding="utf-8"))
    metrics_b = json.loads((run_b / "metrics.json").read_text(encoding="utf-8"))

    def strip_volatile(metrics: dict[str, Any]) -> dict[str, Any]:
        out = {k: v for k, v in metrics.items() if k != "latency"}
        run_level = dict(out.get("run_level", {}))
        run_level.pop("throughput_cases_per_second", None)
        out["run_level"] = run_level
        return out

    assert strip_volatile(metrics_a) == strip_volatile(metrics_b)


# --------------------------------------------------------------------------
# oracle triple validation (decisions.md carry-forward)
# --------------------------------------------------------------------------


def test_oracle_triple_violation_is_an_infrastructure_failure(tmp_path: Path) -> None:
    mini = build_mini_benchmark(tmp_path / "bench", cases=["c-ok"])
    oracle_path = mini.root / "oracle" / "c-ok.json"
    oracle = json.loads(oracle_path.read_text(encoding="utf-8"))
    # an ok expectation must carry a decision; null it out to violate the triple
    oracle["expected"]["assertion"] = {"decision": None, "reason_codes": ["X"]}
    _write_json(oracle_path, oracle)
    manifest = load_evaluation_manifest(mini.manifest_path, mini.root)
    with pytest.raises(RunnerError, match="oracle"):
        evaluate(manifest, _factory(), tmp_path / "out")
    assert not (tmp_path / "out" / "COMPLETE").exists()


# --------------------------------------------------------------------------
# manifest validation and limits
# --------------------------------------------------------------------------


def test_manifest_limit_and_shape_violations_fail_at_load(tmp_path: Path) -> None:
    mini = build_mini_benchmark(tmp_path / "bench")
    doc = mini.manifest()
    doc["extra_trust"] = {"binding": True}  # A4: unknown field, not silently ignored
    _write_json(mini.manifest_path, doc)
    with pytest.raises(RunnerError, match="manifest"):
        load_evaluation_manifest(mini.manifest_path, mini.root)
    mini = build_mini_benchmark(tmp_path / "bench")  # fresh tree per mutation
    doc = mini.manifest()
    doc["expected_count"] = 2
    _write_json(mini.manifest_path, doc)
    with pytest.raises(RunnerError, match="count"):
        load_evaluation_manifest(mini.manifest_path, mini.root)
    mini = build_mini_benchmark(tmp_path / "bench")
    doc = mini.manifest()
    doc["policy"]["allow_model_inference"] = True  # hash no longer matches
    _write_json(mini.manifest_path, doc)
    with pytest.raises(RunnerError, match="policy"):
        load_evaluation_manifest(mini.manifest_path, mini.root)


# --------------------------------------------------------------------------
# fixture trust: collector digests gate external criteria
# --------------------------------------------------------------------------


def test_tampered_collector_digest_yields_untrusted_external(tmp_path: Path) -> None:
    mini = build_mini_benchmark(tmp_path / "bench", cases=["c-ext"])
    collector_path = mini.root / "fixture-collector.json"
    collector = json.loads(collector_path.read_text(encoding="utf-8"))
    collector["bindings"][0]["sha256"] = "b" * 64
    _write_json(collector_path, collector)
    manifest = load_evaluation_manifest(mini.manifest_path, mini.root)
    summary = evaluate(manifest, _factory(), tmp_path / "out")
    assert summary.status == "complete"
    (row,) = _read_cases(tmp_path / "out")
    assert row["execution_status"] == "ok"
    assert row["decision"] == "abstained"
    assert "UNTRUSTED_EXTERNAL" in row["reason_codes"]


# --------------------------------------------------------------------------
# visual manifest with the deterministic backend: input errors, run complete
# --------------------------------------------------------------------------


def test_visual_manifest_with_deterministic_backend_completes_with_input_errors(tmp_path: Path) -> None:
    bench = build_mini_benchmark(tmp_path / "bench", cases=["c-ok"], view="visual")
    # visual view needs a visual criterion and a screenshot-free request still
    # gets UNSUPPORTED_CAPABILITY from the deterministic backend preflight
    manifest = load_evaluation_manifest(bench.manifest_path, bench.root)
    summary = evaluate(manifest, _factory(), tmp_path / "out")
    assert summary.status == "complete"
    (row,) = _read_cases(tmp_path / "out")
    assert row["execution_status"] == "input_error"
    assert row["error_code"] == "UNSUPPORTED_CAPABILITY"
    assert (tmp_path / "out" / "COMPLETE").exists()


# --------------------------------------------------------------------------
# CLI exit codes and the smolvlm stub
# --------------------------------------------------------------------------


def _cli(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "nitelos.evaluation", *args],
        check=False,
        capture_output=True,
        text=True,
        cwd=Path(__file__).resolve().parents[1],
    )


def test_cli_complete_run_exits_zero(tmp_path: Path) -> None:
    mini = build_mini_benchmark(tmp_path / "bench", cases=["c-ok", "c-ext"])
    out = tmp_path / "cli-out"
    proc = _cli(
        [
            "run",
            "--manifest",
            str(mini.manifest_path),
            "--artifacts",
            str(mini.root),
            "--output",
            str(out),
            "--backend",
            "deterministic",
        ]
    )
    assert proc.returncode == 0, proc.stderr
    assert (out / "COMPLETE").exists()
    assert len(_read_cases(out)) == 2


def test_cli_invalid_manifest_exits_two(tmp_path: Path) -> None:
    mini = build_mini_benchmark(tmp_path / "bench")
    doc = mini.manifest()
    doc["schema_version"] = "7"
    _write_json(mini.manifest_path, doc)
    proc = _cli(
        [
            "run",
            "--manifest",
            str(mini.manifest_path),
            "--artifacts",
            str(mini.root),
            "--output",
            str(tmp_path / "out"),
            "--backend",
            "deterministic",
        ]
    )
    assert proc.returncode == 2
    assert "manifest" in (proc.stderr + proc.stdout).lower()


def test_cli_smolvlm_without_backend_module_exits_two(tmp_path: Path) -> None:
    mini = build_mini_benchmark(tmp_path / "bench")
    proc = _cli(
        [
            "run",
            "--manifest",
            str(mini.manifest_path),
            "--artifacts",
            str(mini.root),
            "--output",
            str(tmp_path / "out"),
            "--backend",
            "smolvlm",
        ]
    )
    assert proc.returncode == 2
    assert not (tmp_path / "out").exists() or not (tmp_path / "out" / "COMPLETE").exists()
    combined = proc.stderr + proc.stdout
    assert "local" in combined.lower() or "smolvlm" in combined.lower()


def test_cli_model_dir_rejected_for_deterministic_exits_two(tmp_path: Path) -> None:
    mini = build_mini_benchmark(tmp_path / "bench")
    proc = _cli(
        [
            "run",
            "--manifest",
            str(mini.manifest_path),
            "--artifacts",
            str(mini.root),
            "--output",
            str(tmp_path / "out"),
            "--backend",
            "deterministic",
            "--model-dir",
            str(tmp_path),
        ]
    )
    assert proc.returncode == 2


def test_cli_infrastructure_failure_exits_three(tmp_path: Path) -> None:
    mini = build_mini_benchmark(tmp_path / "bench", cases=["c-ok"])
    (mini.root / "requests" / "c-ok-assertion.json").unlink()  # missing mid-run
    out = tmp_path / "out"
    proc = _cli(
        [
            "run",
            "--manifest",
            str(mini.manifest_path),
            "--artifacts",
            str(mini.root),
            "--output",
            str(out),
            "--backend",
            "deterministic",
        ]
    )
    assert proc.returncode == 3
    run = json.loads((out / "run.json").read_text(encoding="utf-8"))
    assert run["status"] == "incomplete"
    assert not (out / "COMPLETE").exists()


def test_cli_refuses_existing_output_exits_two(tmp_path: Path) -> None:
    mini = build_mini_benchmark(tmp_path / "bench")
    out = tmp_path / "out"
    out.mkdir()
    proc = _cli(
        [
            "run",
            "--manifest",
            str(mini.manifest_path),
            "--artifacts",
            str(mini.root),
            "--output",
            str(out),
            "--backend",
            "deterministic",
        ]
    )
    assert proc.returncode == 2


# --------------------------------------------------------------------------
# safe_relative_path unit table (SEC-07 lives in test_security.py; this is the
# loader-level behaviour the runner itself depends on)
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "bad",
    [
        "../escape.png",
        "a/../../b",
        "/absolute.png",
        "C:\\x.png",
        "\\\\server\\share\\x",
        "\\\\?\\C:\\x",
        "a:b",
        "CON",
        "NUL.bin",
        "com1.log",
        "x.",
        "x ",
        "a<b",
        "..",
        "a\x00b",
    ],
)
def test_safe_relative_path_rejects_hostile_paths(tmp_path: Path, bad: str) -> None:
    from nitelos.errors import EvidenceValidationError

    with pytest.raises((RunnerError, EvidenceValidationError)):
        safe_relative_path(tmp_path, bad)


def test_safe_relative_path_accepts_clean_relative(tmp_path: Path) -> None:
    target = tmp_path / "sub"
    target.mkdir()
    (target / "f.txt").write_text("x", encoding="utf-8")
    resolved = safe_relative_path(tmp_path, "sub/f.txt")
    assert resolved.name == "f.txt"


# --------------------------------------------------------------------------
# NIT-012 review fix: smolvlm wiring (mocked), collector reclassification,
# preprocessing-hash fingerprint
# --------------------------------------------------------------------------


def _visual_manifest(tmp_path: Path) -> MiniBenchmark:
    bench = build_mini_benchmark(tmp_path / "bench", cases=["c-ok"], view="visual")
    # visual manifests must declare the model opt-in for the factory path
    doc = json.loads(bench.manifest_path.read_text(encoding="utf-8"))
    policy = {"id": "visual-strict", "version": "1", "allow_model_inference": True}
    policy["hash"] = _digest(policy)
    doc["policy"] = policy
    _write_json(bench.manifest_path, doc)
    # the visual request cites an observation; a visual criterion on it reaches
    # the backend regardless of eligibility content in the mocked wiring test
    return bench


class _MockSmolVLMBackend:
    """Mocked backend: records construction args; a deterministic verifier wrapper."""

    instances: ClassVar[list[Any]] = []

    def __init__(self, model_dir: object, revision: object, **kwargs: object) -> None:
        self.model_dir = model_dir
        self.revision = revision
        self.kwargs = kwargs
        _MockSmolVLMBackend.instances.append(self)

    @property
    def descriptor(self) -> Any:
        from nitelos.schemas import BackendDescriptor

        return BackendDescriptor(
            id="smolvlm",
            version="1.0",
            preprocessing_hash="e" * 64,
        )

    @property
    def capabilities(self) -> Any:
        from nitelos.backends import BackendCapabilities

        return BackendCapabilities(
            evidence_kinds=("screenshot",),
            criterion_kinds=("visual",),
            supports_images=True,
            supports_evidence_references=True,
            max_images_per_criterion=2,
        )

    def infer(self, prepared: object, context: object) -> object:
        raise AssertionError("no inference in the wiring test")

    def close(self) -> None:
        return None


def test_smolvlm_factory_constructs_backend_and_verifier(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import types

    bench = _visual_manifest(tmp_path)
    manifest = load_evaluation_manifest(bench.manifest_path, bench.root)
    _MockSmolVLMBackend.instances.clear()
    import importlib.util

    fake_module = types.ModuleType("nitelos.backends.smolvlm")
    fake_module.SmolVLMBackend = _MockSmolVLMBackend  # type: ignore[attr-defined]
    fake_module.DEFAULT_REVISION = "482adb537c021c86670beed01cd58990d01e72e4"
    fake_spec = importlib.util.spec_from_file_location("nitelos.backends.smolvlm", __file__)
    fake_module.__spec__ = fake_spec
    monkeypatch.setitem(sys.modules, "nitelos.backends.smolvlm", fake_module)
    from nitelos.evaluation.runner import _build_verifier_factory

    factory = _build_verifier_factory("smolvlm", str(tmp_path / "weights"), manifest.policy)
    verifier = factory("c-ok", object(), {}, ())
    assert _MockSmolVLMBackend.instances, "the factory must construct SmolVLMBackend"
    (instance,) = _MockSmolVLMBackend.instances
    assert str(instance.model_dir).endswith("weights")
    assert instance.revision, "the pinned default revision is passed"
    assert verifier is not None


def test_smolvlm_factory_still_probes_module_availability(monkeypatch: pytest.MonkeyPatch) -> None:
    import importlib.util

    real = importlib.util.find_spec
    monkeypatch.setattr(
        importlib.util, "find_spec", lambda name: None if name == "nitelos.backends.smolvlm" else real(name)
    )
    from nitelos.evaluation.runner import ConfigError, _build_verifier_factory

    with pytest.raises(ConfigError, match="local"):
        _build_verifier_factory("smolvlm", "/weights", VerificationPolicy())


def test_collector_shape_error_is_configuration_exit_two(tmp_path: Path) -> None:
    mini = build_mini_benchmark(tmp_path / "bench", cases=["c-ok"])
    collector_path = mini.root / "fixture-collector.json"
    collector = json.loads(collector_path.read_text(encoding="utf-8"))
    collector["collector_id"] = "wrong-collector"  # trusted runner configuration error
    _write_json(collector_path, collector)
    from nitelos.evaluation.runner import ConfigError

    manifest = load_evaluation_manifest(mini.manifest_path, mini.root)
    with pytest.raises(ConfigError, match="collector"):
        evaluate(manifest, _factory(), tmp_path / "out")


def test_collector_missing_file_is_configuration_exit_two(tmp_path: Path) -> None:
    mini = build_mini_benchmark(tmp_path / "bench", cases=["c-ok"])
    (mini.root / "fixture-collector.json").unlink()
    from nitelos.evaluation.runner import ConfigError

    manifest = load_evaluation_manifest(mini.manifest_path, mini.root)
    with pytest.raises(ConfigError, match="collector"):
        evaluate(manifest, _factory(), tmp_path / "out")


def test_preprocessing_hash_captured_and_compared(tmp_path: Path) -> None:
    bench_a = build_mini_benchmark(tmp_path / "bench-a", cases=["c-ok"])
    run_a = _run_into(tmp_path, "pha", bench_a)
    run_meta = json.loads((run_a / "run.json").read_text(encoding="utf-8"))
    assert "preprocessing_hash" in run_meta
    bench_b = build_mini_benchmark(tmp_path / "bench-b", cases=["c-ok"])
    run_b = _run_into(tmp_path, "phb", bench_b)
    assert compare_reports(run_a, run_b)["compatible"] is True
    # mutate the recorded preprocessing hash -> disclosed mismatch
    meta = json.loads((run_b / "run.json").read_text(encoding="utf-8"))
    meta["preprocessing_hash"] = "f" * 64
    _write_json(run_b / "run.json", meta)
    comparison = compare_reports(run_a, run_b)
    assert comparison["compatible"] is True  # disclosed, not refused
    assert comparison["preprocessing"]["matched"] is False
    assert comparison["preprocessing"]["delta"]
