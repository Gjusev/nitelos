"""GH-01..14: the GitHub collector on the NIT-017 framework (NIT-020, plan F4).

Offline through the injected transport seam (ADR-015 finding 1: recorded
fixtures, no sockets — the conftest denies network to ordinary tests). A live
test needs the centrally-registered opt-in marker plus a conftest escape, both
outside this task's file list (rule-2 stop, reported).
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

from _collector_contract import assert_contract
from nitelos import Verifier, cli, parse_request
from nitelos.collect import (
    CollectorErrorCode,
    CollectorLimits,
    host_trust_bindings,
    run_collector,
)
from nitelos.collect._http import HttpResponse
from nitelos.collect.github import COLLECTOR, GithubCollector, GithubConfig

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "github"
SENTINEL_AUTH = "ghp_test-token-SENTINEL-a1"
SUBJECT = {"repo": "example/app"}


@pytest.fixture(autouse=True)
def _token_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every test gets a token unless it deletes it (the missing-token tests do)."""
    monkeypatch.setenv("GITHUB_TOKEN", SENTINEL_AUTH)


def _fixture(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


def _transport(routes: Mapping[str, tuple[int, bytes, Mapping[str, str]]]) -> Any:
    """Fake GET transport keyed by URL substring; records the headers it got."""

    class _Fake:
        def __init__(self) -> None:
            self.requests: list[tuple[str, dict[str, str]]] = []

        def __call__(
            self, url: str, headers: Mapping[str, str], timeout_s: float, max_bytes: int
        ) -> HttpResponse:
            self.requests.append((url, dict(headers)))
            matches = [(len(needle), response) for needle, response in routes.items() if needle in url]
            if not matches:
                raise AssertionError(f"unexpected url: {url}")
            _length, (status, body, extra) = max(matches, key=lambda item: item[0])
            return HttpResponse(status=status, body=body, headers=dict(extra))

    return _Fake()


def _ok(name: str) -> tuple[int, bytes, Mapping[str, str]]:
    return (200, _fixture(name), {})


def _config(**over: Any) -> GithubConfig:
    values: dict[str, Any] = {
        "evidence_id": "obs-gh-1",
        "checkpoint_id": "cp-1",
        "subject": dict(SUBJECT),
        "owner": "example",
        "repo": "app",
        "pr_number": 27,
    }
    values.update(over)
    return GithubConfig.model_validate(values)


def _collect(transport: Any, **over: Any) -> Any:
    collector = GithubCollector(transport=transport)
    return run_collector(collector, _config(**over))


def _data(result: Any) -> dict[str, Any]:
    assert result.error is None, result.error
    (item,) = result.evidence
    return dict(item.data)["github"]["pr"]  # type: ignore[no-any-return]


def _full_routes() -> dict[str, tuple[int, bytes, Mapping[str, str]]]:
    return {
        "/pulls/27": _ok("pr.json"),
        "/pulls/27/reviews": _ok("reviews-approved.json"),
        "/commits/a41b0c6d2e3f4051672839abcdef0123456789a/check-runs": _ok("check-runs.json"),
        "/branches/main/protection": _ok("protection.json"),
    }


# --------------------------------------------------------------------------
# GH-01..05: observations from recorded fixtures
# --------------------------------------------------------------------------


def test_gh01_pr_fields() -> None:
    data = _data(_collect(_transport(_full_routes())))
    assert data["state"] == "open"
    assert data["merged"] is False
    assert data["draft"] is False
    assert data["mergeable_state"] == "clean"
    assert data["head_sha"] == "a41b0c6d2e3f4051672839abcdef0123456789a"


def test_gh02_review_decision_derived_from_latest_reviews() -> None:
    approved = _data(_collect(_transport(_full_routes())))
    assert approved["review_decision"] == "APPROVED"
    changes_routes = _full_routes()
    changes_routes["/pulls/27/reviews"] = _ok("reviews-changes.json")
    assert _data(_collect(_transport(changes_routes)))["review_decision"] == "CHANGES_REQUESTED"
    none_routes = _full_routes()
    none_routes["/pulls/27/reviews"] = _ok("reviews-none.json")
    assert _data(_collect(_transport(none_routes)))["review_decision"] == "REVIEW_REQUIRED"


def test_gh03_required_checks_and_all_green_true() -> None:
    data = _data(_collect(_transport(_full_routes())))
    assert [check["name"] for check in data["checks"]] == ["build", "test", "lint"]
    assert list(data["required_checks"]) == ["build", "test"]
    assert data["checks_all_green"] is True  # lint fails but is NOT required


def test_gh04_required_failing_check_flips_the_boolean() -> None:
    routes = _full_routes()
    body = json.loads(_fixture("check-runs.json"))
    body["check_runs"][0]["conclusion"] = "failure"
    routes["/commits/a41b0c6d2e3f4051672839abcdef0123456789a/check-runs"] = (
        200,
        json.dumps(body).encode(),
        {},
    )
    assert _data(_collect(_transport(routes)))["checks_all_green"] is False


def test_gh05_unreadable_protection_nulls_the_boolean_not_the_collection() -> None:
    routes = _full_routes()
    routes["/branches/main/protection"] = (404, b'{"message": "Not Found"}', {})
    data = _data(_collect(_transport(routes)))
    assert data["checks_all_green"] is None
    assert data["required_checks"] is None


# --------------------------------------------------------------------------
# GH-06..09: auth, error mapping to abstention, host rules
# --------------------------------------------------------------------------


def test_gh06_token_from_env_and_never_leaks(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GITHUB_TOKEN", SENTINEL_AUTH)
    transport = _transport(_full_routes())
    result = _collect(transport)
    assert result.error is None
    (_url, headers), *_ = [r for r in transport.requests if "/pulls/27" in r[0] and "reviews" not in r[0]]
    assert headers["Authorization"] == f"Bearer {SENTINEL_AUTH}"
    assert SENTINEL_AUTH not in repr(result)
    assert SENTINEL_AUTH not in json.dumps([p.model_dump(mode="json") for p in result.provenance])
    assert SENTINEL_AUTH not in json.dumps([e.model_dump(mode="json") for e in result.evidence])


def test_gh06b_gh_token_fallback_and_missing_maps_to_auth_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.setenv("GH_TOKEN", SENTINEL_AUTH)
    transport = _transport(_full_routes())
    assert _collect(transport).error is None
    monkeypatch.delenv("GH_TOKEN", raising=False)
    result = _collect(_transport(_full_routes()))
    assert result.error is not None
    assert result.error.code is CollectorErrorCode.AUTH_MISSING
    assert result.evidence == ()


def test_gh07_not_found_maps_to_unavailable() -> None:
    routes = {"/pulls/27": (404, b'{"message": "Not Found"}', {})}
    result = _collect(_transport(routes))
    assert result.error is not None
    assert result.error.code is CollectorErrorCode.UNAVAILABLE


def test_gh08_rate_limit_and_bad_token_mapping() -> None:
    limited = {"/pulls/27": (403, b"{}", {"X-RateLimit-Remaining": "0"})}
    result = _collect(_transport(limited))
    assert result.error is not None
    assert result.error.code is CollectorErrorCode.UNAVAILABLE
    too_many = {"/pulls/27": (429, b"{}", {"Retry-After": "60"})}
    assert _collect(_transport(too_many)).error is not None
    unauthorized = {"/pulls/27": (401, b"{}", {})}
    result = _collect(_transport(unauthorized))
    assert result.error is not None
    assert result.error.code is CollectorErrorCode.AUTH_MISSING


def test_gh09_host_is_fixed_unless_enterprise() -> None:
    transport = _transport(_full_routes())
    _collect(transport)
    assert all(url.startswith("https://api.github.com/") for url, _ in transport.requests)
    enterprise = _transport(_full_routes())
    _collect(enterprise, enterprise_host="github.example.com")
    assert all(url.startswith("https://github.example.com/api/v3/") for url, _ in enterprise.requests)


def test_gh09b_config_validation() -> None:
    for bad in (
        {"owner": "example", "repo": "app", "pr_number": 0},
        {"owner": "example", "repo": "app", "pr_number": -1},
        {"owner": "", "repo": "app", "pr_number": 5},
    ):
        values: dict[str, Any] = {
            "evidence_id": "obs-gh-1",
            "checkpoint_id": "cp-1",
            "subject": dict(SUBJECT),
        }
        values.update(bad)
        result = run_collector(COLLECTOR, values)
        assert result.error is not None
        assert result.error.code is CollectorErrorCode.CONFIG_INVALID
    unknown = {
        "evidence_id": "obs-gh-1",
        "checkpoint_id": "cp-1",
        "subject": dict(SUBJECT),
        "owner": "example",
        "repo": "app",
        "pr_number": 5,
        "surprise": 1,
    }
    assert run_collector(COLLECTOR, unknown).error is not None


# --------------------------------------------------------------------------
# GH-10..11: criteria round trip and the contract suite
# --------------------------------------------------------------------------


def _request(result: Any, pointer: str, expected: Any) -> Any:
    (item,) = result.evidence
    document = {
        "schema_version": "1",
        "request_id": "req-gh-1",
        "objective": "The PR really is mergeable",
        "checkpoint_id": "cp-1",
        "as_of": item.model_dump(mode="json")["captured_at"],
        "criteria": [
            {
                "id": "c-gh",
                "description": "PR state matches the claim",
                "kind": "assertion",
                "scope": "external",
                "evidence_ids": [item.id],
                "subject": dict(SUBJECT),
                "pointer": pointer,
                "operator": "equals",
                "expected": expected,
            }
        ],
        "evidence": [item.model_dump(mode="json") for item in result.evidence],
        "metadata": {},
    }
    return parse_request(document)


def test_gh10_criteria_decide_on_pr_state(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GITHUB_TOKEN", SENTINEL_AUTH)
    result = _collect(_transport(_full_routes()))
    verified = Verifier(trust_bindings=host_trust_bindings(result)).verify(
        _request(result, "/github/pr/checks_all_green", True)
    )
    assert verified.decision is not None
    assert verified.decision.value == "success"
    verified = Verifier(trust_bindings=host_trust_bindings(result)).verify(
        _request(result, "/github/pr/state", "closed")
    )
    assert verified.decision is not None
    assert verified.decision.value == "failure"


def test_gh11_contract_suite_passes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GITHUB_TOKEN", SENTINEL_AUTH)

    class _Slow:
        requests: list[Any] = []  # noqa: RUF012 - test double, never mutated

        def __call__(
            self, url: str, headers: Mapping[str, str], timeout_s: float, max_bytes: int
        ) -> HttpResponse:
            import time

            time.sleep(0.2)
            return HttpResponse(status=200, body=_fixture("pr.json"), headers={})

    assert_contract(
        GithubCollector(transport=_transport(_full_routes())),
        _config(),
        slow=lambda: (
            GithubCollector(transport=_Slow()),
            _config(limits=CollectorLimits(timeout_s=0.05)),
        ),
    )


# --------------------------------------------------------------------------
# GH-12: provenance records the endpoints, never the token
# --------------------------------------------------------------------------


def test_gh12_provenance_shape(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GITHUB_TOKEN", SENTINEL_AUTH)
    result = _collect(_transport(_full_routes()))
    (record,) = result.provenance
    assert record.source == "GitHub REST (read-only GET)"
    assert "api.github.com" in record.invocation
    assert SENTINEL_AUTH not in record.invocation
    assert record.evidence_sha256 == result.evidence[0].sha256


# --------------------------------------------------------------------------
# GH-13: the CLI kind
# --------------------------------------------------------------------------


def test_gh13_cli_kind_registered() -> None:
    assert cli.KIND_TARGETS["github"] == "nitelos.collect.github:COLLECTOR"
