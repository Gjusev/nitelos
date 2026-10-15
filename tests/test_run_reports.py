"""RUN-01/02: frozen-run report validation (NIT-013 part A).

Authority: docs/implementation/nit-012-runner-design.md (report schemas and RUN rules),
docs/planning/10 (NIT-013: RUN-01 fails on missing case/status/version/hash, leaked
labels or fabricated measurements; RUN-02 verifies report count identities and per-family
completeness), doc 06 (oracle tokens never appear in reports). All fixtures are SYNTHETIC
report trees built to the runner's own shapes; the validator must accept an unmutated
run and reject each documented mutation.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from nitelos.evaluation.report_validation import ValidationError, validate_run_report

ORACLE_TOKENS = ("outcome_truth", "evidence_sufficiency", "annotators", "annotation_status")
FAMILIES = tuple(f"S{i:02d}" for i in range(1, 16))


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def build_synthetic_run(root: Path, *, families: list[str] | None = None) -> Path:
    """Build a complete synthetic run directory in the runner's exact shapes."""
    families = families or list(FAMILIES)
    run_dir = root / "run"
    case_rows = []
    case_index = 0
    for family in families:
        for case_number in range(4):
            case_index += 1
            case_id = f"0000000{case_index:04d}-0000-4000-8000-{case_index:012d}"
            ok = (case_number % 4) != 3
            row = {
                "run_id": "11111111-2222-4333-8444-555555555555",
                "case_id": case_id,
                "group_id": f"{family.lower()}:L{case_number + 1}",
                "primary_scenario": family,
                "request_hash": f"{case_index:064x}",
                "execution_status": "ok" if ok else "input_error",
                "decision": ("success" if case_number == 0 else "abstained") if ok else None,
                "reason_codes": ["ALL_CRITERIA_SUPPORTED"]
                if ok and case_number == 0
                else (["INSUFFICIENT_EVIDENCE", "MISSING_EVIDENCE"] if ok else ["INVALID_SCHEMA"]),
                "criterion_count": 1,
                "error_code": None if ok else "INVALID_SCHEMA",
                "duration_ms": 1.0 + case_index,
                "model_invoked": False,
                "backend_id": "deterministic",
                "trust_fingerprint": "",
                "evidence_hash": f"{case_index:064x}",
            }
            case_rows.append(row)
    ok_count = sum(1 for row in case_rows if row["execution_status"] == "ok")
    error_count = len(case_rows) - ok_count
    _write_json(
        run_dir / "run.json",
        {
            "run_id": "11111111-2222-4333-8444-555555555555",
            "status": "complete",
            "benchmark_id": "nitelos-synthetic-v1",
            "benchmark_version": 1,
            "split": "dev",
            "evidence_view": "assertion",
            "manifest_path": "dev.json",
            "manifest_sha256": "a" * 64,
            "scheduled": len(case_rows),
            "completed": len(case_rows),
            "started_at": "2026-10-20T10:00:00+00:00",
            "finished_at": "2026-10-20T10:01:00+00:00",
            "elapsed_ms": 1000.0,
            "peak_rss_bytes": None,
            "package_version": "0.1.0",
            "policy_hash": "b" * 64,
            "configuration_fingerprint": "c" * 64,
        },
    )
    with (run_dir / "cases.jsonl").open("w", encoding="utf-8") as sink:
        for row in case_rows:
            sink.write(json.dumps(row, sort_keys=True) + "\n")
    _write_json(
        run_dir / "metrics.json",
        {
            "counts": {
                "n": len(case_rows),
                "e": error_count,
                "b": 0,
                "o": ok_count,
                "a": 3,
                "d": ok_count - 3,
            },
            "metrics": [],
            "latency": {
                "cold": {"n": 0, "median": None, "p95": None},
                "warm": {"n": 0, "median": None, "p95": None},
                "all_attempts": {"n": len(case_rows), "median": 2.0, "p95": 9.0},
            },
            "run_level": {
                "cost_amount": None,
                "cost_unavailable_reason": "no_price_source",
                "peak_rss_bytes": None,
                "peak_rss_method": "peak_rss_unavailable_on_windows",
                "throughput_cases_per_second": 10.0,
            },
        },
    )
    (run_dir / "COMPLETE").write_text("11111111-2222-4333-8444-555555555555\n", encoding="utf-8")
    return run_dir


def _read_cases(run_dir: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in (run_dir / "cases.jsonl").read_text(encoding="utf-8").splitlines()]


def _rewrite_cases(run_dir: Path, rows: list[dict[str, Any]]) -> None:
    with (run_dir / "cases.jsonl").open("w", encoding="utf-8") as sink:
        for row in rows:
            sink.write(json.dumps(row, sort_keys=True) + "\n")


@pytest.fixture
def good_run(tmp_path: Path) -> Path:
    return build_synthetic_run(tmp_path)


def _mutated(tmp_path: Path, source: Path) -> Path:
    target = tmp_path / f"mut-{source.name}-{abs(hash(source)) % 10000}"
    shutil.copytree(source, target)
    return target


# --------------------------------------------------------------------------
# the unmutated report validates
# --------------------------------------------------------------------------


def test_run01_accepts_the_synthetic_report(good_run: Path) -> None:
    report = validate_run_report(good_run)
    assert report.status == "complete"
    assert report.scheduled == 60
    assert report.case_count == 60
    assert report.families == set(FAMILIES)


def test_run01_accepts_a_real_runner_output(tmp_path: Path) -> None:
    repo = Path(__file__).resolve().parents[1]
    out = tmp_path / "real"
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "nitelos.evaluation",
            "run",
            "--manifest",
            str(repo / "benchmarks/synthetic_v1/dev.json"),
            "--artifacts",
            str(repo / "benchmarks/synthetic_v1"),
            "--output",
            str(out),
            "--backend",
            "deterministic",
        ],
        check=False,
        capture_output=True,
        text=True,
        cwd=repo,
    )
    assert proc.returncode == 0, proc.stderr
    report = validate_run_report(out)
    assert report.status == "complete"
    assert report.scheduled == 60 == report.case_count
    assert report.families == set(FAMILIES)


# --------------------------------------------------------------------------
# RUN-01: missing/illegal fields, leaked labels, fabricated measurements
# --------------------------------------------------------------------------


def test_run01_missing_run_field_rejected(good_run: Path, tmp_path: Path) -> None:
    run = _mutated(tmp_path, good_run)
    doc = json.loads((run / "run.json").read_text(encoding="utf-8"))
    del doc["package_version"]
    _write_json(run / "run.json", doc)
    with pytest.raises(ValidationError, match="package_version"):
        validate_run_report(run)


def test_run01_missing_case_row_rejected(good_run: Path, tmp_path: Path) -> None:
    run = _mutated(tmp_path, good_run)
    rows = _read_cases(run)
    _rewrite_cases(run, rows[:-1])
    with pytest.raises(ValidationError, match="case"):
        validate_run_report(run)


def test_run01_status_complete_without_marker_rejected(good_run: Path, tmp_path: Path) -> None:
    run = _mutated(tmp_path, good_run)
    (run / "COMPLETE").unlink()
    with pytest.raises(ValidationError, match="marker"):
        validate_run_report(run)


def test_run01_marker_with_incomplete_status_rejected(good_run: Path, tmp_path: Path) -> None:
    run = _mutated(tmp_path, good_run)
    doc = json.loads((run / "run.json").read_text(encoding="utf-8"))
    doc["status"] = "incomplete"
    _write_json(run / "run.json", doc)
    with pytest.raises(ValidationError, match="status"):
        validate_run_report(run)


def test_run01_decision_on_error_row_rejected(good_run: Path, tmp_path: Path) -> None:
    run = _mutated(tmp_path, good_run)
    rows = _read_cases(run)
    for row in rows:
        if row["execution_status"] == "input_error":
            row["decision"] = "success"
            break
    _rewrite_cases(run, rows)
    with pytest.raises(ValidationError, match="decision"):
        validate_run_report(run)


def test_run01_null_decision_on_ok_row_rejected(good_run: Path, tmp_path: Path) -> None:
    run = _mutated(tmp_path, good_run)
    rows = _read_cases(run)
    for row in rows:
        if row["execution_status"] == "ok":
            row["decision"] = None
            break
    _rewrite_cases(run, rows)
    with pytest.raises(ValidationError, match="decision"):
        validate_run_report(run)


def test_run01_duplicate_case_id_rejected(good_run: Path, tmp_path: Path) -> None:
    run = _mutated(tmp_path, good_run)
    rows = _read_cases(run)
    doc = json.loads((run / "run.json").read_text(encoding="utf-8"))
    doc["scheduled"] = 61  # keep the count identity so only the duplicate fires
    _write_json(run / "run.json", doc)
    rows.append(dict(rows[0]))
    _rewrite_cases(run, rows)
    with pytest.raises(ValidationError, match="duplicate"):
        validate_run_report(run)


def test_run01_leaked_oracle_token_rejected(good_run: Path, tmp_path: Path) -> None:
    run = _mutated(tmp_path, good_run)
    rows = _read_cases(run)
    rows[0]["outcome_truth"] = "success"  # oracle field smuggled into a report row
    _rewrite_cases(run, rows)
    with pytest.raises(ValidationError, match=r"oracle|token|leak"):
        validate_run_report(run)


def test_run01_leaked_token_in_run_json_rejected(good_run: Path, tmp_path: Path) -> None:
    run = _mutated(tmp_path, good_run)
    doc = json.loads((run / "run.json").read_text(encoding="utf-8"))
    doc["evidence_sufficiency"] = "sufficient"
    _write_json(run / "run.json", doc)
    with pytest.raises(ValidationError, match=r"oracle|token|leak"):
        validate_run_report(run)


def test_run01_fabricated_measurement_rejected(good_run: Path, tmp_path: Path) -> None:
    run = _mutated(tmp_path, good_run)
    doc = json.loads((run / "metrics.json").read_text(encoding="utf-8"))
    # a peak RSS with no recorded method is a fabricated measurement
    doc["run_level"]["peak_rss_bytes"] = 123456789
    doc["run_level"]["peak_rss_method"] = None
    _write_json(run / "metrics.json", doc)
    with pytest.raises(ValidationError, match=r"measurement|rss|method"):
        validate_run_report(run)


def test_run01_zero_where_null_required_rejected(good_run: Path, tmp_path: Path) -> None:
    run = _mutated(tmp_path, good_run)
    doc = json.loads((run / "metrics.json").read_text(encoding="utf-8"))
    doc["run_level"]["cost_amount"] = 0.0  # cost must be null, not a zero claim
    doc["run_level"].pop("cost_unavailable_reason")
    _write_json(run / "metrics.json", doc)
    with pytest.raises(ValidationError, match="cost"):
        validate_run_report(run)


def test_run01_count_identity_break_rejected(good_run: Path, tmp_path: Path) -> None:
    run = _mutated(tmp_path, good_run)
    doc = json.loads((run / "metrics.json").read_text(encoding="utf-8"))
    doc["counts"]["n"] = 59  # does not equal rows + errors identity
    _write_json(run / "metrics.json", doc)
    with pytest.raises(ValidationError, match=r"count|identit"):
        validate_run_report(run)


# --------------------------------------------------------------------------
# RUN-02: count identities and per-family completeness
# --------------------------------------------------------------------------


def test_run02_scheduled_equals_ok_plus_errors(good_run: Path) -> None:
    report = validate_run_report(good_run)
    rows = _read_cases(good_run)
    ok = sum(1 for row in rows if row["execution_status"] == "ok")
    errors = sum(1 for row in rows if row["execution_status"] != "ok")
    assert report.scheduled == len(rows) == ok + errors
    assert report.ok_count == ok
    assert report.error_count == errors


def test_run02_missing_family_rejected(tmp_path: Path) -> None:
    families = [f for f in FAMILIES if f != "S07"]
    run = build_synthetic_run(tmp_path, families=families)
    with pytest.raises(ValidationError, match=r"famil"):
        validate_run_report(run, expected_families=set(FAMILIES))


def test_run02_family_with_no_cases_rejected(tmp_path: Path) -> None:
    run = build_synthetic_run(tmp_path, families=list(FAMILIES))
    rows = [row for row in _read_cases(run) if row["primary_scenario"] != "S09"]
    doc = json.loads((run / "run.json").read_text(encoding="utf-8"))
    doc["scheduled"] = len(rows)  # keep the row-count identity so only completeness fires
    _write_json(run / "run.json", doc)
    metrics = json.loads((run / "metrics.json").read_text(encoding="utf-8"))
    metrics["counts"]["n"] = len(rows)
    ok = sum(1 for row in rows if row["execution_status"] == "ok")
    metrics["counts"]["o"] = ok
    metrics["counts"]["e"] = len(rows) - ok
    _write_json(run / "metrics.json", metrics)
    _rewrite_cases(run, rows)
    with pytest.raises(ValidationError, match=r"famil"):
        validate_run_report(run, expected_families=set(FAMILIES))


def test_run02_run_id_consistency_across_rows(good_run: Path, tmp_path: Path) -> None:
    run = _mutated(tmp_path, good_run)
    rows = _read_cases(run)
    rows[0]["run_id"] = "99999999-9999-4999-8999-999999999999"
    _rewrite_cases(run, rows)
    with pytest.raises(ValidationError, match="run_id"):
        validate_run_report(run)
