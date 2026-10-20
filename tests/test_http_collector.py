"""HTC-01..12: F5 HTTP JSON collector (NIT-021, kind ``http``)."""

from __future__ import annotations

import json
from typing import Any

import pytest

from nitelos import canonical_json
from nitelos.collect import (
    CollectorErrorCode,
    CollectorLimits,
    run_collector,
)
from nitelos.collect._http import HttpResponse
from nitelos.collect.http_json import COLLECTOR, HttpJsonCollector, HttpJsonConfig

BAD = "url must be an absolute https|pointers|Input should be"


def _transport_reply(status: int, body: bytes, headers: dict[str, str] | None = None) -> HttpResponse:
    return HttpResponse(status, body, headers or {"content-type": "application/json"})


def _config(
    *,
    url: str = "https://api.example.com/v1/records/rec-1",
    pointers: tuple[str, ...] = ("/status",),
    subject: dict[str, str] | None = None,
) -> HttpJsonConfig:
    return HttpJsonConfig(
        evidence_id="rec-1",
        checkpoint_id="cp",
        subject=subject or {"record": "rec-1"},
        url=url,
        pointers=pointers,
    )


def _run(transport_responses: list[HttpResponse], cfg: HttpJsonConfig | None = None) -> Any:
    calls: list[str] = []

    def transport(url: str, headers: Any, timeout_s: float, max_bytes: int) -> HttpResponse:
        calls.append(url)
        return transport_responses[len(calls) - 1]

    collector = HttpJsonCollector(transport=transport)
    result = run_collector(collector, cfg if cfg is not None else _config())
    result._calls = calls  # type: ignore[attr-defined]
    return result


def _data(result: Any) -> dict[str, Any]:
    assert result.error is None, result.error
    assert len(result.evidence) == 1
    return dict(result.evidence[0].data)


def test_htc01_extracts_pointers_status_and_headers() -> None:
    body = json.dumps({"status": "active", "nested": {"owner": "ada"}}).encode()
    result = _run([_transport_reply(200, body)])
    data = _data(result)
    http = data["http"]
    assert http["status_code"] == 200
    assert http["values"] == {"/status": "active"}
    assert http["headers"]["content-type"] == "application/json"
    assert result._calls == ["https://api.example.com/v1/records/rec-1"]


def test_htc02_nested_pointers() -> None:
    body = json.dumps({"nested": {"owner": "ada", "ids": [10, 20]}}).encode()
    cfg = _config(pointers=("/nested/owner", "/nested/ids/1"))
    data = _data(_run([_transport_reply(200, body)], cfg))
    assert data["http"]["values"] == {"/nested/owner": "ada", "/nested/ids/1": 20}


def test_htc03b_leading_zero_index_stays_unresolved() -> None:
    body = json.dumps({"l": [10, 20]}).encode()
    cfg = _config(pointers=("/l/01", "/l/1"))
    data = _data(_run([_transport_reply(200, body)], cfg))
    assert data["http"]["values"] == {"/l/01": None, "/l/1": 20}


def test_htc03_missing_pointer_is_null_not_error() -> None:
    body = json.dumps({"status": "active"}).encode()
    cfg = _config(pointers=("/status", "/absent"))
    data = _data(_run([_transport_reply(200, body)], cfg))
    assert data["http"]["values"] == {"/status": "active", "/absent": None}


def test_htc04_only_allowlisted_headers_kept() -> None:
    body = b"{}"
    reply = _transport_reply(
        200, body, {"content-type": "application/json", "server": "nginx", "x-ratelimit-remaining": "42"}
    )
    data = _data(_run([reply]))
    assert set(data["http"]["headers"]) == {"content-type", "x-ratelimit-remaining"}


def test_htc05_plain_http_rejected_before_request() -> None:
    def transport(url: str, headers: Any, timeout_s: float, max_bytes: int) -> HttpResponse:
        raise AssertionError("must not be called")

    mapping = {
        "evidence_id": "x-1",
        "checkpoint_id": "cp",
        "subject": {"record": "rec-1"},
        "url": "http://api.example.com/x",
        "pointers": ["/status"],
    }
    result = run_collector(HttpJsonCollector(transport=transport), mapping)
    assert result.error is not None
    assert result.error.code == CollectorErrorCode.CONFIG_INVALID


def test_htc06_non_json_body_is_structured_error() -> None:
    result = _run([_transport_reply(200, b"<html>not json</html>")])
    assert result.error is not None
    assert result.error.code == CollectorErrorCode.EXCEPTION


def test_htc07_404_is_unavailable() -> None:
    result = _run([_transport_reply(404, b"{}")])
    assert result.error is not None
    assert result.error.code == CollectorErrorCode.UNAVAILABLE


def test_htc08_401_is_auth_missing() -> None:
    result = _run([_transport_reply(401, b"{}")])
    assert result.error is not None
    assert result.error.code == CollectorErrorCode.AUTH_MISSING


def test_htc09_no_secret_leakage_in_data_or_provenance() -> None:
    sentinel = "SECRET-token-value"
    body = json.dumps({"status": "active", "token": sentinel}).encode()
    result = _run([_transport_reply(200, body)])
    blob = (
        repr(result)
        + canonical_json(_data(result))
        + json.dumps({"source": result.provenance[0].source, "invocation": result.provenance[0].invocation})
    )
    assert sentinel not in blob
    assert "token" not in canonical_json(_data(result))
    record = result.provenance[0]
    assert sentinel not in json.dumps({"source": record.source, "invocation": record.invocation})


def test_htc10_provenance_and_wire_contract() -> None:
    body = json.dumps({"status": "active"}).encode()
    result = _run([_transport_reply(200, body)])
    item = result.evidence[0]
    assert item.source_id == COLLECTOR.id
    assert str(item.channel) == "external_api"
    record = result.provenance[0]
    assert record.raw_bytes == len(body)
    assert record.sha256 != ""


def test_htc11_config_validation() -> None:
    with pytest.raises(ValueError, match=BAD):
        HttpJsonConfig(
            evidence_id="x",
            checkpoint_id="cp",
            subject={"r": "1"},
            url="ftp://example.com/x",
            pointers=("/a",),
        )
    with pytest.raises(ValueError, match=BAD):
        HttpJsonConfig(
            evidence_id="x",
            checkpoint_id="cp",
            subject={"r": "1"},
            url="https://api.example.com/x",
            pointers=("/status", "/a~2bad"),
        )
    with pytest.raises(ValueError, match=BAD):
        HttpJsonConfig(
            evidence_id="x",
            checkpoint_id="cp",
            subject={"r": "1"},
            url="https://api.example.com/x",
            pointers=(),
        )


def test_htc12_response_size_cap_via_transport() -> None:
    # the cap itself is the transport's contract (htp03); here we assert the
    # collector passes its limits through and surfaces the raised error.
    def capped_transport(url: str, headers: Any, timeout_s: float, max_bytes: int) -> HttpResponse:
        assert max_bytes == 1024
        raise __import__("nitelos.collect", fromlist=["CollectorError"]).CollectorError(
            CollectorErrorCode.OUTPUT_TOO_LARGE
        )

    cfg = HttpJsonConfig(
        evidence_id="x-1",
        checkpoint_id="cp",
        subject={"r": "1"},
        url="https://api.example.com/x",
        pointers=("/a",),
        limits=CollectorLimits(max_raw_bytes=1024),
    )
    result = run_collector(HttpJsonCollector(transport=capped_transport), cfg)
    assert result.error is not None
    assert result.error.code == CollectorErrorCode.OUTPUT_TOO_LARGE
