"""Frozen-run report validation: RUN-01/RUN-02 (NIT-013 part A).

Authority: docs/implementation/nit-012-runner-design.md (report schemas and the RUN-01
rule list), docs/planning/10 (NIT-013 test-first requirements), doc 06 (oracle data
never appears in reports). Pure and offline: the validator reads a run directory and
either returns a :class:`RunReportSummary` or raises :class:`ValidationError` with a
safe, specific message. It judges STRUCTURE and COHERENCE, never model accuracy.

RUN-01 rules enforced here: required run.json fields (run id, status, benchmark ids,
manifest hash, configuration fingerprint, package version); cases.jsonl row count and
case ids match run.json's scheduled count with no duplicates or foreign ids; decision
is null exactly on error rows; status/marker coherence (``complete`` requires the
COMPLETE marker; a marker with any other status is incoherent); oracle-token leak scan
(declared token names such as ``outcome_truth`` must not appear in any report file);
measurement honesty (a non-null peak RSS requires a recorded method; cost must be null
unless it carries a source — v0.1 runs have none, so a present cost without a reason
is fabricated); and the scheduled = errors + ok identity in metrics.counts.

RUN-02 rules: count identities (from RUN-01) plus per-family completeness — every
expected family present with at least one case. The expected family set defaults to
S01..S15 and can be overridden for partial manifests.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

__all__ = ["RunReportSummary", "ValidationError", "validate_run_report"]

_DEFAULT_FAMILIES = frozenset(f"S{i:02d}" for i in range(1, 16))
_ORACLE_TOKENS = (
    "outcome_truth",
    "evidence_sufficiency",
    "annotation_status",
    "annotators",
    "oracle_source_id",
    "sign_off",
)
_REQUIRED_RUN_FIELDS = (
    "run_id",
    "status",
    "benchmark_id",
    "benchmark_version",
    "manifest_sha256",
    "configuration_fingerprint",
    "package_version",
    "scheduled",
)
_LEGAL_STATUSES = ("complete", "incomplete", "running")
_LEGAL_CASE_STATUSES = ("ok", "input_error", "backend_error")
_HEX64 = re.compile(r"[0-9a-f]{64}")


class ValidationError(ValueError):
    """A report violates the RUN-01/02 contract; the message names the defect safely."""


@dataclass(frozen=True)
class RunReportSummary:
    """What a valid report looks like to reporting layers."""

    run_id: str
    status: str
    benchmark_id: str
    split: str
    evidence_view: str
    scheduled: int
    case_count: int
    ok_count: int
    error_count: int
    families: frozenset[str]

    def __repr__(self) -> str:
        return (
            f"RunReportSummary(run_id={self.run_id!r}, status={self.status!s}, "
            f"scheduled={self.scheduled}, ok={self.ok_count}, errors={self.error_count}, "
            f"families={len(self.families)})"
        )


def _load_json(path: Path) -> dict[str, Any]:
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except OSError as error:
        raise ValidationError(f"report file could not be read: {path.name}") from error
    except json.JSONDecodeError as error:
        raise ValidationError(f"report file is not valid JSON: {path.name}") from error
    if not isinstance(doc, dict):
        raise ValidationError(f"report file must hold a JSON object: {path.name}")
    return doc


def _load_rows(path: Path) -> list[dict[str, Any]]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as error:
        raise ValidationError("cases.jsonl could not be read") from error
    rows: list[dict[str, Any]] = []
    for number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as error:
            raise ValidationError(f"cases.jsonl line {number} is not valid JSON") from error
        if not isinstance(row, dict):
            raise ValidationError(f"cases.jsonl line {number} is not an object")
        rows.append(row)
    return rows


def _check_no_oracle_tokens(name: str, text: str) -> None:
    lowered = text.lower()
    for token in _ORACLE_TOKENS:
        if re.search(rf'"{token}"', lowered):
            raise ValidationError(
                f"oracle data leaked into a model-visible report ({name} contains '{token}')"
            )


def validate_run_report(
    run_dir: Path, *, expected_families: frozenset[str] = _DEFAULT_FAMILIES
) -> RunReportSummary:
    """Validate one run directory (RUN-01 structure/coherence + RUN-02 completeness)."""
    run_dir = Path(run_dir)
    run = _load_json(run_dir / "run.json")
    rows = _load_rows(run_dir / "cases.jsonl")
    metrics = _load_json(run_dir / "metrics.json")

    # --- RUN-01: required fields, hashes, status coherence ---
    for field in _REQUIRED_RUN_FIELDS:
        if field not in run or run[field] is None:
            raise ValidationError(f"run.json is missing the required field '{field}'")
    if run["status"] not in _LEGAL_STATUSES:
        raise ValidationError(f"run.json status is not a legal status: {run['status']!r}")
    for hash_field in ("manifest_sha256", "configuration_fingerprint"):
        if not isinstance(run[hash_field], str) or not _HEX64.fullmatch(run[hash_field]):
            raise ValidationError(f"run.json {hash_field} is not a sha256 hex digest")
    marker = run_dir / "COMPLETE"
    if run["status"] == "complete" and not marker.exists():
        raise ValidationError("status is complete but the COMPLETE marker is missing")
    if run["status"] != "complete" and marker.exists():
        raise ValidationError("the COMPLETE marker exists but the status is not complete")

    # --- RUN-01: case rows ---
    scheduled = run["scheduled"]
    if not isinstance(scheduled, int) or scheduled < 1:
        raise ValidationError("run.json scheduled must be a positive integer")
    if len(rows) != scheduled:
        raise ValidationError(f"case rows ({len(rows)}) do not match the scheduled count ({scheduled})")
    seen: set[str] = set()
    for row in rows:
        case_id = row.get("case_id")
        if not isinstance(case_id, str) or not case_id:
            raise ValidationError("a case row is missing its case_id")
        if case_id in seen:
            raise ValidationError(f"duplicate case id in cases.jsonl: {case_id}")
        seen.add(case_id)
        status = row.get("execution_status")
        if status not in _LEGAL_CASE_STATUSES:
            raise ValidationError(f"case {case_id} has an illegal execution status: {status!r}")
        decision = row.get("decision")
        if status == "ok" and decision is None:
            raise ValidationError(f"ok case {case_id} carries a null decision")
        if status != "ok" and decision is not None:
            raise ValidationError(f"error case {case_id} carries a non-null decision")
        if row.get("run_id") != run["run_id"]:
            raise ValidationError(f"case {case_id} carries a foreign run_id")

    ok_count = sum(1 for row in rows if row["execution_status"] == "ok")
    error_count = len(rows) - ok_count

    # --- RUN-01: oracle-token leak scan over every report file ---
    for path in sorted(p for p in run_dir.iterdir() if p.is_file()):
        _check_no_oracle_tokens(path.name, path.read_text(encoding="utf-8", errors="replace"))

    # --- RUN-01: measurement honesty in metrics.json ---
    run_level = metrics.get("run_level")
    if not isinstance(run_level, dict):
        raise ValidationError("metrics.json has no run_level object")
    peak_rss = run_level.get("peak_rss_bytes")
    peak_method = run_level.get("peak_rss_method")
    if peak_rss is not None and not (isinstance(peak_method, str) and peak_method):
        raise ValidationError("peak_rss_bytes is present without a recorded measurement method")
    cost = run_level.get("cost_amount")
    if cost is not None and not isinstance(run_level.get("cost_source"), str):
        raise ValidationError(
            "cost_amount is present without a price source; v0.1 cost must be null, not zero"
        )

    # --- RUN-01: scheduled = errors + ok identity in metrics.counts ---
    counts = metrics.get("counts")
    if not isinstance(counts, dict):
        raise ValidationError("metrics.json has no counts object")
    reported_n = counts.get("n")
    if reported_n != scheduled or counts.get("e", 0) + counts.get("o", 0) != scheduled:
        raise ValidationError(
            "metrics counts break the scheduled = errors + ok identity "
            f"(n={reported_n!r}, scheduled={scheduled})"
        )
    if counts.get("o") != ok_count or counts.get("e") != error_count:
        raise ValidationError("metrics counts do not match the case rows' ok/error split")

    # --- RUN-02: per-family completeness ---
    families = {row.get("primary_scenario") for row in rows}
    families.discard(None)
    missing = expected_families - families
    if missing:
        raise ValidationError(f"report is missing cases for families: {sorted(missing)}")

    return RunReportSummary(
        run_id=run["run_id"],
        status=run["status"],
        benchmark_id=run["benchmark_id"],
        split=run.get("split", ""),
        evidence_view=run.get("evidence_view", ""),
        scheduled=scheduled,
        case_count=len(rows),
        ok_count=ok_count,
        error_count=error_count,
        families=frozenset(str(f) for f in families),
    )
