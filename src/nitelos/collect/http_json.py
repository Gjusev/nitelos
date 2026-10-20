"""The HTTP JSON collector (plan F5, NIT-021; extra ``http``).

One GET to a host-pinned https URL through the shared NIT-020 transport
(``nitelos.collect._http`` — https-only, TLS on, same-host redirects only,
incremental size cap, timeout; injectable transport for offline tests).
The URL and the JSON pointers to extract are HOST configuration; the agent
never chooses where requests go. The observation exposes the status code,
the transport-kept headers (the allowlist lives in ``_http._KEPT_HEADERS``)
and the values at the configured pointers (null when a pointer is absent —
missing is a value, not an error). Non-2xx maps through the collector error
table (401 AUTH_MISSING; 404/5xx UNAVAILABLE; other 4xx CONFIG_INVALID); a
non-JSON body or a JSON non-object root is COLLECTOR_EXCEPTION. Response
values never enter provenance or logs; the raw digest covers the response
body bytes.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit

from pydantic import Field, field_validator

from nitelos.collect import (
    CollectionResult,
    CollectorCapabilities,
    CollectorConfig,
    CollectorError,
    CollectorErrorCode,
    ProvenanceRecord,
)
from nitelos.collect._http import (
    _KEPT_HEADERS,
    GetTransport,
    default_transport,
)
from nitelos.collect.github import _map_http_error
from nitelos.schemas import Evidence as _EvidenceFactory
from nitelos.schemas import JsonPointerType, canonical_json

__all__ = ["COLLECTOR", "HttpJsonCollector", "HttpJsonConfig"]


class HttpJsonConfig(CollectorConfig):
    """Kind config: one https URL and the pointers to extract."""

    url: str = Field(min_length=8, max_length=2048)
    pointers: tuple[JsonPointerType, ...] = Field(min_length=1, max_length=32)

    @field_validator("url")
    @classmethod
    def _https_only(cls, value: str) -> str:
        if urlsplit(value).scheme != "https" or not urlsplit(value).netloc:
            raise ValueError("url must be an absolute https:// URL")
        return value


def _walk(document: Any, pointer: str) -> Any:
    node = document
    for raw_token in pointer.lstrip("/").split("/") if pointer.lstrip("/") else []:
        token = raw_token.replace("~1", "/").replace("~0", "~")
        if isinstance(node, dict):
            node = node.get(token)
        elif isinstance(node, list) and token.isdigit():
            index = int(token)
            node = node[index] if index < len(node) else None
        else:
            return None
        if node is None:
            return None
    return node


class HttpJsonCollector:
    """Read-only collector over one HTTP JSON document."""

    def __init__(self, *, transport: GetTransport | None = None) -> None:
        self._transport = transport or default_transport

    id = "http"
    version = "0.1.0"
    capabilities = CollectorCapabilities(evidence_kinds=("observation",))
    config_model = HttpJsonConfig

    def collect(self, config: CollectorConfig) -> CollectionResult:
        cfg = (
            config
            if isinstance(config, HttpJsonConfig)
            else HttpJsonConfig.model_validate(config.model_dump())
        )
        response = self._transport(cfg.url, {}, cfg.limits.timeout_s, cfg.limits.max_raw_bytes)
        if not 200 <= response.status < 300:
            _map_http_error(response)
        try:
            document = json.loads(response.body)
        except ValueError:
            raise CollectorError(CollectorErrorCode.EXCEPTION) from None
        if not isinstance(document, dict):
            raise CollectorError(CollectorErrorCode.EXCEPTION)
        values = {pointer: _walk(document, pointer) for pointer in cfg.pointers}
        data = {
            "http": {
                "status_code": response.status,
                "headers": {
                    key: value
                    for key, value in dict(response.headers).items()
                    if key.lower() in _KEPT_HEADERS
                },
                "values": values,
            }
        }
        captured_at = datetime.now(UTC)
        item = _EvidenceFactory.observation(
            id=cfg.evidence_id,
            sequence=cfg.sequence_start,
            captured_at=captured_at,
            checkpoint_id=cfg.checkpoint_id,
            source_id=self.id,
            subject=cfg.subject,
            phase="final",
            channel="external_api",
            data=data,
        )
        record = ProvenanceRecord(
            evidence_id=item.id,
            collector_id=self.id,
            collector_version=self.version,
            source="HTTP JSON document (shared GET transport)",
            invocation=f"GET {cfg.url}",
            captured_at=captured_at,
            subject=cfg.subject,
            sha256=hashlib.sha256(response.body).hexdigest(),
            raw_bytes=len(response.body),
            normalized_bytes=len(canonical_json(data).encode("utf-8")),
        )
        return CollectionResult(
            collector_id=self.id,
            collector_version=self.version,
            evidence=(item,),
            provenance=(record,),
        )


COLLECTOR = HttpJsonCollector()
