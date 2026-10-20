"""COL-01..08: the collector framework contract (NIT-017, plan section F1).

Authority: docs/planning/17 section F1, ADR-015 (side effects, error codes,
channel/trust), ADR-014 (packaging), docs 05 (trust bindings) and 07 (no
secrets in logs or reprs), and the NIT-017 review findings 1-8. Fakes only.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
import subprocess
import sys
import time
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
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
    derive_evidence_id,
    host_trust_bindings,
    run_collector,
)

SENTINEL = "SENTINEL-SECRET-d5c1"
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

    config_model = CollectorConfig

    def __init__(self, data: Mapping[str, object], *, mutate: Mapping[str, Any] | None = None) -> None:
        self.data = data
        self.mutate = mutate or {}

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
        overrides: dict[str, Any] = dict(self.mutate)
        item = Evidence.observation(
            id=config.evidence_id,
            sequence=overrides.pop("sequence", config.sequence_start),
            captured_at=overrides.pop("captured_at", CAPTURED_AT),
            checkpoint_id=overrides.pop("checkpoint_id", config.checkpoint_id),
            source_id=overrides.pop("source_id", self.id),
            subject=overrides.pop("subject", config.subject),
            phase="final",
            channel=overrides.pop("channel", "external_api"),
            data=self.data,
        )
        size = len(canonical_json(self.data).encode("utf-8"))
        provenance = ProvenanceRecord(
            evidence_id=item.id,
            collector_id=overrides.pop("provenance_collector_id", self.id),
            collector_version=overrides.pop("provenance_collector_version", self.version),
            source="static in-memory fixture",
            invocation="static",
            captured_at=overrides.pop("provenance_captured_at", item.captured_at),
            subject=overrides.pop("provenance_subject", item.subject),
            sha256=item.sha256,
            raw_bytes=max(1, size),
            normalized_bytes=size,
        )
        assert not overrides, f"unknown mutation keys: {sorted(overrides)}"
        return CollectionResult(
            collector_id=self.id,
            collector_version=self.version,
            evidence=(item,),
            provenance=(provenance,),
        )


class _RaisingCollector(_StaticCollector):
    def __init__(self, error: BaseException | CollectorErrorInfo) -> None:
        super().__init__({"deployed": True})
        self.error = error

    def collect(self, config: CollectorConfig) -> CollectionResult:
        if isinstance(self.error, CollectorErrorInfo):
            return CollectionResult.model_construct(
                collector_id=self.id,
                collector_version=self.version,
                evidence=(),
                provenance=(),
                error=self.error,
            )
        raise self.error


class _SleepyCollector(_StaticCollector):
    def __init__(self, seconds: float) -> None:
        super().__init__({"deployed": True})
        self.seconds = seconds

    def collect(self, config: CollectorConfig) -> CollectionResult:
        time.sleep(self.seconds)
        return super().collect(config)


class _SubConfig(CollectorConfig):
    """A kind-specific config (NIT-018 shape): one extra required field."""

    repo_path: str


class _SubConfigCollector(_StaticCollector):
    config_model = _SubConfig


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
    assert failed.error.safe_message  # always the fixed text, never empty


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


def test_col01_provenance_raw_bytes_allows_zero() -> None:
    record = ProvenanceRecord(
        evidence_id="obs-1",
        collector_id="static-fixture",
        collector_version="1.0.0",
        source="static",
        invocation="static",
        captured_at=CAPTURED_AT,
        subject=dict(SUBJECT),
        sha256="a" * 64,
        raw_bytes=0,
        normalized_bytes=0,
    )
    assert record.raw_bytes == 0


# --------------------------------------------------------------------------
# COL-02: error mapping via run_collector
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("error", "expected_code"),
    [
        (CollectorError(CollectorErrorCode.TIMEOUT), CollectorErrorCode.TIMEOUT),
        (CollectorError(CollectorErrorCode.UNAVAILABLE), CollectorErrorCode.UNAVAILABLE),
        (CollectorError(CollectorErrorCode.OUTPUT_TOO_LARGE), CollectorErrorCode.OUTPUT_TOO_LARGE),
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


def test_col02_collector_returned_error_is_rebuilt_with_fixed_text() -> None:
    # review finding 5: a collector-returned safe_message must never pass through
    leaky = CollectorErrorInfo.model_construct(
        code=CollectorErrorCode.TIMEOUT, safe_message=f"leak {SENTINEL}"
    )
    result = run_collector(_RaisingCollector(leaky), _config())
    assert result.error is not None
    assert result.error.code is CollectorErrorCode.TIMEOUT
    assert result.error.safe_message == CollectorErrorInfo(code=CollectorErrorCode.TIMEOUT).safe_message
    assert SENTINEL not in result.error.safe_message


def test_col02_dev_reraise_reraises_unexpected_exceptions(monkeypatch: pytest.MonkeyPatch) -> None:
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


def _redacted_run(
    payload: Mapping[str, object] | list[object], pointers: tuple[str, ...] = ()
) -> CollectionResult:
    config = _config(redact_pointers=pointers)
    return run_collector(_StaticCollector(payload), config)


def _data_of(result: CollectionResult) -> Any:
    (item,) = result.evidence
    return json.loads(canonical_json(dict(item.data)))  # type: ignore[arg-type]


def test_col04_pointer_and_default_secret_keys_dropped_at_any_depth() -> None:
    payload = {
        "deployed": True,
        "visible": "drop-me",
        "GITHUB_TOKEN": SENTINEL,
        "nested": {"Authorization": f"Bearer {SENTINEL}", "db_password": "pw", "keep": 1},
    }
    data = _data_of(_redacted_run(payload, ("/visible",)))
    assert data == {"deployed": True, "nested": {"keep": 1}}


def test_col04_user_pointer_deletion_does_not_shift_secret_targets() -> None:
    # review finding 1: deleting items[0] used to shift the secret scan away from items[1]
    data = _data_of(_redacted_run({"items": [{"a": 1}, {"token": SENTINEL}]}, ("/items/0",)))
    assert data == {"items": [{}]}
    assert SENTINEL not in canonical_json(data)


def test_col04_multiple_array_pointer_deletions_keep_correct_elements() -> None:
    # review finding 1: the old code deleted a AND c (index shift); the pointers
    # address elements 0 and 1, so the correct survivors are exactly ["c"]
    data = _data_of(_redacted_run({"l": ["a", "b", "c"]}, ("/l/0", "/l/1")))
    assert data == {"l": ["c"]}


def test_col04_secret_keys_dropped_inside_arrays_of_objects() -> None:
    data = _data_of(_redacted_run({"rows": [{"token": SENTINEL}, {"ok": 1}]}))
    assert data == {"rows": [{}, {"ok": 1}]}


def test_col04_noncanonical_array_tokens_are_not_droppable() -> None:
    # review item 11: "/l/01" is invalid under the evaluator's array grammar
    data = _data_of(_redacted_run({"l": ["a", "b"]}, ("/l/01",)))
    assert data == {"l": ["a", "b"]}


def test_col04_applied_pointers_recorded_in_provenance() -> None:
    result = _redacted_run({"deployed": True, "visible": 1, "GITHUB_TOKEN": SENTINEL}, ("/visible",))
    (record,) = result.provenance
    assert "/visible" in record.redactions
    assert "/GITHUB_TOKEN" in record.redactions


def test_col04_evidence_digest_is_of_the_redacted_payload() -> None:
    result = _redacted_run({"deployed": True, "api_token": SENTINEL})
    (item,) = result.evidence
    (record,) = result.provenance
    redacted_canonical = canonical_json({"deployed": True})
    assert item.sha256 == hashlib.sha256(redacted_canonical.encode("utf-8")).hexdigest()
    assert record.evidence_sha256 == item.sha256


def test_col04_sentinel_absent_from_result_and_repr() -> None:
    result = _redacted_run({"deployed": True, "api_token": SENTINEL})
    assert SENTINEL not in repr(result)
    assert SENTINEL not in json.dumps([r.model_dump(mode="json") for r in result.provenance])
    assert SENTINEL not in canonical_json(result.evidence[0].model_dump(mode="json"))


def test_col04_redact_pointers_from_a_json_mapping_config() -> None:
    # review finding 4: strict python mode rejected JSON arrays in mappings
    mapping: dict[str, Any] = {
        "evidence_id": "obs-1",
        "checkpoint_id": "cp-1",
        "subject": dict(SUBJECT),
        "redact_pointers": ["/visible"],
    }
    result = run_collector(_StaticCollector({"deployed": True, "visible": SENTINEL}), mapping)
    assert result.error is None
    assert _data_of(result) == {"deployed": True}


def test_col04_subclass_config_validates_through_config_model() -> None:
    mapping: dict[str, Any] = {
        "evidence_id": "obs-1",
        "checkpoint_id": "cp-1",
        "subject": dict(SUBJECT),
        "repo_path": "/tmp/repo",
        "redact_pointers": ["/visible"],
    }
    collector = _SubConfigCollector({"deployed": True, "visible": SENTINEL})
    result = run_collector(collector, mapping)
    assert result.error is None
    assert _data_of(result) == {"deployed": True}
    missing = dict(mapping)
    del missing["repo_path"]
    failed = run_collector(collector, missing)
    assert failed.error is not None
    assert failed.error.code is CollectorErrorCode.CONFIG_INVALID


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
    (criterion,) = verified.criteria
    assert criterion.state.value == "unknown"


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


def test_col06_debug_log_carries_counts_only_no_payload(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.DEBUG, logger="nitelos.collect"):
        result = run_collector(_StaticCollector({"deployed": True, "api_token": SENTINEL}), _config())
    assert result.error is None
    assert caplog.text.strip(), "the framework logs a safe debug line per collection"
    assert SENTINEL not in caplog.text


def test_col06_provenance_repr_is_ids_and_counts_only() -> None:
    result = run_collector(_StaticCollector({"deployed": True}), _config())
    (record,) = result.provenance
    text = repr(record)
    assert "static in-memory fixture" not in text
    assert record.evidence_id in text


# --------------------------------------------------------------------------
# COL-06b: provenance/evidence cross-checks (review finding 6)
# --------------------------------------------------------------------------


_CROSS_CASES = {
    "spoofed_source_id": {"source_id": "evil-source"},
    "wrong_channel": {"channel": "tool"},
    "foreign_subject": {"subject": {"repo": "other/thing"}},
    "foreign_checkpoint": {"checkpoint_id": "cp-evil"},
    "foreign_provenance_collector_id": {"provenance_collector_id": "evil-collector"},
    "foreign_provenance_collector_version": {"provenance_collector_version": "0.0.1"},
    "foreign_provenance_subject": {"provenance_subject": {"repo": "other/thing"}},
    "stale_provenance_captured_at": {"provenance_captured_at": "2000-01-01T00:00:00Z"},
}


@pytest.mark.parametrize("mutation", _CROSS_CASES.values(), ids=_CROSS_CASES.keys())
def test_col06b_cross_check_violations_are_exceptions(mutation: Mapping[str, Any]) -> None:
    result = run_collector(_StaticCollector({"deployed": True}, mutate=mutation), _config())
    assert result.error is not None
    assert result.error.code is CollectorErrorCode.EXCEPTION
    assert result.evidence == ()


def test_col06b_duplicate_and_pre_start_sequences_rejected() -> None:
    class _Twice(_StaticCollector):
        def collect(self, config: CollectorConfig) -> CollectionResult:
            base = super().collect(config)
            second = Evidence.observation(
                id=derive_evidence_id(config.evidence_id, 1),
                sequence=config.sequence_start,  # duplicate on purpose
                captured_at=CAPTURED_AT,
                checkpoint_id=config.checkpoint_id,
                source_id=self.id,
                subject=config.subject,
                phase="final",
                channel="external_api",
                data={"deployed": True},
            )
            (record,) = base.provenance
            second_record = record.model_copy(update={"evidence_id": second.id})
            return CollectionResult(
                collector_id=base.collector_id,
                collector_version=base.collector_version,
                evidence=(*base.evidence, second),
                provenance=(*base.provenance, second_record),
            )

    result = run_collector(_Twice({"deployed": True}), _config())
    assert result.error is not None
    assert result.error.code is CollectorErrorCode.EXCEPTION

    pre_start = run_collector(
        _StaticCollector({"deployed": True}, mutate={"sequence": 5}), _config(sequence_start=7)
    )
    assert pre_start.error is not None
    assert pre_start.error.code is CollectorErrorCode.EXCEPTION


# --------------------------------------------------------------------------
# COL-06c: id derivation (review item 14)
# --------------------------------------------------------------------------


def test_col06c_derive_evidence_id_deterministic_and_pattern_checked() -> None:
    assert derive_evidence_id("obs-1", 0) == "obs-1"
    assert derive_evidence_id("obs-1", 2) == "obs-1-2"
    with pytest.raises(ValueError, match="ID pattern"):
        derive_evidence_id("x" * 128, 1)
    with pytest.raises(ValueError, match="at least 0"):
        derive_evidence_id("obs-1", -1)


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


def test_col07_argv_outside_allowlist_rejected_before_start(monkeypatch: pytest.MonkeyPatch) -> None:
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
    output = _run_allowed(argv, (argv,))
    assert output.stdout.decode("utf-8").strip() == "absent"


def test_col07_result_carries_returncode() -> None:
    argv = (sys.executable, "-c", "print('hi')")
    output = _run_allowed(argv, (argv,))
    assert output.returncode == 0
    assert b"hi" in output.stdout


def test_col07_timeout_maps_to_collector_timeout() -> None:
    argv = (sys.executable, "-c", "import time; time.sleep(5)")
    with pytest.raises(CollectorError) as excinfo:
        _run_allowed(argv, (argv,), timeout_s=0.5)
    assert excinfo.value.code is CollectorErrorCode.TIMEOUT


def test_col07_streaming_child_over_cap_fails_fast() -> None:
    # review finding 2a: communicate() buffered everything until the timeout
    streamer = "import sys\nfor _ in range(300):\n    sys.stdout.write('x' * 65536)\n    sys.stdout.flush()"
    argv = (sys.executable, "-c", streamer)
    started = time.monotonic()
    with pytest.raises(CollectorError) as excinfo:
        _run_allowed(argv, (argv,), max_raw_bytes=262_144, timeout_s=30.0)
    assert excinfo.value.code is CollectorErrorCode.OUTPUT_TOO_LARGE
    assert time.monotonic() - started < 10.0  # killed at the cap, not at the timeout


def test_col07_grandchild_holding_pipes_times_out_and_tree_dies(tmp_path: Path) -> None:
    # review finding 2b: a grandchild holding the pipes must not extend the wait
    spawner = (
        "import subprocess, sys, time\n"
        "subprocess.Popen([sys.executable, '-c', "
        "\"open('held','w').write('x'); import time; time.sleep(60)\"])\n"
        "time.sleep(0.3)"
    )
    argv = (sys.executable, "-c", spawner)
    started = time.monotonic()
    with pytest.raises(CollectorError) as excinfo:
        _run_allowed(argv, (argv,), timeout_s=0.8, cwd=tmp_path)
    elapsed = time.monotonic() - started
    assert excinfo.value.code is CollectorErrorCode.TIMEOUT
    assert elapsed < 4.0  # roughly timeout + bounded reap, never a hang
    time.sleep(1.0)  # the OS needs a moment to tear the tree down
    held = tmp_path / "held"
    if os.name == "nt" and held.exists():
        os.replace(held, tmp_path / "moved")  # succeeds only once the grandchild released it


def test_col07_planted_batch_file_in_cwd_never_runs(tmp_path: Path) -> None:
    # review finding 3: cwd search and .bat/.cmd targets must both be impossible
    planted = tmp_path / "git.bat"
    planted.write_text("@echo PWNED\r\n", encoding="utf-8")
    argv = ("git", "--version")
    outcome: Any = None
    try:
        outcome = _run_allowed(argv, (argv,), cwd=tmp_path)
    except CollectorError as caught:
        outcome = caught
    if isinstance(outcome, CollectorError):
        assert outcome.code is CollectorErrorCode.UNAVAILABLE  # no real git on absolute PATH
    else:
        assert b"PWNED" not in outcome.stdout


def test_col07_relative_path_entries_are_ignored(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from nitelos.collect._process import _resolve_executable

    planted = tmp_path / "probe.cmd"
    planted.write_text("@echo PWNED\r\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PATH", f".{os.pathsep}{tmp_path}")
    assert _resolve_executable("probe") is None  # relative entry + .cmd target: both refused


def test_col07_executable_resolution_uses_absolute_path_entries_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from nitelos.collect._process import _resolve_executable

    source = Path(os.environ.get("COMSPEC") or "/bin/sh")
    exe = tmp_path / ("probe.exe" if os.name == "nt" else "probe")
    shutil.copy(source, exe)
    if os.name != "nt":
        exe.chmod(0o755)
    monkeypatch.setenv("PATH", str(tmp_path))
    resolved = _resolve_executable("probe")
    assert resolved is not None
    assert Path(resolved).is_absolute()
    assert Path(resolved).parent == tmp_path


def test_col07_relative_argv0_with_separator_rejected(tmp_path: Path) -> None:
    argv = ("sub/probe", "--version")
    with pytest.raises(CollectorError) as excinfo:
        _run_allowed(argv, (argv,), cwd=tmp_path)
    assert excinfo.value.code is CollectorErrorCode.CONFIG_INVALID


def test_col07_bad_cwd_maps_to_unavailable(tmp_path: Path) -> None:
    argv = (sys.executable, "-c", "print('never')")
    with pytest.raises(CollectorError) as excinfo:
        _run_allowed(argv, (argv,), cwd=tmp_path / "does-not-exist")
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
    output = _run_allowed(argv, (argv,))
    assert seen["args"][0] == sys.executable or str(seen["args"][0]).endswith("python")
    assert seen["shell"] is False
    assert b"ok" in output.stdout


# --------------------------------------------------------------------------
# COL-08: the reusable contract suite
# --------------------------------------------------------------------------


def test_col08_contract_suite_passes_for_a_well_formed_collector() -> None:
    assert_contract(
        _StaticCollector({"deployed": True, "api_token": SENTINEL}),
        _config(),
        slow=lambda: (_SleepyCollector(0.3), _config(limits=CollectorLimits(timeout_s=0.05))),
    )


def test_col08_contract_suite_passes_without_the_slow_hook() -> None:
    # without a slow hook the suite skips its timeout probe (documented for NIT-018+)
    assert_contract(_StaticCollector({"deployed": True}), _config())


def test_col08_suite_catches_missing_provenance() -> None:
    class _NoProvenance(_StaticCollector):
        def collect(self, config: CollectorConfig) -> CollectionResult:
            good = super().collect(config)
            return CollectionResult(
                collector_id=good.collector_id,
                collector_version=good.collector_version,
                evidence=good.evidence,
                provenance=(),  # broken: no provenance
            )

    assert_broken_collector_fails(
        _NoProvenance({"deployed": True}), _config(), expected_code=CollectorErrorCode.EXCEPTION
    )


def test_col08_suite_self_granted_trust_is_structurally_impossible() -> None:
    class _SelfTrusting(_StaticCollector):
        def collect(self, config: CollectorConfig) -> CollectionResult:
            good = super().collect(config)
            smuggled = CollectionResult.model_construct(
                collector_id=good.collector_id,
                collector_version=good.collector_version,
                evidence=good.evidence,
                provenance=good.provenance,
                trusted=True,  # deliberately broken: an attempted trust field
            )
            assert not hasattr(smuggled, "trusted")  # the model evaporates it
            return smuggled

    result = run_collector(_SelfTrusting({"deployed": True}), _config())
    assert result.error is None  # the smuggle never had any effect
    assert not hasattr(result, "trusted")
    assert "bindings" not in CollectionResult.model_fields
    with pytest.raises(ValidationError, match="extra"):
        CollectionResult(
            collector_id="x",
            collector_version="1",
            evidence=(),
            provenance=(),
            trusted=True,  # type: ignore[call-arg]
        )


def test_col08_suite_catches_spoofed_source_id() -> None:
    assert_broken_collector_fails(
        _StaticCollector({"deployed": True}, mutate={"source_id": "evil-source"}),
        _config(),
        expected_code=CollectorErrorCode.EXCEPTION,
    )


def test_col04_screenshot_items_pass_through_with_final_digest() -> None:
    from _imagekit import png_bytes

    payload = png_bytes(4, 4, "RGB", (10, 20, 30))

    class _ScreenshotCollector(_StaticCollector):
        @property
        def capabilities(self) -> CollectorCapabilities:
            return CollectorCapabilities(evidence_kinds=("screenshot",))

        def collect(self, config: CollectorConfig) -> CollectionResult:
            item = Evidence.screenshot(
                id=config.evidence_id,
                artifact_id="art-1",
                data=payload,
                sequence=config.sequence_start,
                captured_at=CAPTURED_AT,
                checkpoint_id=config.checkpoint_id,
                source_id=self.id,
                subject=config.subject,
                phase="final",
            )
            digest = hashlib.sha256(payload).hexdigest()
            return CollectionResult(
                collector_id=self.id,
                collector_version=self.version,
                evidence=(item,),
                provenance=(
                    ProvenanceRecord(
                        evidence_id=item.id,
                        collector_id=self.id,
                        collector_version=self.version,
                        source="static screenshot fixture",
                        invocation="static",
                        captured_at=item.captured_at,
                        subject=config.subject,
                        sha256=digest,
                        raw_bytes=len(payload),
                        normalized_bytes=len(payload),
                    ),
                ),
            )

    result = run_collector(_ScreenshotCollector({}), _config())
    assert result.error is None
    (item,) = result.evidence
    (record,) = result.provenance
    assert item.kind == "screenshot"
    assert record.sha256 == hashlib.sha256(payload).hexdigest()  # raw capture digest
    assert record.evidence_sha256 == item.sha256  # final digest filled in
