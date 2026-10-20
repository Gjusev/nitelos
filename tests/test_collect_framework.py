"""COL-01..08: the collector framework contract (NIT-017, plan section F1).

Authority: docs/planning/17 section F1, ADR-015 (side effects, error codes,
channel/trust), ADR-014 (packaging), docs 05 (trust bindings) and 07 (no
secrets in logs or reprs). Fakes only; no real collector ships in this task.
"""

from __future__ import annotations

import hashlib
import json
import logging
import subprocess
import sys
import time
from collections.abc import Mapping
from datetime import datetime
from typing import Any

import pytest
from pydantic import ValidationError

from _collector_contract import assert_broken_collector_fails, assert_contract
from nitelos import Evidence, Verifier, canonical_json, parse_request
from nitelos.collect import (
    CollectionResult,
    CollectorCapabilities,
    CollectorConfig,
    CollectorError,
    CollectorErrorCode,
    CollectorErrorInfo,
    CollectorLimits,
    ProvenanceRecord,
    cap_list,
    host_trust_bindings,
    run_collector,
)

SENTINEL = "SENTINEL-SENTINEL-d5c1"
SUBJECT = {"repo": "example/app"}
CAPTURED_AT = "2026-10-20T12:00:00Z"


def _config(**over: Any) -> CollectorConfig:
    values: dict[str, Any] = {
        "evidence_id": "obs-1",
        "sequence_start": 0,
        "checkpoint_id": "cp-1",
        "subject": dict(SUBJECT),
    }
    values.update(over)
    return CollectorConfig.model_validate(values)


class _StaticCollector:
    """Fake collector producing one observation from a fixed payload."""

    def __init__(self, data: Mapping[str, object], *, provenance_sha: str | None = None) -> None:
        self.data = data
        self.provenance_sha = provenance_sha  # None: the honest digest; else a lying one

    @property
    def id(self) -> str:
        return "static-fixture"

    @property
    def version(self) -> str:
        return "1.0.0"

    @property
    def capabilities(self) -> CollectorCapabilities:
        return CollectorCapabilities(evidence_kinds=("observation",))

    def collect(self, config: CollectorConfig) -> CollectionResult:
        item = Evidence.observation(
            id=config.evidence_id,
            sequence=config.sequence_start,
            captured_at=CAPTURED_AT,
            checkpoint_id=config.checkpoint_id,
            source_id=self.id,
            subject=config.subject,
            phase="final",
            channel="external_api",
            data=self.data,
        )
        size = len(canonical_json(self.data).encode("utf-8"))
        provenance = ProvenanceRecord(
            evidence_id=item.id,
            collector_id=self.id,
            collector_version=self.version,
            source="static in-memory fixture",
            invocation="static",
            captured_at=item.captured_at,
            subject=config.subject,
            sha256=self.provenance_sha or item.sha256,
            raw_bytes=size,
            normalized_bytes=size,
        )
        return CollectionResult(
            collector_id=self.id,
            collector_version=self.version,
            evidence=(item,),
            provenance=(provenance,),
        )


class _RaisingCollector(_StaticCollector):
    def __init__(self, error: BaseException) -> None:
        super().__init__({"deployed": True})
        self.error = error

    def collect(self, config: CollectorConfig) -> CollectionResult:
        raise self.error


class _SleepyCollector(_StaticCollector):
    def __init__(self, seconds: float) -> None:
        super().__init__({"deployed": True})
        self.seconds = seconds

    def collect(self, config: CollectorConfig) -> CollectionResult:
        time.sleep(self.seconds)
        return super().collect(config)


class _NoProvenanceCollector(_StaticCollector):
    def collect(self, config: CollectorConfig) -> CollectionResult:
        good = super().collect(config)
        return CollectionResult(
            collector_id=good.collector_id,
            collector_version=good.collector_version,
            evidence=good.evidence,
            provenance=(),  # broken: no provenance
        )


class _SelfTrustingCollector(_StaticCollector):
    def collect(self, config: CollectorConfig) -> CollectionResult:
        evidence = Evidence.observation(
            id=config.evidence_id,
            sequence=0,
            captured_at=CAPTURED_AT,
            checkpoint_id=config.checkpoint_id,
            source_id=self.id,
            subject=config.subject,
            phase="final",
            channel="external_api",
            data={"deployed": True},
        )
        return CollectionResult(
            collector_id=self.id,
            collector_version=self.version,
            evidence=(evidence,),
            provenance=(
                ProvenanceRecord(
                    evidence_id=evidence.id,
                    collector_id=self.id,
                    collector_version=self.version,
                    source="static",
                    invocation="static",
                    captured_at=evidence.captured_at,
                    subject=config.subject,
                    sha256=evidence.sha256,
                    raw_bytes=21,
                    normalized_bytes=21,
                ),
            ),
            trusted=True,  # type: ignore[call-arg]  # deliberately broken: self-granted trust
        )


# --------------------------------------------------------------------------
# COL-01: the result model
# --------------------------------------------------------------------------


def test_col01_result_is_frozen_and_extras_rejected() -> None:
    result = _StaticCollector({"deployed": True}).collect(_config())
    with pytest.raises(ValidationError, match="frozen"):
        result.collector_id = "other"  # type: ignore[misc]
    with pytest.raises(ValueError, match="extra"):
        CollectionResult.model_validate(
            {
                "collector_id": "x",
                "collector_version": "1",
                "evidence": [],
                "provenance": [],
                "trusted": True,
            }
        )


def test_col01_exactly_one_provenance_per_evidence() -> None:
    good = _StaticCollector({"deployed": True}).collect(_config())
    assert [p.evidence_id for p in good.provenance] == [e.id for e in good.evidence]
    with pytest.raises(ValueError, match="provenance"):
        CollectionResult(
            collector_id="static-fixture",
            collector_version="1.0.0",
            evidence=good.evidence,
            provenance=(),
        )


def test_col01_failed_result_carries_no_evidence() -> None:
    failed = CollectionResult(
        collector_id="static-fixture",
        collector_version="1.0.0",
        evidence=(),
        provenance=(),
        error=CollectorErrorInfo(code=CollectorErrorCode.TIMEOUT),
    )
    assert failed.error is not None
    assert failed.error.code is CollectorErrorCode.TIMEOUT


def test_col01_provenance_captured_at_must_be_aware_utc() -> None:
    with pytest.raises(ValueError, match="timezone"):
        ProvenanceRecord(
            evidence_id="obs-1",
            collector_id="static-fixture",
            collector_version="1.0.0",
            source="static",
            invocation="static",
            captured_at=datetime(2026, 10, 20, 12, 0, 0),  # naive: rejected
            subject=dict(SUBJECT),
            sha256="a" * 64,
            raw_bytes=1,
            normalized_bytes=1,
        )


# --------------------------------------------------------------------------
# COL-02: error mapping via run_collector
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("error", "expected_code"),
    [
        (CollectorError(CollectorErrorCode.TIMEOUT), CollectorErrorCode.TIMEOUT),
        (CollectorError(CollectorErrorCode.UNAVAILABLE), CollectorErrorCode.UNAVAILABLE),
        (
            CollectorError(CollectorErrorCode.OUTPUT_TOO_LARGE),
            CollectorErrorCode.OUTPUT_TOO_LARGE,
        ),
        (CollectorError(CollectorErrorCode.AUTH_MISSING), CollectorErrorCode.AUTH_MISSING),
        (RuntimeError(f"boom {SENTINEL}"), CollectorErrorCode.EXCEPTION),
    ],
)
def test_col02_each_code_reachable_with_fixed_message(error: BaseException, expected_code: Any) -> None:
    result = run_collector(_RaisingCollector(error), _config())
    assert result.error is not None
    assert result.error.code is expected_code
    assert result.evidence == ()
    assert result.provenance == ()
    assert SENTINEL not in result.error.safe_message  # never exception text
    assert result.error.safe_message  # fixed text per code, always present


def test_col02_invalid_config_mapping_is_config_invalid() -> None:
    result = run_collector(_StaticCollector({"deployed": True}), {"evidence_id": "obs-1", "surprise": 1})
    assert result.error is not None
    assert result.error.code is CollectorErrorCode.CONFIG_INVALID


def test_col02_dev_reraise_reraises_unexpected_exceptions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("NITELOS_DEV_RERAISE", "1")
    with pytest.raises(RuntimeError):
        run_collector(_RaisingCollector(RuntimeError("boom")), _config())


def test_col02_keyboard_interrupt_propagates(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NITELOS_DEV_RERAISE", raising=False)
    with pytest.raises(KeyboardInterrupt):
        run_collector(_RaisingCollector(KeyboardInterrupt()), _config())


# --------------------------------------------------------------------------
# COL-03: caps
# --------------------------------------------------------------------------


def test_col03_observation_over_cap_errors_never_truncates() -> None:
    payload = {"blob": "x" * 200}
    limits = CollectorLimits(max_observation_bytes=64)
    result = run_collector(_StaticCollector(payload), _config(limits=limits))
    assert result.error is not None
    assert result.error.code is CollectorErrorCode.OUTPUT_TOO_LARGE
    assert result.evidence == ()


def test_col03_observation_exactly_at_limit_passes() -> None:
    # canonical form is {"blob":"x"*n} -> 11 + n bytes; build n so it hits 64 exactly
    n = 64 - len('{"blob":""}')
    payload = {"blob": "x" * n}
    result = run_collector(
        _StaticCollector(payload), _config(limits=CollectorLimits(max_observation_bytes=64))
    )
    assert result.error is None
    assert len(result.evidence) == 1


def test_col03_cap_list_returns_explicit_truncated_count() -> None:
    items, truncated = cap_list(list(range(5)), 3)
    assert items == (0, 1, 2)
    assert truncated == 2
    assert cap_list(list(range(2)), 3) == ((0, 1), 0)


def test_col03_limits_configurable_downward() -> None:
    tight = CollectorLimits(timeout_s=0.05, max_raw_bytes=100, max_observation_bytes=10, max_list_items=1)
    assert tight.timeout_s == 0.05
    result = run_collector(_SleepyCollector(0.2), _config(limits=tight))
    assert result.error is not None
    assert result.error.code is CollectorErrorCode.TIMEOUT


# --------------------------------------------------------------------------
# COL-04: redaction
# --------------------------------------------------------------------------


def _redacted_run() -> CollectionResult:
    payload = {
        "deployed": True,
        "visible": "drop-me",
        "GITHUB_TOKEN": SENTINEL,
        "nested": {"Authorization": f"Bearer {SENTINEL}", "db_password": "pw", "keep": 1},
    }
    config = _config(redact_pointers=("/visible",))
    return run_collector(_StaticCollector(payload), config)


def test_col04_pointer_and_default_secret_keys_dropped_at_any_depth() -> None:
    result = _redacted_run()
    assert result.error is None
    (item,) = result.evidence
    data = json.loads(canonical_json(dict(item.data)))  # type: ignore[arg-type]
    assert data == {"deployed": True, "nested": {"keep": 1}}


def test_col04_applied_pointers_recorded_in_provenance() -> None:
    result = _redacted_run()
    (record,) = result.provenance
    assert "/visible" in record.redactions
    assert "/GITHUB_TOKEN" in record.redactions
    assert "/nested/Authorization" in record.redactions
    assert "/nested/db_password" in record.redactions


def test_col04_evidence_digest_is_of_the_redacted_payload() -> None:
    result = _redacted_run()
    (item,) = result.evidence
    redacted_canonical = canonical_json({"deployed": True, "nested": {"keep": 1}})
    assert item.sha256 == hashlib.sha256(redacted_canonical.encode("utf-8")).hexdigest()


def test_col04_sentinel_absent_from_result_and_repr() -> None:
    result = _redacted_run()
    assert SENTINEL not in repr(result)
    assert SENTINEL not in json.dumps([r.model_dump(mode="json") for r in result.provenance])
    assert SENTINEL not in canonical_json(result.evidence[0].model_dump(mode="json"))


# --------------------------------------------------------------------------
# COL-05: trust
# --------------------------------------------------------------------------


def _request_document(result: CollectionResult, *, expected: Any, evidence_ids: list[str]) -> dict[str, Any]:
    return {
        "schema_version": "1",
        "request_id": "req-collect-1",
        "objective": "Deployment really happened",
        "checkpoint_id": "cp-1",
        "as_of": CAPTURED_AT,
        "criteria": [
            {
                "id": "c-deployed",
                "description": "The deployment record reports deployed=true",
                "kind": "assertion",
                "scope": "external",
                "evidence_ids": evidence_ids,
                "subject": dict(SUBJECT),
                "pointer": "/deployed",
                "operator": "equals",
                "expected": expected,
            }
        ],
        "evidence": [item.model_dump(mode="json") for item in result.evidence],
        "metadata": {},
    }


def test_col05_result_carries_no_bindings() -> None:
    run_collector(_StaticCollector({"deployed": True}), _config())  # construction alone proves the shape
    assert "bindings" not in CollectionResult.model_fields
    assert "trust" not in CollectionResult.model_fields


def test_col05_unbound_collected_evidence_abstains_untrusted() -> None:
    result = run_collector(_StaticCollector({"deployed": True}), _config())
    document = _request_document(result, expected=True, evidence_ids=["obs-1"])
    verified = Verifier().verify(parse_request(document))
    assert verified.execution_status.value == "ok"
    assert verified.decision is not None
    assert verified.decision.value == "abstained"
    assert "UNTRUSTED_EXTERNAL" in verified.reason_codes


def test_col05_host_trust_bindings_make_supported_success_and_refuted_failure() -> None:
    result = run_collector(_StaticCollector({"deployed": True}), _config())
    bindings = host_trust_bindings(result)
    assert len(bindings) == 1
    supported = Verifier(trust_bindings=bindings).verify(
        parse_request(_request_document(result, expected=True, evidence_ids=["obs-1"]))
    )
    assert supported.decision is not None
    assert supported.decision.value == "success"
    refuted = Verifier(trust_bindings=bindings).verify(
        parse_request(_request_document(result, expected=False, evidence_ids=["obs-1"]))
    )
    assert refuted.decision is not None
    assert refuted.decision.value == "failure"


def test_col05_collector_failure_abstains_with_missing_evidence() -> None:
    result = run_collector(_RaisingCollector(CollectorError(CollectorErrorCode.UNAVAILABLE)), _config())
    assert result.error is not None
    document = _request_document(result, expected=True, evidence_ids=[])
    verified = Verifier().verify(parse_request(document))
    assert verified.execution_status.value == "ok"
    assert verified.decision is not None
    assert verified.decision.value == "abstained"
    assert "MISSING_EVIDENCE" in verified.reason_codes


# --------------------------------------------------------------------------
# COL-06: safety of reprs and logs
# --------------------------------------------------------------------------


def test_col06_logs_carry_no_raw_values(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.DEBUG, logger="nitelos.collect"):
        result = run_collector(_StaticCollector({"deployed": True, "api_token": SENTINEL}), _config())
    assert result.error is None
    assert SENTINEL not in caplog.text


def test_col06_provenance_repr_is_ids_and_counts_only() -> None:
    result = run_collector(_StaticCollector({"deployed": True}), _config())
    (record,) = result.provenance
    text = repr(record)
    assert "static in-memory fixture" not in text
    assert record.evidence_id in text


# --------------------------------------------------------------------------
# COL-07: the allowlisted subprocess runner
# --------------------------------------------------------------------------


_CHILD_PRINT_ENV = "import os, sys; sys.stdout.write(os.environ.get('NITELOS_TEST_SECRET', 'absent'))"


def _run_allowed(argv: tuple[str, ...], allowlist: tuple[tuple[str, ...], ...], **kwargs: Any) -> Any:
    from nitelos.collect._process import run_allowed

    return run_allowed(
        argv=argv,
        allowlist=allowlist,
        timeout_s=kwargs.pop("timeout_s", 10.0),
        max_raw_bytes=kwargs.pop("max_raw_bytes", 1_048_576),
        **kwargs,
    )


def test_col07_argv_outside_allowlist_rejected_before_start(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[Any] = []

    def _spy(*args: Any, **kwargs: Any) -> None:
        calls.append((args, kwargs))
        raise AssertionError("no process may start for a non-allowlisted argv")

    monkeypatch.setattr(subprocess, "Popen", _spy)
    argv = (sys.executable, "-c", "print('nope')")
    allowlist = ((sys.executable, "-c", "print('yes')"),)
    with pytest.raises(CollectorError) as excinfo:
        _run_allowed(argv, allowlist)
    assert excinfo.value.code is CollectorErrorCode.CONFIG_INVALID
    assert calls == []


def test_col07_child_env_is_scrubbed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NITELOS_TEST_SECRET", "leaked-if-visible")
    argv = (sys.executable, "-c", _CHILD_PRINT_ENV)
    out, _err = _run_allowed(argv, (argv,))
    assert out.decode("utf-8").strip() == "absent"


def test_col07_timeout_maps_to_collector_timeout() -> None:
    argv = (sys.executable, "-c", "import time; time.sleep(5)")
    with pytest.raises(CollectorError) as excinfo:
        _run_allowed(argv, (argv,), timeout_s=0.3)
    assert excinfo.value.code is CollectorErrorCode.TIMEOUT


def test_col07_output_over_cap_maps_to_too_large() -> None:
    argv = (sys.executable, "-c", "print('x' * 100)")
    with pytest.raises(CollectorError) as excinfo:
        _run_allowed(argv, (argv,), max_raw_bytes=10)
    assert excinfo.value.code is CollectorErrorCode.OUTPUT_TOO_LARGE


def test_col07_missing_executable_maps_to_unavailable() -> None:
    argv = ("nitelos-no-such-executable-xyz", "--version")
    with pytest.raises(CollectorError) as excinfo:
        _run_allowed(argv, (argv,))
    assert excinfo.value.code is CollectorErrorCode.UNAVAILABLE


def test_col07_shell_is_never_used(monkeypatch: pytest.MonkeyPatch) -> None:
    real_popen = subprocess.Popen
    seen: dict[str, Any] = {}

    def _spy(args: Any, **kwargs: Any) -> Any:
        seen["args"] = args
        seen["shell"] = kwargs.get("shell")
        return real_popen(args, **kwargs)

    monkeypatch.setattr(subprocess, "Popen", _spy)
    argv = (sys.executable, "-c", "print('ok')")
    out, _ = _run_allowed(argv, (argv,))
    assert seen["args"][0] == sys.executable or str(seen["args"][0]).endswith("python")
    assert seen["shell"] is False
    assert b"ok" in out


# --------------------------------------------------------------------------
# COL-08: the reusable contract suite
# --------------------------------------------------------------------------


def test_col08_contract_suite_passes_for_a_well_formed_collector() -> None:
    assert_contract(_StaticCollector({"deployed": True, "api_token": SENTINEL}), _config())


def test_col08_suite_catches_missing_provenance() -> None:
    assert_broken_collector_fails(_NoProvenanceCollector({"deployed": True}), _config())


def test_col08_suite_catches_self_granted_trust() -> None:
    assert_broken_collector_fails(_SelfTrustingCollector({"deployed": True}), _config())


def test_col08_suite_catches_lying_provenance_digest() -> None:
    lying = _StaticCollector({"deployed": True}, provenance_sha="b" * 64)
    assert_broken_collector_fails(lying, _config())
