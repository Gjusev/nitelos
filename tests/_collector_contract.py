"""Reusable collector contract suite (COL-08, NIT-017).

Not collected by pytest directly: import ``assert_contract`` (happy path) and
``assert_broken_collector_fails`` (negative path) from a collector's test
module and point them at your collector, e.g.::

    from _collector_contract import assert_contract, assert_broken_collector_fails

    def test_git_collector_contract() -> None:
        assert_contract(MyGitCollector(), _config())

The happy-path contract checks, in order: error/evidence exclusivity,
one complete provenance record per evidence item (ids 1:1, aware-UTC
captured_at), evidence kinds within declared capabilities, wire-valid
evidence a real Verifier accepts, determinism (identical input -> identical
digests), and payload-free reprs. The negative path proves the framework
never lets an incomplete collector succeed: a broken collector surfaces as a
structured error result, never as partial evidence. NIT-018 (git) and
NIT-019 (junit) reuse this suite as their acceptance contract.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from nitelos import Verifier, parse_request
from nitelos.collect import CollectorConfig, CollectorError, CollectorErrorCode, run_collector

PAYLOAD_SENTINEL = "CONTRACT-SENTINEL-8f2a"


def assert_contract(collector: Any, config: CollectorConfig | Mapping[str, Any]) -> None:
    """Run ``collector`` through ``run_collector`` and assert the full contract."""
    result = run_collector(collector, config)
    _assert_error_exclusivity(result)
    assert result.error is None, result.error
    _assert_provenance_complete(result)
    _assert_kinds_within_capabilities(collector, result)
    if result.evidence:
        _assert_wire_valid_evidence(result, config)
    _assert_deterministic_digests(collector, config, result)
    _assert_safe_repr(result)


def assert_broken_collector_fails(collector: Any, config: CollectorConfig | Mapping[str, Any]) -> None:
    """A collector violating the contract must fail loudly, never partially."""
    result = run_collector(collector, config)
    _assert_error_exclusivity(result)
    assert result.error is not None
    assert result.evidence == ()
    assert result.provenance == ()


def collector_error(code: CollectorErrorCode) -> CollectorError:
    """Helper for collectors simulating a known failure."""
    return CollectorError(code)


def _assert_error_exclusivity(result: Any) -> None:
    if result.error is not None:
        assert result.evidence == ()
        assert result.provenance == ()
    else:
        assert result.collector_id
        assert result.collector_version


def _assert_provenance_complete(result: Any) -> None:
    evidence_ids = [item.id for item in result.evidence]
    provenance_ids = [record.evidence_id for record in result.provenance]
    assert sorted(evidence_ids) == sorted(provenance_ids)
    for record in result.provenance:
        assert record.captured_at.tzinfo is not None
        assert record.raw_bytes >= 1
        assert record.sha256  # 64-hex, enforced by the model


def _assert_kinds_within_capabilities(collector: Any, result: Any) -> None:
    declared = collector.capabilities.evidence_kinds
    for item in result.evidence:
        assert item.kind in declared, item.kind


def _assert_wire_valid_evidence(result: Any, config: CollectorConfig | Mapping[str, Any]) -> None:
    cfg = config if isinstance(config, CollectorConfig) else CollectorConfig.model_validate(dict(config))
    captured_at = result.evidence[0].model_dump(mode="json")["captured_at"]
    document = {
        "schema_version": "1",
        "objective": "contract round-trip",
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
        "request_id": "req-contract",
        "checkpoint_id": cfg.checkpoint_id,
        "as_of": captured_at,
    }
    request = parse_request(document)
    verified = Verifier().verify(request)
    assert verified.execution_status.value == "ok", verified.error


def _assert_deterministic_digests(collector: Any, config: Any, first: Any) -> None:
    second = run_collector(collector, config)
    assert [item.sha256 for item in second.evidence] == [item.sha256 for item in first.evidence]


def _assert_safe_repr(result: Any) -> None:
    assert PAYLOAD_SENTINEL not in repr(result)
    for record in result.provenance:
        assert PAYLOAD_SENTINEL not in repr(record)
