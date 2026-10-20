"""F3 test-results collector (NIT-019, kind ``junit``).

Reads test-report files from a glob and produces ONE aggregated
``external_api`` observation under ``/tests``: total, passed, failed, errors,
skipped, failed_ids[] (capped), report_paths[], report_mtime_max. Supported
formats: JUnit XML (pytest, jest-junit, vitest, Maven Surefire) and
pytest-json-report. Detection is by content: leading ``<`` means XML,
otherwise JSON.

Safety: stdlib only. XML is parsed with xml.etree (expat) AFTER the raw bytes
are scanned and rejected on any DOCTYPE or ENTITY declaration (the ADR-014
amendment: no defusedxml; no DTDs means no entity expansion at all). Files
are read once, capped per-file by ``max_raw_bytes``; more than
``max_list_items`` matched files is an OUTPUT_TOO_LARGE error, never silent
truncation. A malformed file becomes COLLECTOR_EXCEPTION; an empty match set
is an honest empty success (no evidence, no error), so the verifier abstains.

Freshness: report files older than ``turn_start`` (the hook provides it) or
than ``max_age_seconds`` are ineligible and excluded from the aggregation; if
nothing remains, the result is the same empty success. The observation's
``captured_at`` is the newest eligible report mtime, so the v0.1 policy can
also stale-gate the evidence itself (STALE_EVIDENCE) through a criterion's
``max_age_seconds``.

Errors become structured results, never failures; the collector is read-only
and never executes anything found in a report.
"""

from __future__ import annotations

import hashlib
import json
import time
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

from pydantic import Field, field_validator

from nitelos import __version__
from nitelos.collect import (
    CollectionResult,
    CollectorCapabilities,
    CollectorConfig,
    CollectorError,
    CollectorErrorCode,
    ProvenanceRecord,
)
from nitelos.schemas import Evidence as _EvidenceFactory
from nitelos.schemas import UTCDateTime

__all__ = ["COLLECTOR", "TestResultsCollector", "TestResultsConfig"]


class TestResultsConfig(CollectorConfig):
    """Kind config: where the reports are and how fresh they must be."""

    report_root: Path
    report_glob: str = Field(min_length=1, max_length=256)
    turn_start: UTCDateTime | None = None
    max_age_seconds: int | None = Field(default=None, ge=0, le=86400)

    @field_validator("report_glob")
    @classmethod
    def _glob_must_be_relative(cls, value: str) -> str:
        drive = len(value) > 1 and value[1] == ":" and value[0].isalpha()
        if (
            PureWindowsPath(value).is_absolute()
            or PurePosixPath(value).is_absolute()
            or value.startswith(("/", "\\"))
            or drive
            or ".." in PurePosixPath(value.replace("\\", "/")).parts
        ):
            raise ValueError("report_glob must be a relative pattern without parent refs")
        return value


def _case_id(attrs: dict[str, str], index: int) -> str:
    classname = attrs.get("classname", "")
    name = attrs.get("name", "")
    if classname and name:
        return f"{classname}::{name}"
    return name or classname or f"case-{index}"


def _int_attr(attrs: dict[str, str], key: str, fallback: int) -> int:
    raw = attrs.get(key)
    if raw is None:
        return fallback
    return int(raw.strip())


def _parse_junit_xml(raw: bytes) -> dict[str, Any]:
    root = ET.fromstring(raw)  # noqa: S314 - ADR-014 amendment: DOCTYPE/ENTITY bytes are rejected before this line; defusedxml is deliberately not a dependency
    if root.tag == "testsuite":
        suites: list[ET.Element] = [root]
    else:
        suites = list(root.iter("testsuite"))
        if not suites and root.tag == "testsuites":
            suites = [root]  # bare wrapper carrying counts and cases directly
    total = failed = errors = skipped = 0
    failed_ids: list[str] = []
    index = 0
    for suite in suites:
        cases = list(suite.findall("testcase"))
        total += _int_attr(suite.attrib, "tests", len(cases))
        failed += _int_attr(suite.attrib, "failures", 0)
        errors += _int_attr(suite.attrib, "errors", 0)
        skipped += _int_attr(suite.attrib, "skipped", 0)
        for case in cases:
            index += 1
            if case.find("failure") is not None or case.find("error") is not None:
                failed_ids.append(_case_id(case.attrib, index))
    return {
        "total": total,
        "failed": failed,
        "errors": errors,
        "skipped": skipped,
        "failed_ids": failed_ids,
    }


def _parse_pytest_json(document: Any) -> dict[str, Any]:
    if not isinstance(document, dict):
        raise ValueError("pytest-json-report root must be an object")
    summary = document.get("summary")
    tests = document.get("tests", [])
    if isinstance(summary, dict):
        counts = {key: int(summary.get(key, 0)) for key in ("failed", "error", "skipped")}
        total = int(summary.get("total", len(tests)))
    else:
        outcomes = [str(t.get("outcome", "")) for t in tests if isinstance(t, dict)]
        counts = {
            "failed": outcomes.count("failed"),
            "error": outcomes.count("error"),
            "skipped": outcomes.count("skipped") + outcomes.count("xfailed"),
        }
        total = len(outcomes)
    failed_ids = [
        str(t.get("nodeid", f"case-{i}"))
        for i, t in enumerate(tests)
        if isinstance(t, dict) and str(t.get("outcome", "")) in ("failed", "error")
    ]
    return {
        "total": total,
        "failed": counts["failed"],
        "errors": counts["error"],
        "skipped": counts["skipped"],
        "failed_ids": failed_ids,
    }


class TestResultsCollector:
    """The ``junit`` collector instance (protocol-shaped, no registry)."""

    id = "nitelos-junit"
    version = __version__
    capabilities = CollectorCapabilities(evidence_kinds=("observation",))
    config_model = TestResultsConfig

    def collect(self, config: CollectorConfig) -> CollectionResult:
        cfg = (
            config
            if isinstance(config, TestResultsConfig)
            else TestResultsConfig.model_validate(config.model_dump())
        )
        if not cfg.report_root.is_dir():
            raise CollectorError(CollectorErrorCode.CONFIG_INVALID)
        pattern = Path(cfg.report_glob)
        if pattern.is_absolute() or ".." in pattern.parts:
            raise CollectorError(CollectorErrorCode.CONFIG_INVALID)
        files = sorted(
            (p for p in cfg.report_root.glob(cfg.report_glob) if p.is_file()),
            key=lambda p: p.relative_to(cfg.report_root).as_posix(),
        )
        if len(files) > cfg.limits.max_list_items:
            raise CollectorError(CollectorErrorCode.OUTPUT_TOO_LARGE)

        now = time.time()
        eligible: list[tuple[Path, bytes, float]] = []
        for path in files:
            raw = path.read_bytes()
            if len(raw) > cfg.limits.max_raw_bytes:
                raise CollectorError(CollectorErrorCode.OUTPUT_TOO_LARGE)
            mtime = path.stat().st_mtime
            if cfg.turn_start is not None and mtime < cfg.turn_start.timestamp():
                continue
            if cfg.max_age_seconds is not None and now - mtime > cfg.max_age_seconds:
                continue
            eligible.append((path, raw, mtime))
        if not eligible:
            return CollectionResult(collector_id=self.id, collector_version=self.version)

        total = failed = errors = skipped = 0
        failed_ids: list[str] = []
        for _path, raw, _mtime in eligible:
            if b"<!DOCTYPE" in raw or b"<!ENTITY" in raw:
                raise ValueError("XML with DOCTYPE or ENTITY declarations is rejected")
            if raw.lstrip()[:1] == b"<":
                parsed = _parse_junit_xml(raw)
            else:
                parsed = _parse_pytest_json(json.loads(raw))
            total += parsed["total"]
            failed += parsed["failed"]
            errors += parsed["errors"]
            skipped += parsed["skipped"]
            failed_ids.extend(parsed["failed_ids"])
        passed = total - failed - errors - skipped
        if passed < 0:
            raise ValueError("inconsistent report counts: passed would be negative")
        mtime_max = max(m for _p, _r, m in eligible)
        captured_at = datetime.fromtimestamp(mtime_max, tz=UTC)
        data = {
            "total": total,
            "passed": passed,
            "failed": failed,
            "errors": errors,
            "skipped": skipped,
            "failed_ids": failed_ids[: cfg.limits.max_list_items],
            "report_paths": [p.relative_to(cfg.report_root).as_posix() for p, _r, _m in eligible],
            "report_mtime_max": captured_at.isoformat().replace("+00:00", "Z"),
        }
        item = _EvidenceFactory.observation(
            id=cfg.evidence_id,
            sequence=cfg.sequence_start,
            captured_at=captured_at,
            checkpoint_id=cfg.checkpoint_id,
            source_id=self.id,
            subject=cfg.subject,
            phase="final",
            channel="external_api",
            data=data,
        )
        blob = b"".join(raw for _p, raw, _m in eligible)
        record = ProvenanceRecord(
            evidence_id=item.id,
            collector_id=self.id,
            collector_version=self.version,
            source="test report files (JUnit XML / pytest-json-report)",
            invocation=f"glob {cfg.report_glob} under report_root ({len(eligible)} file(s))",
            captured_at=captured_at,
            subject=cfg.subject,
            sha256=hashlib.sha256(blob).hexdigest(),
            raw_bytes=len(blob),
            normalized_bytes=0,
        )
        return CollectionResult(
            collector_id=self.id,
            collector_version=self.version,
            evidence=(item,),
            provenance=(record,),
        )


COLLECTOR = TestResultsCollector()
