"""Reproducible sequential evaluation runner (NIT-012).

Authority: docs/implementation/nit-012-runner-design.md (readings A1-A7), doc 06
(manifest and runner contract, metrics, reporting), doc 07 (SEC-07 path defenses;
evaluation writes only to a user-selected new directory), doc 12 (commands, EVAL
family, exit codes). Everything here is offline and sequential: one case at a time,
no retries, no resume; per-case input/backend errors are persisted results and never
abort the run; infrastructure failures write an explicit incomplete report and raise
:class:`RunnerError` (kind ``infra``), which the CLI maps to exit 3. Configuration
errors (invalid manifest, existing output directory, backend misuse) raise
``RunnerError`` (kind ``config``; exit 2).

Oracle separation (EVAL-04): backend case data (request + artifact bytes + per-case
bindings) and oracle records are distinct types with distinct loaders; oracles are
loaded only in the post-inference metrics phase and their content never reaches the
verifier factory, a backend, or the per-case report. The oracle triple rule from
decisions.md is enforced (an ``ok`` expectation requires a decision; an error-status
expectation requires null).

This module stays numpy/scipy-free: metrics come from ``nitelos.evaluation.metrics``
(pure), so importing the runner never pulls the eval extra's heavy dependencies.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from nitelos import __version__
from nitelos._json import JsonError, parse_json
from nitelos.evaluation.metrics import CaseRecord, compute_metrics
from nitelos.policy import TrustBinding, VerificationPolicy, parse_policy, policy_hash
from nitelos.schemas import (
    Decision,
    ExecutionStatus,
    VerificationRequest,
    canonical_json,
    parse_request,
)

__all__ = [
    "BackendCaseData",
    "ConfigError",
    "InfraError",
    "LoadedManifest",
    "OracleRecord",
    "RunSummary",
    "RunnerError",
    "compare_reports",
    "evaluate",
    "load_evaluation_manifest",
    "main",
    "safe_relative_path",
]


MAX_MANIFEST_BYTES = 4 * 1024 * 1024
MAX_CASES = 10_000
_MAX_JSON_DEPTH = 8  # manifests are shallow; requests keep their own bound
_DEVICE_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *{f"COM{i}" for i in range(1, 10)},
    *{f"LPT{i}" for i in range(1, 9)},
}


class RunnerError(Exception):
    """Runner failure with a safe message; ``kind`` is 'config' or 'infra'."""


class ConfigError(RunnerError):
    """Invalid manifest/config (CLI exit 2)."""


class InfraError(RunnerError):
    """Infrastructure failure or incomplete run (CLI exit 3)."""


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# ---------------------------------------------------------------------------
# safe path loading (SEC-07)
# ---------------------------------------------------------------------------


def safe_relative_path(root: Path, relative: str) -> Path:
    """Validate RELATIVE under ROOT (string rules + realpath confinement).

    Rejects empty paths, NUL bytes, backslashes (which also kills UNC/``\\\\?\\``
    and drive-letter forms), absolute POSIX paths, any ``..`` component, colons
    (alternate data streams), Windows-reserved characters, components ending in
    dot/space, device names (CON, NUL.bin, com1.log, ...), and anything that
    resolves outside ROOT via symlink/junction/reparse-point resolution.
    """
    root = Path(root)
    if not relative or "\x00" in relative or "\\" in relative:
        raise ConfigError("path not allowed: empty, NUL byte or backslash")
    probe = relative.replace("/", "\x00").split("\x00")
    if relative.startswith("/") or relative.startswith("//"):
        raise ConfigError("path not allowed: absolute path")
    if _looks_like_drive(relative):
        raise ConfigError("path not allowed: drive or UNC path")
    for component in probe:
        if component in ("", ".", ".."):
            if component == "..":
                raise ConfigError("path not allowed: traversal")
            continue
        if ":" in component:
            raise ConfigError("path not allowed: colon (alternate data stream)")
        for ch in component:
            if ch in '<>|"*?':
                raise ConfigError("path not allowed: reserved character")
        if component.endswith(".") or component.endswith(" "):
            raise ConfigError("path not allowed: trailing dot or space")
        stem = component.split(".")[0].upper()
        if stem in _DEVICE_NAMES:
            raise ConfigError("path not allowed: device name")
    resolved_root = Path(os.path.realpath(root))
    resolved = Path(os.path.realpath(root / relative))
    if resolved != resolved_root and resolved_root not in resolved.parents:
        raise ConfigError("path not allowed: escapes the artifact root via a link")
    return resolved


def _looks_like_drive(relative: str) -> bool:
    return len(relative) >= 2 and relative[1] == ":" and relative[0].isalpha()


# ---------------------------------------------------------------------------
# manifest loading (A4: extra=forbid semantics via explicit field checks)
# ---------------------------------------------------------------------------

_MANIFEST_FIELDS = frozenset(
    {
        "schema_version",
        "benchmark_id",
        "benchmark_version",
        "split",
        "evidence_view",
        "seed",
        "policy",
        "cases",
        "provenance",
        "configuration_fingerprint",
        "expected_count",
    }
)
_CASE_FIELDS = frozenset({"case_id", "group_id", "primary_scenario", "request", "artifacts", "oracle"})
_ALLOWED_VIEWS = ("assertion", "visual")
_ALLOWED_SPLITS = ("dev", "test")


@dataclass(frozen=True)
class LoadedManifest:
    """A validated manifest bound to its resolved artifact root."""

    path: Path
    root: Path
    raw: dict[str, Any]

    @property
    def cases(self) -> list[dict[str, Any]]:
        cases: list[dict[str, Any]] = self.raw["cases"]
        return cases

    @property
    def policy(self) -> VerificationPolicy:
        policy = self.raw["policy"]
        return parse_policy({key: value for key, value in policy.items() if key != "hash"})

    @property
    def split(self) -> str:
        split: str = self.raw["split"]
        return split

    @property
    def evidence_view(self) -> str:
        view: str = self.raw["evidence_view"]
        return view


@dataclass(frozen=True)
class BackendCaseData:
    """What the verifier factory receives for one case (no oracle data)."""

    case: dict[str, Any]
    request: VerificationRequest
    artifacts: dict[str, bytes]
    bindings: tuple[TrustBinding, ...]


@dataclass(frozen=True)
class OracleRecord:
    """Post-inference oracle data for one case (never sent to a backend)."""

    case_id: str
    raw: dict[str, Any]


def _load_json_file(path: Path, *, limit: int, label: str) -> Any:
    try:
        data = path.read_bytes()
    except OSError as error:
        raise InfraError(f"{label} could not be read") from error
    if len(data) > limit:
        raise ConfigError(f"{label} exceeds its size limit")
    try:
        return parse_json(data.decode("utf-8"), max_depth=_MAX_JSON_DEPTH)
    except (UnicodeDecodeError, JsonError) as error:
        raise ConfigError(f"{label} is not valid strict JSON") from error


def load_evaluation_manifest(path: Path, artifacts_root: Path) -> LoadedManifest:
    """Load and validate an EvaluationManifest (schema 1) bound to ARTIFACTS_ROOT."""
    path = Path(path)
    raw = _load_json_file(path, limit=MAX_MANIFEST_BYTES, label="manifest")
    if not isinstance(raw, dict):
        raise ConfigError("manifest must be a JSON object")
    for key in raw:
        if key not in _MANIFEST_FIELDS:
            raise ConfigError(f"manifest contains an unknown field: {key}")
    if raw.get("schema_version") != "1":
        raise ConfigError("manifest schema_version must be '1'")
    if raw.get("split") not in _ALLOWED_SPLITS:
        raise ConfigError("manifest split must be dev or test")
    if raw.get("evidence_view") not in _ALLOWED_VIEWS:
        raise ConfigError("manifest evidence_view must be assertion or visual")
    cases = raw.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ConfigError("manifest cases must be a nonempty list")
    if len(cases) > MAX_CASES:
        raise ConfigError("manifest exceeds the case limit")
    if raw.get("expected_count") != len(cases):
        raise ConfigError(f"manifest expected_count does not match the case count ({len(cases)})")
    seen: set[str] = set()
    for case in cases:
        if not isinstance(case, dict):
            raise ConfigError("manifest case entries must be objects")
        for key in case:
            if key not in _CASE_FIELDS:
                raise ConfigError(f"manifest case contains an unknown field: {key}")
        case_id = case.get("case_id")
        if not isinstance(case_id, str) or not case_id or case_id in seen:
            raise ConfigError("manifest case ids must be unique nonempty strings")
        seen.add(case_id)
        for field in ("request", "oracle"):
            value = case.get(field)
            if not isinstance(value, str):
                raise ConfigError(f"manifest case {field} must be a relative path string")
            safe_relative_path(artifacts_root, value)
        for artifact in case.get("artifacts", []):
            if not isinstance(artifact, dict) or set(artifact) != {"id", "path", "sha256"}:
                raise ConfigError("manifest artifact entries need exactly id, path and sha256")
            safe_relative_path(artifacts_root, artifact["path"])
    policy = raw.get("policy")
    if not isinstance(policy, dict) or set(policy) != {"id", "version", "allow_model_inference", "hash"}:
        raise ConfigError("manifest policy must carry exactly id, version, allow_model_inference and hash")
    policy_without_hash = {key: value for key, value in policy.items() if key != "hash"}
    try:
        parsed_policy = parse_policy(policy_without_hash)
    except RunnerError as error:
        raise ConfigError("manifest policy is not a valid policy") from error
    if policy["hash"] != policy_hash(parsed_policy):
        raise ConfigError("manifest policy hash does not match the declared policy")
    return LoadedManifest(path=path, root=Path(artifacts_root), raw=raw)


def _load_collector(root: Path) -> list[dict[str, Any]]:
    raw = _load_json_file(
        root / "fixture-collector.json", limit=MAX_MANIFEST_BYTES, label="fixture collector"
    )
    if not isinstance(raw, dict) or raw.get("collector_id") != "fixture-collector-v1":
        raise ConfigError("fixture collector is missing or has the wrong collector id")
    bindings = raw.get("bindings")
    if not isinstance(bindings, list):
        raise ConfigError("fixture collector bindings must be a list")
    for entry in bindings:
        if not isinstance(entry, dict) or set(entry) != {
            "evidence_id",
            "sha256",
            "source_id",
            "subject",
            "checkpoint_id",
        }:
            raise ConfigError("fixture collector entries have the wrong shape")
    return bindings


# ---------------------------------------------------------------------------
# evaluate
# ---------------------------------------------------------------------------


class VerifierFactory(Protocol):
    """Builds one verifier per case from backend case data (never oracle data)."""

    def __call__(
        self,
        case_id: str,
        request: VerificationRequest,
        artifacts: dict[str, bytes],
        bindings: tuple[TrustBinding, ...],
    ) -> Any: ...


@dataclass(frozen=True)
class RunSummary:
    """Outcome of one evaluate() call."""

    status: str  # "complete" | "incomplete"
    scheduled: int
    completed_count: int
    ok_count: int
    error_count: int
    output_dir: Path


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _now_utc() -> str:
    return datetime.now(UTC).isoformat()


def _bindings_for(collector: list[dict[str, Any]], request: VerificationRequest) -> tuple[TrustBinding, ...]:
    evidence_ids = {item.id for item in request.evidence}
    return tuple(
        TrustBinding(
            evidence_id=entry["evidence_id"],
            sha256=entry["sha256"],
            source_id=entry["source_id"],
            subject=entry["subject"],
            checkpoint_id=entry["checkpoint_id"],
        )
        for entry in collector
        if entry["evidence_id"] in evidence_ids
    )


def _peak_rss_bytes() -> tuple[int | None, str]:
    platform = sys.platform
    if platform.startswith("linux"):
        import resource  # noqa: PLC0415 - POSIX-only module, imported where it exists
        from types import ModuleType  # noqa: PLC0415 - pairs with the resource import

        posix_resource: ModuleType = resource
        getrusage = getattr(posix_resource, "getrusage", None)
        if getrusage is None:  # pragma: no cover - exotic POSIX without getrusage
            return None, "ru_maxrss_unavailable"
        usage = getrusage(resource.RUSAGE_SELF)  # type: ignore[attr-defined, unused-ignore]
        return usage.ru_maxrss * 1024, "ru_maxrss"
    if platform == "win32":
        # GlobalMemoryStatusEx reports system-wide counters, not this process's
        # peak; the honest v0.1 answer on Windows is null-with-reason
        return None, "peak_rss_unavailable_on_windows"
    return None, "peak_rss_unavailable"  # pragma: no cover - linux/win32 handled above


def _fail_incomplete(  # noqa: PLR0917 - internal failure writer, bundling would hurt clarity
    output_dir: Path,
    run_id: str,
    manifest: LoadedManifest,
    rows: list[dict[str, Any]],
    started: float,
    reason: str,
) -> None:
    run_path = output_dir / "run.json"
    try:
        run = json.loads(run_path.read_text(encoding="utf-8")) if run_path.exists() else {}
    except OSError:
        run = {}
    run.update(
        {
            "run_id": run_id,
            "status": "incomplete",
            "scheduled": len(manifest.cases),
            "completed": len(rows),
            "incomplete_reason": reason,
            "finished_at": _now_utc(),
            "elapsed_ms": round((time.perf_counter() - started) * 1000.0, 3),
        }
    )
    _write_json(run_path, run)


def evaluate(
    manifest: LoadedManifest,
    verifier_factory: VerifierFactory,
    output_dir: Path,
) -> RunSummary:
    """Run every scheduled case sequentially into a NEW OUTPUT_DIR.

    Writes run.json, one cases.jsonl line per completed case (flushed per line),
    metrics.json after the post-inference oracle phase, and the atomic COMPLETE
    marker. Refuses an existing output directory (no overwrite, no resume).
    Per-case input/backend errors become result rows; infrastructure failures
    write an incomplete report and raise InfraError.
    """
    output_dir = Path(output_dir)
    if output_dir.exists():
        raise ConfigError(f"output directory already exists: {output_dir.name}")
    output_dir.mkdir(parents=True)
    run_id = str(uuid.uuid4())
    started = time.perf_counter()
    run_meta = {
        "run_id": run_id,
        "status": "running",
        "benchmark_id": manifest.raw["benchmark_id"],
        "benchmark_version": manifest.raw["benchmark_version"],
        "split": manifest.split,
        "evidence_view": manifest.evidence_view,
        "manifest_path": manifest.path.name,
        "manifest_sha256": _sha(manifest.path.read_bytes()),
        "scheduled": len(manifest.cases),
        "completed": 0,
        "started_at": _now_utc(),
        "package_version": __version__,
        "policy_hash": policy_hash(manifest.policy),
        "configuration_fingerprint": manifest.raw["configuration_fingerprint"],
    }
    _write_json(output_dir / "run.json", run_meta)
    rows: list[dict[str, Any]] = []
    results: list[Any] = []
    cases_lines = output_dir / "cases.jsonl"
    try:
        collector = _load_collector(manifest.root)
    except ConfigError as error:
        _fail_incomplete(output_dir, run_id, manifest, rows, started, str(error))
        raise InfraError(f"infrastructure failure: {error}") from error
    with cases_lines.open("w", encoding="utf-8") as sink:
        for case in manifest.cases:
            try:
                row, result = _run_case(manifest, case, collector, verifier_factory, run_id)
            except InfraError as error:
                sink.flush()
                os.fsync(sink.fileno())
                _fail_incomplete(output_dir, run_id, manifest, rows, started, str(error))
                raise
            rows.append(row)
            results.append(result)
            sink.write(json.dumps(row, sort_keys=True) + "\n")
            sink.flush()
            os.fsync(sink.fileno())
    # post-inference phase: oracle loading, triple validation, metrics
    try:
        oracles = _load_oracles(manifest)
        metrics_doc = _build_metrics(manifest, rows, results, oracles, started)
    except (InfraError, ConfigError) as error:
        _fail_incomplete(output_dir, run_id, manifest, rows, started, str(error))
        raise InfraError(f"infrastructure failure: {error}") from error
    _write_json(output_dir / "metrics.json", metrics_doc)
    elapsed_ms = round((time.perf_counter() - started) * 1000.0, 3)
    run_meta.update(
        {
            "status": "complete",
            "completed": len(rows),
            "finished_at": _now_utc(),
            "elapsed_ms": elapsed_ms,
            "peak_rss_bytes": metrics_doc["run_level"]["peak_rss_bytes"],
        }
    )
    _write_json(output_dir / "run.json", run_meta)
    marker = output_dir / "COMPLETE"
    tmp = output_dir / ".COMPLETE.tmp"
    tmp.write_text(f"{run_id}\n", encoding="utf-8")
    os.replace(tmp, marker)
    ok_count = sum(1 for row in rows if row["execution_status"] == "ok")
    return RunSummary(
        status="complete",
        scheduled=len(manifest.cases),
        completed_count=len(rows),
        ok_count=ok_count,
        error_count=len(rows) - ok_count,
        output_dir=output_dir,
    )


def _run_case(
    manifest: LoadedManifest,
    case: dict[str, Any],
    collector: list[dict[str, Any]],
    verifier_factory: VerifierFactory,
    run_id: str = "",
) -> tuple[dict[str, Any], Any]:
    case_id = case["case_id"]
    request_path = safe_relative_path(manifest.root, case["request"])
    try:
        request_bytes = request_path.read_bytes()
    except OSError as error:
        raise InfraError(f"infrastructure failure: request for {case_id} could not be read") from error
    row_base = {
        "run_id": run_id,
        "case_id": case_id,
        "group_id": case.get("group_id", ""),
        "primary_scenario": case.get("primary_scenario", ""),
        "request_hash": _sha(request_bytes),
    }
    try:
        request = parse_request(request_bytes)
    except Exception as error:  # noqa: BLE001 - per-case input error, coded below
        del error
        return (
            {
                **row_base,
                "execution_status": "input_error",
                "decision": None,
                "reason_codes": ["INVALID_SCHEMA"],
                "criterion_count": 0,
                "error_code": "INVALID_SCHEMA",
                "duration_ms": 0.0,
                "model_invoked": False,
                "backend_id": "",
                "trust_fingerprint": "",
                "evidence_hash": "",
            },
            None,
        )
    artifacts: dict[str, bytes] = {}
    for artifact in case.get("artifacts", []):
        artifact_path = safe_relative_path(manifest.root, artifact["path"])
        try:
            data = artifact_path.read_bytes()
        except OSError as error:
            raise InfraError(f"infrastructure failure: artifact for {case_id} could not be read") from error
        if _sha(data) != artifact["sha256"]:
            raise InfraError(f"infrastructure failure: artifact digest mismatch for {case_id}")
        artifacts[artifact["id"]] = data
    bindings = _bindings_for(collector, request)
    started = time.perf_counter()
    try:
        verifier = verifier_factory(case_id, request, artifacts, bindings)  # infra on failure
    except (KeyboardInterrupt, SystemExit):
        raise
    except Exception as error:
        raise InfraError(f"infrastructure failure: verifier for {case_id} could not be built") from error
    try:
        result = verifier.verify(request, artifacts=artifacts)
    except (KeyboardInterrupt, SystemExit):
        raise
    except Exception:  # noqa: BLE001 - any verifier failure is a per-case backend error
        return (
            {
                **row_base,
                "execution_status": "backend_error",
                "decision": None,
                "reason_codes": ["BACKEND_EXCEPTION"],
                "criterion_count": 0,
                "error_code": "BACKEND_EXCEPTION",
                "duration_ms": round((time.perf_counter() - started) * 1000.0, 3),
                "model_invoked": False,
                "backend_id": "",
                "trust_fingerprint": _trust_fingerprint(bindings),
                "evidence_hash": _evidence_hash(request),
            },
            None,
        )
    duration_ms = round((time.perf_counter() - started) * 1000.0, 3)
    model_invoked = any(
        getattr(criterion_result, "basis", None) == "model_inferred" for criterion_result in result.criteria
    )
    failure = result.error
    return (
        {
            **row_base,
            "execution_status": result.execution_status.value,
            "decision": result.decision.value if result.decision is not None else None,
            "reason_codes": list(result.reason_codes),
            "criterion_count": len(result.criteria),
            "error_code": failure.code.value if failure is not None else None,
            "duration_ms": duration_ms,
            "model_invoked": model_invoked,
            "backend_id": result.diagnostics.backend.id,
            "trust_fingerprint": _trust_fingerprint(bindings),
            "evidence_hash": _evidence_hash(request),
        },
        result,
    )


def _trust_fingerprint(bindings: tuple[TrustBinding, ...]) -> str:
    if not bindings:
        return ""
    return _sha(
        canonical_json(
            [
                {
                    "evidence_id": binding.evidence_id,
                    "sha256": binding.sha256,
                    "source_id": binding.source_id,
                    "subject": dict(binding.subject),
                    "checkpoint_id": binding.checkpoint_id,
                }
                for binding in bindings
            ]
        ).encode("utf-8")
    )


def _evidence_hash(request: VerificationRequest) -> str:
    return _sha(
        canonical_json(
            [
                {
                    "evidence_id": item.id,
                    "sha256": item.sha256,
                    "artifact_id": getattr(item, "artifact_id", None),
                }
                for item in request.evidence
            ]
        ).encode("utf-8")
    )


# ---------------------------------------------------------------------------
# post-inference oracle phase
# ---------------------------------------------------------------------------


def _load_oracles(manifest: LoadedManifest) -> dict[str, OracleRecord]:
    oracles: dict[str, OracleRecord] = {}
    for case in manifest.cases:
        path = safe_relative_path(manifest.root, case["oracle"])
        try:
            raw_bytes = path.read_bytes()
        except OSError as error:
            raise InfraError(
                f"infrastructure failure: oracle for {case['case_id']} could not be read"
            ) from error
        try:
            raw = json.loads(raw_bytes.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ConfigError(f"oracle for {case['case_id']} is not valid JSON") from error
        if not isinstance(raw, dict) or raw.get("case_id") != case["case_id"]:
            raise ConfigError(f"oracle for {case['case_id']} has the wrong case id")
        _validate_oracle_triple(raw, case["case_id"])
        oracles[case["case_id"]] = OracleRecord(case_id=case["case_id"], raw=raw)
    return oracles


def _validate_oracle_triple(raw: dict[str, Any], case_id: str) -> None:
    expected = raw.get("expected")
    if not isinstance(expected, dict):
        raise ConfigError(f"oracle for {case_id} has no expected map")
    for view in ("assertion", "visual"):
        entry = expected.get(view)
        if not isinstance(entry, dict) or "decision" not in entry:
            raise ConfigError(f"oracle for {case_id} is missing an expected decision")
        decision = entry["decision"]
        if decision not in ("success", "failure", "abstained"):
            raise ConfigError(
                f"oracle for {case_id}: an ok expectation requires a decision "
                f"(got {decision!r}); an error-status expectation must be null"
            )


def _build_metrics(
    manifest: LoadedManifest,
    rows: list[dict[str, Any]],
    results: list[Any],
    oracles: dict[str, OracleRecord],
    started: float,
) -> dict[str, Any]:
    view = manifest.evidence_view
    records: list[CaseRecord] = []
    cold_seen = False
    for row, _result in zip(rows, results, strict=True):
        oracle = oracles[row["case_id"]]
        expected = oracle.raw["expected"][view]
        model_invoked = bool(row["model_invoked"])
        cold = model_invoked and not cold_seen
        cold_seen = cold_seen or model_invoked
        expected_decision = expected["decision"]
        records.append(
            CaseRecord(
                case_id=row["case_id"],
                group_id=row["group_id"],
                primary_family=row["primary_scenario"],
                scopes=tuple(oracle.raw.get("scope", ())),
                split=manifest.split,
                backend_id=row["backend_id"],
                execution_status=ExecutionStatus(row["execution_status"]),
                decision=Decision(row["decision"]) if row["decision"] is not None else None,
                reason_codes=tuple(row["reason_codes"]),
                expected_execution_status=ExecutionStatus.OK if expected_decision else None,
                expected_decision=Decision(expected_decision) if expected_decision else None,
                expected_reason_codes=tuple(expected.get("reason_codes", ())),
                outcome_truth=oracle.raw["outcome_truth"],
                evidence_sufficiency=oracle.raw["evidence_sufficiency"],
                elapsed_ms=float(row["duration_ms"]),
                model_invoked=model_invoked,
                cold=cold,
            )
        )
    report = compute_metrics(records)
    elapsed_seconds = time.perf_counter() - started
    peak_rss, rss_method = _peak_rss_bytes()
    metrics_doc = {
        "counts": {
            "n": report.counts.n,
            "e": report.counts.e,
            "b": report.counts.b,
            "o": report.counts.o,
            "a": report.counts.a,
            "d": report.counts.d,
        },
        "metrics": [
            {
                "name": record.name,
                "value": record.value,
                "numerator": record.numerator,
                "denominator": record.denominator,
                "undefined_reason": record.undefined_reason,
            }
            for record in report.metrics
        ],
        "latency": {
            "cold": {
                "n": report.latency.cold.n,
                "median": report.latency.cold.median,
                "p95": report.latency.cold.p95,
            },
            "warm": {
                "n": report.latency.warm.n,
                "median": report.latency.warm.median,
                "p95": report.latency.warm.p95,
            },
            "all_attempts": {
                "n": report.latency.all_attempts.n,
                "median": report.latency.all_attempts.median,
                "p95": report.latency.all_attempts.p95,
            },
        },
        "run_level": {
            "cost_amount": None,
            "cost_unavailable_reason": "no_price_source",
            "peak_rss_bytes": peak_rss,
            "peak_rss_method": rss_method,
            "throughput_cases_per_second": (
                round(len(rows) / elapsed_seconds, 6) if elapsed_seconds > 0 else None
            ),
        },
    }
    return metrics_doc


# ---------------------------------------------------------------------------
# compare_reports
# ---------------------------------------------------------------------------


def _read_run(run_dir: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    run = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    rows = [json.loads(line) for line in (run_dir / "cases.jsonl").read_text(encoding="utf-8").splitlines()]
    return run, rows


def compare_reports(run_a: Path, run_b: Path) -> dict[str, Any]:
    """Fingerprint-matched comparison of two completed run directories."""
    run_a, run_b = Path(run_a), Path(run_b)
    meta_a, rows_a = _read_run(run_a)
    meta_b, rows_b = _read_run(run_b)
    if meta_a.get("evidence_view") != meta_b.get("evidence_view"):
        raise ConfigError("comparison refused: different evidence views")
    for key in ("benchmark_id", "split"):
        if meta_a.get(key) != meta_b.get(key):
            raise ConfigError(f"comparison refused: different {key}")
    if meta_a.get("policy_hash") != meta_b.get("policy_hash"):
        raise ConfigError("comparison refused: different policy hashes")
    ids_a = [row["case_id"] for row in rows_a]
    ids_b = [row["case_id"] for row in rows_b]
    if ids_a != ids_b:
        raise ConfigError("comparison refused: different case id sets")
    by_case_a = {row["case_id"]: row for row in rows_a}
    for row in rows_b:
        counterpart = by_case_a[row["case_id"]]
        if counterpart["request_hash"] != row["request_hash"]:
            raise ConfigError("comparison refused: request/evidence bytes differ between runs")
        if counterpart.get("evidence_hash") != row.get("evidence_hash"):
            raise ConfigError("comparison refused: evidence manifests differ between runs")
        if counterpart.get("trust_fingerprint") != row.get("trust_fingerprint"):
            raise ConfigError("comparison refused: trust eligibility differs between runs")
    return {
        "compatible": True,
        "case_count": len(rows_a),
        "case_ids": ids_a,
        "preprocessing": {"matched": True, "delta": []},
        "note": "model/backend versions and timings may differ by design",
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_verifier_factory(
    backend: str, model_dir: str | None, policy: VerificationPolicy
) -> VerifierFactory:
    if backend == "deterministic":
        if model_dir is not None:
            raise ConfigError("--model-dir is only valid with --backend smolvlm")
        from nitelos import DeterministicBackend, Verifier  # noqa: PLC0415 - lazy backend wiring

        def factory(case_id: str, request: Any, artifacts: Any, bindings: Any) -> Any:
            return Verifier(backend=DeterministicBackend(), policy=policy, trust_bindings=bindings)

        return factory
    if backend == "smolvlm":
        import importlib.util  # noqa: PLC0415 - probe of the optional NIT-008 module

        if importlib.util.find_spec("nitelos.backends.smolvlm") is None:
            raise ConfigError(
                "the smolvlm backend is not available in this installation: it arrives with "
                "NIT-008 and the 'local' extra (uv sync --extra local); no model run is faked"
            )
        if model_dir is None:
            raise ConfigError("--model-dir is required with --backend smolvlm")

        def factory(  # pragma: no cover - wired when NIT-008 lands
            case_id: str,
            request: Any,
            artifacts: Any,
            bindings: Any,
        ) -> Any:
            raise NotImplementedError("wired when NIT-008 lands")

        return factory
    raise ConfigError(f"unknown backend: {backend}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m nitelos.evaluation")
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="run a benchmark manifest sequentially")
    run.add_argument("--manifest", required=True)
    run.add_argument("--artifacts", required=True)
    run.add_argument("--output", required=True)
    run.add_argument("--backend", choices=["deterministic", "smolvlm"], default="deterministic")
    run.add_argument("--model-dir", default=None)
    args = parser.parse_args(argv)
    try:
        manifest = load_evaluation_manifest(Path(args.manifest), Path(args.artifacts))
        factory = _build_verifier_factory(args.backend, args.model_dir, manifest.policy)
        summary = evaluate(manifest, factory, Path(args.output))
    except ConfigError as error:
        print(f"configuration error: {error}", file=sys.stderr)
        return 2
    except InfraError as error:
        print(f"infrastructure failure (incomplete run): {error}", file=sys.stderr)
        return 3
    print(
        f"run complete: {summary.scheduled} scheduled, {summary.ok_count} ok, "
        f"{summary.error_count} errors -> {summary.output_dir}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
