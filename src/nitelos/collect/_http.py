"""One shared GET-only HTTPS transport for collectors (ADR-015, NIT-020).

The rules enforced here: GET only (no other verb exists on this path);
``https://`` URLs only (plain http is a config error before any request);
TLS verification stays ON (the default verifier); redirects are followed only
WITHIN the original host — a cross-host redirect raises COLLECTOR_UNAVAILABLE
and never leaks the Authorization header to another origin; the body is read
incrementally with a running byte count, so exceeding ``max_bytes`` raises
COLLECTOR_OUTPUT_TOO_LARGE (never silent truncation, never unbounded
buffering); a socket timeout raises COLLECTOR_TIMEOUT; other transport errors
map to COLLECTOR_UNAVAILABLE. Non-2xx statuses are NOT errors here: they come
back as ordinary responses (status, capped body, kept headers) so the caller
maps 401/403/404 semantics itself. Bodies and header values are returned to
the caller only and are never logged.

Collectors receive the transport as an injectable seam (:data:`GetTransport`)
so offline tests replay recorded fixtures (ADR-015 finding 1); the default
here is the only place a socket is opened. Enforcement (timeout, cap) stays
inside this module; injected fakes may bend time and size, which is exactly
what the offline tests exploit.
"""

from __future__ import annotations

import urllib.error
import urllib.request
from collections.abc import Callable, Iterable, Mapping
from typing import Any, NamedTuple, Protocol
from urllib.parse import urlsplit

from nitelos.collect import CollectorError, CollectorErrorCode

_READ_CHUNK = 65_536
#: The response headers collectors may surface (public: collectors and future
#: transports share one allowlist).
KEPT_HEADERS = ("x-ratelimit-remaining", "x-ratelimit-reset", "retry-after", "content-type")


class _HttpReply(Protocol):
    """The slice of urllib's response objects this module touches."""

    def read(self, size: int = -1) -> bytes: ...

    @property
    def status(self) -> int: ...

    @property
    def headers(self) -> Any: ...

    def __enter__(self) -> _HttpReply: ...

    def __exit__(self, *exc_info: object) -> None: ...


class HttpResponse(NamedTuple):
    """A GET response: status, raw body bytes, and the headers we keep."""

    status: int
    body: bytes
    headers: Mapping[str, str]


class _SameHostRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Follow redirects only within the original host (ADR-015)."""

    def redirect_request(  # noqa: PLR0917 - urllib's own fixed signature; type: ignore[override]
        self, req: Any, fp: Any, code: int, msg: str, headers: Any, newurl: str
    ) -> urllib.request.Request | None:
        if urlsplit(newurl).netloc != urlsplit(req.full_url).netloc:
            raise CollectorError(CollectorErrorCode.UNAVAILABLE)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


_OPENER = urllib.request.build_opener(_SameHostRedirectHandler)


def _open(request: urllib.request.Request, timeout: float) -> Any:
    """The one socket-opening call; tests never touch it (injected transports)."""
    return _OPENER.open(request, timeout=timeout)


def _kept_headers(items: Iterable[tuple[str, str]]) -> dict[str, str]:
    return {key: value for key, value in items if key.lower() in KEPT_HEADERS}


def _read_capped(response: Any, max_bytes: int) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = response.read(_READ_CHUNK)
        if not chunk:
            break
        chunks.append(chunk)
        total += len(chunk)
        if total > max_bytes:
            raise CollectorError(CollectorErrorCode.OUTPUT_TOO_LARGE)
    return b"".join(chunks)


def map_http_error(response: HttpResponse) -> None:
    """Map a non-2xx status to a collector code (abstention, never failure).

    Shared table for every HTTP-based collector: 401 -> COLLECTOR_AUTH_MISSING;
    429 or 403-with-X-RateLimit-Remaining:0 (rate limited right now), 404 and
    5xx -> COLLECTOR_UNAVAILABLE; other 4xx -> COLLECTOR_CONFIG_INVALID.
    Non-2xx here means the caller already treats it as an error; a 2xx input
    returns silently.
    """

    if 200 <= response.status < 300:
        return
    remaining = next(
        (value for key, value in response.headers.items() if key.lower() == "x-ratelimit-remaining"),
        None,
    )
    if response.status == 401:
        raise CollectorError(CollectorErrorCode.AUTH_MISSING)
    if response.status == 429 or (response.status == 403 and remaining == "0"):
        raise CollectorError(CollectorErrorCode.UNAVAILABLE)
    if response.status == 404:
        raise CollectorError(CollectorErrorCode.UNAVAILABLE)
    if 500 <= response.status < 600:
        raise CollectorError(CollectorErrorCode.UNAVAILABLE)
    if 400 <= response.status < 500:
        raise CollectorError(CollectorErrorCode.CONFIG_INVALID)
    raise CollectorError(CollectorErrorCode.EXCEPTION)


def default_transport(url: str, headers: Mapping[str, str], timeout_s: float, max_bytes: int) -> HttpResponse:
    """GET ``url`` over TLS and return (status, capped body, kept headers)."""
    if urlsplit(url).scheme != "https":
        raise CollectorError(CollectorErrorCode.CONFIG_INVALID)
    request = urllib.request.Request(  # noqa: S310 - https-only URLs (checked above), GET only
        url, headers=dict(headers), method="GET"
    )
    try:
        with _open(request, timeout_s) as response:
            status = int(response.status)
            body = _read_capped(response, max_bytes)
            kept = _kept_headers(response.headers.items())
    except CollectorError:
        raise
    except urllib.error.HTTPError as error:
        with error:
            body = _read_capped(error, max_bytes)
            return HttpResponse(error.code, body, _kept_headers(error.headers.items()))
    except TimeoutError:
        raise CollectorError(CollectorErrorCode.TIMEOUT) from None
    except OSError as transport_error:
        raise CollectorError(CollectorErrorCode.UNAVAILABLE) from transport_error
    return HttpResponse(status, body, kept)


#: The injectable transport seam every network collector takes in its constructor.
GetTransport = Callable[[str, Mapping[str, str], float, int], HttpResponse]

__all__ = ["GetTransport", "HttpResponse", "KEPT_HEADERS", "default_transport", "map_http_error"]  # noqa: RUF022  # logical grouping
