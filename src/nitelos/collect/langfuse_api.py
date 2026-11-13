"""Minimal stdlib transport for the Langfuse public API (Project 1B backfill).

Lives under ``nitelos.collect`` because that is the only place where network
and process side-effect imports are allowed (test boundary BND-03): the
backfill reads observations and scores over HTTP with :mod:`urllib.request`,
basic-authenticated with the Langfuse public keys. Read-only GETs only; the
cursor-pagination and field-group parameters follow the documented
``GET /api/public/v2/observations`` contract (research section 2.4). Tests
inject a fake with the same ``request`` interface and never construct this.
"""

from __future__ import annotations

import base64
import json
import os
import urllib.parse
import urllib.request
from typing import Any


class PublicApiTransport:
    """Basic-auth GET transport for the Langfuse public API.

    Credentials come from the environment (``LANGFUSE_HOST``,
    ``LANGFUSE_PUBLIC_KEY``, ``LANGFUSE_SECRET_KEY``) unless given explicitly.
    """

    def __init__(
        self,
        *,
        host: str | None = None,
        public_key: str | None = None,
        secret_key: str | None = None,
    ) -> None:
        self.host = (host or os.environ.get("LANGFUSE_HOST") or "https://cloud.langfuse.com").rstrip("/")
        public = public_key or os.environ.get("LANGFUSE_PUBLIC_KEY") or ""
        secret = secret_key or os.environ.get("LANGFUSE_SECRET_KEY") or ""
        if not public or not secret:
            raise ValueError(
                "backfill needs LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY "
                "(and LANGFUSE_HOST) in the environment"
            )
        self._auth = "Basic " + base64.b64encode(f"{public}:{secret}".encode()).decode("ascii")

    def request(self, method: str, path: str, params: dict[str, str] | None = None) -> dict[str, Any]:
        url = self.host + path
        if params:
            url += "?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(  # noqa: S310 - https-only: the host comes from LANGFUSE_HOST
            url, method=method, headers={"Authorization": self._auth, "Accept": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=30) as response:  # noqa: S310 - same https-only rule
            body = response.read().decode("utf-8")
        return json.loads(body) if body else {}
