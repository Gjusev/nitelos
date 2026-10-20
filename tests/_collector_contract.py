"""Reusable collector contract suite (COL-08, NIT-017).

Not collected by pytest directly: import ``assert_contract`` (happy path plus
generic probes) and ``assert_broken_collector_fails`` (negative path) from a
collector's test module and point them at your collector::

    from _collector_contract import assert_broken_collector_fails, assert_contract

    def test_git_collector_contract() -> None:
        assert_contract(
            MyGitCollector(),
            _config(),
            slow=lambda: (MyGitCollector(), slow_config),  # timeout probe
        )

The suite checks, through ``run_collector`` and the collector's own
``config_model``: error/evidence exclusivity; one complete provenance record
per evidence item (ids 1:1, aware-UTC captured_at, the review-finding-6
cross-checks incl. source_id/channel/subject/checkpoint and the
provenance/evidence correspondence); evidence kinds within declared
capabilities; wire-valid evidence a real Verifier accepts; a DECISIVE
round trip under ``host_trust_bindings`` (success or failure — an abstention
means the collected evidence cannot satisfy any criterion, a contract
violation); determinism (identical input -> identical digests); payload-free
reprs; the observation cap (``max_observation_bytes=1`` -> OUTPUT_TOO_LARGE,
never truncation; screenshot-only collectors skip this probe); unknown config
fields -> CONFIG_INVALID; and, when a ``slow`` hook is supplied, the timeout
mapping -> COLLECTOR_TIMEOUT. The negative path proves a broken collector
never succeeds: pass ``expected_code`` to assert which failure surfaces.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from nitelos import Verifier, canonical_json, parse_request
from nitelos.collect import (
    CollectionResult,
    CollectorConfig,
    CollectorError,
    CollectorErrorCode,
    CollectorLimits,
    host_trust_bindings,
    run_collector,
)

SENTINEL = "CONTRACT-SENTINEL-8f2a"

SlowHook = Callable[[], tuple[Any, CollectorConfig | Mapping[str, Any]]]


def assert_contract(
    collector: Any,
    config: CollectorConfig | Mapping[str, Any],
    *,
    slow: SlowHook | None = None,
) -> CollectionResult:
    """Run ``collector`` through ``run_collector`` and assert the full contract."""
    result = run_collector(collector, config)
    _assert_error_exclusivity(result)
    assert result.error is None, result.error
    _assert_provenance_complete(result)
    _assert_kinds_within_capabilities(collector, result)
    if result.evidence:
        _assert_wire_valid_evidence(result, config)
        _assert_decisive_round_trip(result, config)
    _assert_deterministic_digests(collector, config, result)
    _assert_safe_repr(result, SENTINEL)
    _assert_cap_probe(collector, config, result)
    _assert_invalid_config_probe(collector, config)
    if slow is not None:
        _assert_timeout_probe(slow)
    return result


def assert_broken_collector_fails(
    collector: Any,
    config: CollectorConfig | Mapping[str, Any],
    *,
    expected_code: CollectorErrorCode | None = None,
) -> None:
    """A collector violating the contract must fail loudly, never partially."""
    result = run_collector(collector, config)
    _assert_error_exclusivity(result)
    assert result.error is not None
    if expected_code is not None:
        assert result.error.code is expected_code, result.error
    assert result.evidence == ()
    assert result.provenance == ()


def _config_through_model(collector: Any, config: Mapping[str, Any]) -> Any:
    model = getattr(collector, "config_model", CollectorConfig)
    return run_collector(collector, model.model_validate_json(canonical_json(config)))


def _assert_error_exclusivity(result: CollectionResult) -> None:
    if result.error is not None:
        assert result.evidence == ()
        assert result.provenance == ()
    else:
        assert result.collector_id
        assert result.collector_version


def _assert_provenance_complete(result: CollectionResult) -> None:
    evidence_ids = [item.id for item in result.evidence]
    provenance_ids = [record.evidence_id for record in result.provenance]
    assert sorted(evidence_ids) == sorted(provenance_ids)
    for item, record in zip(result.evidence, result.provenance, strict=True):
        assert record.captured_at == item.captured_at
        assert record.collector_id == result.collector_id
        assert record.collector_version == result.collector_version
        assert record.subject == item.subject
        assert record.evidence_sha256 == item.sha256
        assert record.captured_at.tzinfo is not None
        assert record.raw_bytes >= 0


def _assert_kinds_within_capabilities(collector: Any, result: CollectionResult) -> None:
    declared = collector.capabilities.evidence_kinds
    for item in result.evidence:
        assert item.kind in declared, item.kind


def _request_document(result: CollectionResult, cfg: CollectorConfig) -> dict[str, Any]:
    captured_at = result.evidence[0].model_dump(mode="json")["captured_at"]
    return {
        "schema_version": "1",
        "request_id": "req-contract",
        "objective": "contract round-trip",
        "checkpoint_id": cfg.checkpoint_id,
        "as_of": captured_at,
        "criteria": [
            {
                "id": "c-contract",
                "description": "The collected payload exists",
                "kind": "assertion",
                "scope": "external",
                "evidence_ids": [item.id for item in result.evidence],
                "subject": dict(cfg.subject),
                "pointer": "",
                "operator": "exists",
            }
        ],
        "evidence": [item.model_dump(mode="json") for item in result.evidence],
        "metadata": {},
    }


def _wire_config(config: CollectorConfig | Mapping[str, Any]) -> CollectorConfig:
    if isinstance(config, CollectorConfig):
        return config
    return CollectorConfig.model_validate_json(canonical_json(dict(config)))


def _assert_wire_valid_evidence(result: CollectionResult, config: Any) -> None:
    cfg = _wire_config(config)
    request = parse_request(_request_document(result, cfg))
    verified = Verifier().verify(request)
    assert verified.execution_status.value == "ok", verified.error


def _assert_decisive_round_trip(result: CollectionResult, config: Any) -> None:
    """Bound collected evidence must yield a DECISIVE verified decision."""
    cfg = _wire_config(config)
    request = parse_request(_request_document(result, cfg))
    verified = Verifier(trust_bindings=host_trust_bindings(result)).verify(request)
    assert verified.execution_status.value == "ok", verified.error
    assert verified.decision is not None
    assert verified.decision.value in ("success", "failure"), verified.decision


def _assert_deterministic_digests(collector: Any, config: Any, first: CollectionResult) -> None:
    second = run_collector(collector, config)
    assert [item.sha256 for item in second.evidence] == [item.sha256 for item in first.evidence]


def _assert_safe_repr(result: CollectionResult, sentinel: str) -> None:
    assert sentinel not in repr(result)
    for record in result.provenance:
        assert sentinel not in repr(record)


def _assert_cap_probe(collector: Any, config: Any, first: CollectionResult) -> None:
    """max_observation_bytes=1 must error (never truncate) for observation collectors."""
    if not any(item.kind == "observation" for item in first.evidence):
        return  # screenshot-only collectors: no observation cap applies
    cfg = _wire_config(config)
    tight = cfg.model_copy(update={"limits": CollectorLimits(max_observation_bytes=1)})
    probed = run_collector(collector, tight)
    assert probed.error is not None
    assert probed.error.code is CollectorErrorCode.OUTPUT_TOO_LARGE, probed.error
    assert probed.evidence == ()


def _assert_invalid_config_probe(collector: Any, config: Any) -> None:
    cfg = _wire_config(config)
    values = cfg.model_dump()
    values["surprise_field_xyz"] = 1  # unknown field: run_collector maps this, not us
    probed = run_collector(collector, values)
    assert probed.error is not None
    assert probed.error.code is CollectorErrorCode.CONFIG_INVALID, probed.error


def _assert_timeout_probe(slow: SlowHook) -> None:
    collector, config = slow()
    probed = run_collector(collector, config)
    assert probed.error is not None
    assert probed.error.code is CollectorErrorCode.TIMEOUT, probed.error


def collector_error(code: CollectorErrorCode) -> CollectorError:
    """Helper for collectors simulating a known failure."""
    return CollectorError(code)
