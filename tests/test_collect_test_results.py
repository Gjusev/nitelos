"""TST-01..15: F3 test-results collector (NIT-019, kind ``junit``)."""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from nitelos import Verifier
from nitelos.collect import (
    CollectorErrorCode,
    CollectorLimits,
    host_trust_bindings,
    run_collector,
)
from nitelos.collect.test_results import COLLECTOR
from nitelos.collect.test_results import TestResultsConfig as JunitConfig
from nitelos.schemas import parse_request

BAD_GLOB_MESSAGE = chr(92).join(["report_glob must be a relative pattern"])

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "test-results"


def _config(
    pattern: str = "*",
    *,
    turn_start: datetime | None = None,
    max_age: int | None = None,
    max_raw_bytes: int = 1_048_576,
    max_list_items: int = 100,
    evidence_id: str = "tests-1",
) -> JunitConfig:
    return JunitConfig(
        evidence_id=evidence_id,
        checkpoint_id="cp-final",
        subject={"suite": "regression"},
        report_root=FIXTURES,
        report_glob=pattern,
        turn_start=turn_start,
        max_age_seconds=max_age,
        limits=CollectorLimits(max_raw_bytes=max_raw_bytes, max_list_items=max_list_items),
    )


def _run(pattern: str = "*", **kwargs: Any) -> Any:
    return run_collector(COLLECTOR, _config(pattern, **kwargs))


def _data(result: Any) -> dict[str, Any]:
    assert result.error is None, result.error
    assert len(result.evidence) == 1
    return dict(result.evidence[0].data)


def test_tst01_config_validation() -> None:
    def build(glob: str) -> JunitConfig:
        return JunitConfig(
            evidence_id="x-1",
            checkpoint_id="cp",
            subject={"suite": "s"},
            report_root=FIXTURES,
            report_glob=glob,
        )

    for bad in ("/abs/*.xml", "..\\escape\\*.xml", "../escape/*.xml", "C:/abs/*.xml"):
        with pytest.raises(ValidationError, match=BAD_GLOB_MESSAGE):
            build(bad)
    missing = run_collector(
        COLLECTOR,
        {
            "evidence_id": "x-3",
            "checkpoint_id": "cp",
            "subject": {"suite": "s"},
            "report_root": str(FIXTURES / "nope"),
            "report_glob": "*",
        },
    )
    assert missing.error is not None
    assert missing.error.code == CollectorErrorCode.CONFIG_INVALID
    res = run_collector(
        COLLECTOR,
        {
            "evidence_id": "x-4",
            "checkpoint_id": "cp",
            "subject": {"suite": "s"},
            "report_root": str(FIXTURES),
            "report_glob": "/abs/*.xml",
        },
    )
    assert res.error is not None
    assert res.error.code == CollectorErrorCode.CONFIG_INVALID


def test_tst02_pytest_junit_counts_and_ids() -> None:
    data = _data(_run("pytest-junit.xml"))
    assert data["total"] == 5
    assert data["passed"] == 2
    assert data["failed"] == 1
    assert data["errors"] == 1
    assert data["skipped"] == 1
    assert data["failed_ids"] == (
        "tests.test_reg::test_email_required",
        "tests.test_reg::test_crash",
    )
    assert data["report_paths"] == ("pytest-junit.xml",)
    assert "T" in str(data["report_mtime_max"])
    assert str(data["report_mtime_max"]).endswith("Z")


def test_tst03_jest_junit_and_multi_file_aggregation() -> None:
    data = _data(_run("jest-junit.xml"))
    assert data["total"] == 3
    assert data["failed"] == 1
    assert data["errors"] == 0
    assert data["passed"] == 2
    assert data["skipped"] == 0
    assert data["failed_ids"] == ("app renders the completion banner::hides spinner",)


def test_tst04_vitest() -> None:
    data = _data(_run("vitest-junit.xml"))
    assert data["total"] == 2
    assert data["failed"] == 0
    assert data["errors"] == 0
    assert data["skipped"] == 1
    assert data["passed"] == 1
    assert data["failed_ids"] == ()


def test_tst05_surefire_root_testsuite() -> None:
    data = _data(_run("surefire.xml"))
    assert data["total"] == 4
    assert data["errors"] == 1
    assert data["failed"] == 0
    assert data["skipped"] == 0
    assert data["passed"] == 3
    assert data["failed_ids"] == ("com.example.RegTest::confirms",)


def test_tst06_pytest_json_report() -> None:
    data = _data(_run("pytest-json.json"))
    assert data["total"] == 4
    assert data["passed"] == 2
    assert data["failed"] == 1
    assert data["errors"] == 0
    assert data["skipped"] == 1
    assert data["failed_ids"] == ("tests/test_a.py::test_two",)


def test_tst07_mixed_glob_aggregates_across_formats() -> None:
    data = _data(_run("*"))
    assert data["total"] == 5 + 3 + 2 + 4 + 4
    assert data["failed"] == 1 + 1 + 0 + 0 + 1
    assert data["errors"] == 1 + 0 + 0 + 1 + 0
    assert data["skipped"] == 1 + 0 + 1 + 0 + 1
    assert len(data["report_paths"]) == 5
    assert data["report_paths"] == tuple(sorted(data["report_paths"]))


def test_tst08_malformed_xml_is_structured_error() -> None:
    result = _run("bad/malformed.xml")
    assert result.error is not None
    assert result.error.code == CollectorErrorCode.EXCEPTION
    assert result.evidence == ()


def test_tst09_huge_file_rejected_by_cap(tmp_path: Path) -> None:
    huge = tmp_path / "huge.xml"
    huge.write_text('<testsuites tests="1">' + "x" * 2000 + "</testsuites>")
    cfg = JunitConfig(
        evidence_id="h-1",
        checkpoint_id="cp",
        subject={"suite": "s"},
        report_root=tmp_path,
        report_glob="*.xml",
        limits=CollectorLimits(max_raw_bytes=1024),
    )
    result = run_collector(COLLECTOR, cfg)
    assert result.error is not None
    assert result.error.code == CollectorErrorCode.OUTPUT_TOO_LARGE


def test_tst10_doctype_and_entities_rejected() -> None:
    result = _run("bad/dtd.xml")
    assert result.error is not None
    assert result.error.code == CollectorErrorCode.EXCEPTION
    assert result.evidence == ()


def test_tst11_freshness_gates(tmp_path: Path) -> None:
    old = tmp_path / "old.xml"
    old.write_text('<testsuites tests="1"><testcase name="a"/></testsuites>')
    past = datetime.now(UTC) - timedelta(hours=2)
    recent = datetime.now(UTC) - timedelta(minutes=1)
    os.utime(old, (past.timestamp(), past.timestamp()))

    all_stale_by_age = _run_from(tmp_path, max_age=3600)
    assert all_stale_by_age.error is None
    assert all_stale_by_age.evidence == ()

    all_stale_by_turn = _run_from(tmp_path, turn_start=recent)
    assert all_stale_by_turn.error is None
    assert all_stale_by_turn.evidence == ()

    fresh = tmp_path / "new.xml"
    fresh.write_text('<testsuites tests="2"><testcase name="b"/></testsuites>')
    mixed = _run_from(tmp_path, turn_start=recent)
    assert mixed.error is None
    assert len(mixed.evidence) == 1
    data = dict(mixed.evidence[0].data)
    assert data["report_paths"] == ("new.xml",)
    assert data["total"] == 2


def _run_from(root: Path, *, turn_start: datetime | None = None, max_age: int | None = None) -> Any:
    return run_collector(
        COLLECTOR,
        JunitConfig(
            evidence_id="f-1",
            checkpoint_id="cp",
            subject={"suite": "s"},
            report_root=root,
            report_glob="*.xml",
            turn_start=turn_start,
            max_age_seconds=max_age,
        ),
    )


def test_tst12_failed_ids_capped(tmp_path: Path) -> None:
    cases = "".join(f'<testcase classname="c" name="t{i}"><failure/></testcase>' for i in range(5))
    (tmp_path / "many.xml").write_bytes(
        f'<testsuites><testsuite tests="5" failures="5">{cases}</testsuite></testsuites>'.encode()
    )
    cfg = JunitConfig(
        evidence_id="c-1",
        checkpoint_id="cp",
        subject={"suite": "s"},
        report_root=tmp_path,
        report_glob="*.xml",
        limits=CollectorLimits(max_list_items=3),
    )
    result = run_collector(COLLECTOR, cfg)
    assert result.error is None
    data = dict(result.evidence[0].data)
    assert data["total"] == 5
    assert data["failed"] == 5
    assert len(data["failed_ids"]) == 3
    assert data["failed_ids"] == ("c::t0", "c::t1", "c::t2")
    assert data["failed_ids_truncated"] == 2


def test_tst13_too_many_report_files_is_error(tmp_path: Path) -> None:
    for i in range(4):
        (tmp_path / f"r{i}.xml").write_text('<testsuites tests="1"/>')
    cfg = JunitConfig(
        evidence_id="m-1",
        checkpoint_id="cp",
        subject={"suite": "s"},
        report_root=tmp_path,
        report_glob="*.xml",
        limits=CollectorLimits(max_list_items=3),
    )
    result = run_collector(COLLECTOR, cfg)
    assert result.error is not None
    assert result.error.code == CollectorErrorCode.OUTPUT_TOO_LARGE


def test_tst13b_doctype_scan_only_in_xml_branch(tmp_path: Path) -> None:
    report = tmp_path / "report.json"
    report.write_text(
        json.dumps(
            {
                "summary": {"total": 1, "passed": 0, "failed": 1, "skipped": 0},
                "tests": [{"nodeid": "tests/test_x.py::test_mentions[<!DOCTYPE html>]", "outcome": "failed"}],
            }
        ),
        encoding="utf-8",
    )
    cfg = JunitConfig(
        evidence_id="d-1",
        checkpoint_id="cp",
        subject={"suite": "s"},
        report_root=tmp_path,
        report_glob="*.json",
    )
    result = run_collector(COLLECTOR, cfg)
    assert result.error is None
    data = dict(result.evidence[0].data)
    assert data["total"] == 1
    assert data["failed_ids"] == ("tests/test_x.py::test_mentions[<!DOCTYPE html>]",)


def test_tst14_zero_matches_is_empty_success() -> None:
    result = _run("nothing-matches-*.txt")
    assert result.error is None
    assert result.evidence == ()
    assert result.provenance == ()


def test_tst15_framework_contract_and_end_to_end(tmp_path: Path) -> None:
    src = FIXTURES / "pytest-junit.xml"
    (tmp_path / "run.xml").write_bytes(src.read_bytes())
    result = _run_from(tmp_path)
    assert result.error is None
    item = result.evidence[0]
    assert item.source_id == COLLECTOR.id
    assert str(item.channel) == "external_api"
    assert item.subject == {"suite": "s"}
    assert item.checkpoint_id == "cp"
    record = result.provenance[0]
    assert record.collector_id == COLLECTOR.id
    assert record.evidence_sha256 == item.sha256
    assert record.raw_bytes == (tmp_path / "run.xml").stat().st_size
    bindings = host_trust_bindings(result)
    assert len(bindings) == 1

    as_of = datetime.now(UTC) + timedelta(minutes=1)
    request = parse_request(
        json.dumps(
            {
                "schema_version": "1",
                "request_id": "tst-15",
                "objective": "Tests pass",
                "checkpoint_id": "cp",
                "as_of": as_of.isoformat().replace("+00:00", "Z"),
                "criteria": [
                    {
                        "id": "no-failures",
                        "description": "No test failed",
                        "kind": "assertion",
                        "scope": "external",
                        "evidence_ids": [item.id],
                        "subject": {"suite": "s"},
                        "pointer": "/failed",
                        "operator": "equals",
                        "expected": 0,
                    }
                ],
                "evidence": [json.loads(item.model_dump_json(exclude_none=True))],
            }
        )
    )
    verifier = Verifier(trust_bindings=bindings)
    outcome = verifier.verify(request)
    assert outcome.execution_status == "ok"
    assert outcome.decision == "failure"  # the fixture has failures; criterion expects 0

    stale = Verifier(trust_bindings=bindings).verify(
        parse_request(
            json.dumps(
                {
                    "schema_version": "1",
                    "request_id": "tst-15b",
                    "objective": "Tests pass",
                    "checkpoint_id": "cp",
                    "as_of": (datetime.now(UTC) + timedelta(days=2)).isoformat().replace("+00:00", "Z"),
                    "criteria": [
                        {
                            "id": "no-failures",
                            "description": "No test failed",
                            "kind": "assertion",
                            "scope": "external",
                            "evidence_ids": [item.id],
                            "subject": {"suite": "s"},
                            "pointer": "/failed",
                            "operator": "equals",
                            "expected": 0,
                            "max_age_seconds": 86400,
                        }
                    ],
                    "evidence": [json.loads(item.model_dump_json(exclude_none=True))],
                }
            )
        )
    )
    assert stale.execution_status == "ok"
    assert stale.decision == "abstained"
    assert "STALE_EVIDENCE" in stale.criteria[0].reason_codes
