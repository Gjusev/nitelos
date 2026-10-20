"""HTP-01..07: the shared GET-only transport (NIT-020, ADR-015 collector exception).

The default transport is exercised with a monkeypatched opener call (no
sockets; the conftest denies network to ordinary tests). Only the
scheme/redirect/host rules, the size cap and the timeout mapping are
unit-tested here; live behaviour rides on the opt-in marker that needs a
central rule-2 change (reported).
"""

from __future__ import annotations

import io
import urllib.request
from typing import Any

import pytest

from nitelos.collect import CollectorError, CollectorErrorCode, _http


class _FakeResponse(io.BytesIO):
    def __init__(self, body: bytes, *, status: int = 200) -> None:
        super().__init__(body)
        self.status = status
        self.headers: dict[str, str] = {}

    def geturl(self) -> str:
        return "https://api.github.com/x"

    def info(self) -> dict[str, str]:
        return self.headers


def test_htp01_get_returns_status_body_and_headers(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_http, "_open", lambda req, timeout: _FakeResponse(b'{"ok": true}'))
    response = _http.default_transport("https://api.github.com/x", {}, timeout_s=5.0, max_bytes=1024)
    assert response.status == 200
    assert response.body == b'{"ok": true}'


def test_htp02_plain_http_is_rejected_before_any_request() -> None:
    with pytest.raises(CollectorError) as excinfo:
        _http.default_transport("http://api.github.com/x", {}, timeout_s=5.0, max_bytes=1024)
    assert excinfo.value.code is CollectorErrorCode.CONFIG_INVALID


def test_htp03_body_over_cap_is_too_large_never_truncated(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_http, "_open", lambda req, timeout: _FakeResponse(b"x" * 4096))
    with pytest.raises(CollectorError) as excinfo:
        _http.default_transport("https://api.github.com/x", {}, timeout_s=5.0, max_bytes=1024)
    assert excinfo.value.code is CollectorErrorCode.OUTPUT_TOO_LARGE


def test_htp04_socket_timeout_maps_to_collector_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    def _slow(req: Any, timeout: float) -> Any:
        raise TimeoutError("timed out")

    monkeypatch.setattr(_http, "_open", _slow)
    with pytest.raises(CollectorError) as excinfo:
        _http.default_transport("https://api.github.com/x", {}, timeout_s=5.0, max_bytes=1024)
    assert excinfo.value.code is CollectorErrorCode.TIMEOUT


def test_htp05_network_errors_map_to_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    from urllib.error import URLError

    def _dead(req: Any, timeout: float) -> Any:
        raise URLError("no route to host")

    monkeypatch.setattr(_http, "_open", _dead)
    with pytest.raises(CollectorError) as excinfo:
        _http.default_transport("https://api.github.com/x", {}, timeout_s=5.0, max_bytes=1024)
    assert excinfo.value.code is CollectorErrorCode.UNAVAILABLE


def test_htp06_http_error_comes_back_as_a_response(monkeypatch: pytest.MonkeyPatch) -> None:
    from urllib.error import HTTPError

    def _not_found(req: Any, timeout: float) -> Any:
        raise HTTPError(
            "https://api.github.com/x",
            404,
            "Not Found",
            {"Content-Type": "application/json"},
            io.BytesIO(b'{"m": 1}'),
        )

    monkeypatch.setattr(_http, "_open", _not_found)
    response = _http.default_transport("https://api.github.com/x", {}, timeout_s=5.0, max_bytes=1024)
    assert response.status == 404
    assert response.body == b'{"m": 1}'


def test_htp07_cross_host_redirect_rejected_same_host_allowed() -> None:
    handler = _http._SameHostRedirectHandler()
    origin = urllib.request.Request("https://api.github.com/x")
    with pytest.raises(CollectorError) as excinfo:
        handler.redirect_request(origin, None, 302, "Found", {}, "https://evil.example.com/y")
    assert excinfo.value.code is CollectorErrorCode.UNAVAILABLE
    result = handler.redirect_request(origin, None, 302, "Found", {}, "https://api.github.com/y")
    assert result is not None
    assert result.full_url == "https://api.github.com/y"
