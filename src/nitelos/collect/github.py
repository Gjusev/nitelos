"""The GitHub collector (plan section F4, NIT-020; extra ``nitelos[github]``).

Read-only GitHub REST GETs through the shared NIT-020 transport
(``nitelos.collect._http`` — https-only, TLS on, same-host redirects only,
incremental size cap, timeout; the transport is injectable so offline tests
replay recorded fixtures and never open a socket). Token from ``GITHUB_TOKEN``
or ``GH_TOKEN``; the token is sent as a bearer header, never logged and never
written into evidence, provenance or stdout. Recommended scopes: a read-only
fine-grained token with Pull requests: read and Checks: read (Contents: read
if you also want branch-protection contexts); the collector performs no
writes ever. The host is fixed to ``api.github.com`` unless ``enterprise_host``
is configured (``https://<host>/api/v3/``).

Endpoints (four GETs): ``/repos/{o}/{r}/pulls/{n}`` (state, merged, draft,
head sha, mergeable_state, base ref), ``/pulls/{n}/reviews`` (review_decision
DERIVED from the latest APPROVED/CHANGES_REQUESTED review per reviewer — an
approximation of GraphQL's review_decision, kept REST-only per the plan),
``/commits/{sha}/check-runs`` (per-check name/status/conclusion), and
``/branches/{base}/protection/required_status_checks`` (the required
contexts). ``checks_all_green`` is computed from REQUIRED checks only: every
required context must have a completed check-run with conclusion success. If
branch protection is unreadable (403/404 — e.g. no admin scope), the required
set is unknown and ``checks_all_green``/``required_checks`` are null rather
than guessed; a 404 on check-runs simply yields no checks.

Errors become structured results — abstention downstream, never failure: 401
→ COLLECTOR_AUTH_MISSING; rate limit (403 with X-RateLimit-Remaining: 0, or
429) → COLLECTOR_UNAVAILABLE; 404 → COLLECTOR_UNAVAILABLE; a missing token →
COLLECTOR_AUTH_MISSING; other 4xx → COLLECTOR_CONFIG_INVALID; 5xx →
COLLECTOR_UNAVAILABLE. The observation data sits under ``/github/pr/...``.
"""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from pydantic import Field

from nitelos.collect import (
    CollectionResult,
    CollectorCapabilities,
    CollectorConfig,
    CollectorError,
    CollectorErrorCode,
    ProvenanceRecord,
)
from nitelos.collect._http import GetTransport, HttpResponse, default_transport
from nitelos.schemas import Evidence as _EvidenceFactory
from nitelos.schemas import canonical_json

__all__ = ["COLLECTOR", "GithubCollector", "GithubConfig"]

_API_VERSION = "2022-11-28"


class GithubConfig(CollectorConfig):
    """Kind config: which pull request, and an optional GitHub Enterprise host."""

    owner: str = Field(min_length=1, max_length=100)
    repo: str = Field(min_length=1, max_length=100)
    pr_number: int = Field(ge=1, le=100_000_000)
    enterprise_host: str | None = Field(default=None, min_length=1, max_length=253)


class GithubCollector:
    """Read-only collector over one pull request's GitHub REST state."""

    config_model = GithubConfig

    def __init__(self, *, transport: GetTransport | None = None) -> None:
        self._transport = transport or default_transport

    @property
    def id(self) -> str:
        return "github"

    @property
    def version(self) -> str:
        return "0.1.0"

    @property
    def capabilities(self) -> CollectorCapabilities:
        return CollectorCapabilities(evidence_kinds=("observation",))

    def collect(self, config: CollectorConfig) -> CollectionResult:
        cfg = config if isinstance(config, GithubConfig) else GithubConfig.model_validate(config.model_dump())
        token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
        if not token:
            raise CollectorError(CollectorErrorCode.AUTH_MISSING)
        base = f"https://{cfg.enterprise_host}/api/v3" if cfg.enterprise_host else "https://api.github.com"
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": _API_VERSION,
        }
        repo_base = f"{base}/repos/{cfg.owner}/{cfg.repo}"
        bodies: dict[str, HttpResponse] = {}

        def get(key: str, url: str, *, tolerate: tuple[int, ...] = ()) -> HttpResponse | None:
            response = self._transport(url, headers, cfg.limits.timeout_s, cfg.limits.max_raw_bytes)
            if 200 <= response.status < 300:
                bodies[key] = response
                return response
            if response.status in tolerate:
                return None
            _map_http_error(response)
            return None  # unreachable: _map_http_error always raises

        pr_response = get("pull_request", f"{repo_base}/pulls/{cfg.pr_number}")
        if pr_response is None:  # pragma: no cover - _map_http_error always raises
            raise CollectorError(CollectorErrorCode.UNAVAILABLE)
        pr = json.loads(pr_response.body)
        head_sha = str(pr.get("head", {}).get("sha") or "")
        base_ref = str(pr.get("base", {}).get("ref") or "")

        checks_response = (
            get("check_runs", f"{repo_base}/commits/{head_sha}/check-runs", tolerate=(404,))
            if head_sha
            else None
        )
        checks_document = json.loads(checks_response.body) if checks_response else {"check_runs": []}
        checks = [
            {
                "name": str(run.get("name", "")),
                "status": str(run.get("status", "")),
                "conclusion": run.get("conclusion"),
            }
            for run in checks_document.get("check_runs", [])
        ]

        protection_response = (
            get(
                "protection",
                f"{repo_base}/branches/{base_ref}/protection/required_status_checks",
                tolerate=(403, 404),
            )
            if base_ref
            else None
        )
        required: list[str] | None = None
        if protection_response is not None:
            contexts = json.loads(protection_response.body).get("contexts")
            if isinstance(contexts, list):
                required = [str(context) for context in contexts]

        reviews_response = get("reviews", f"{repo_base}/pulls/{cfg.pr_number}/reviews")
        if reviews_response is None:  # pragma: no cover - _map_http_error always raises
            raise CollectorError(CollectorErrorCode.UNAVAILABLE)
        reviews = json.loads(reviews_response.body)

        all_green: bool | None = None
        if required is not None:
            by_name = {check["name"]: check for check in checks}
            all_green = all(
                by_name.get(context, {}).get("status") == "completed"
                and by_name.get(context, {}).get("conclusion") == "success"
                for context in required
            )

        data: dict[str, Any] = {
            "github": {
                "pr": {
                    "state": pr.get("state"),
                    "merged": pr.get("merged"),
                    "draft": pr.get("draft"),
                    "head_sha": head_sha or None,
                    "mergeable_state": pr.get("mergeable_state"),
                    "review_decision": _review_decision(reviews),
                    "checks": checks,
                    "required_checks": required,
                    "checks_all_green": all_green,
                }
            }
        }
        item = _EvidenceFactory.observation(
            id=cfg.evidence_id,
            sequence=cfg.sequence_start,
            captured_at=datetime.now(UTC),
            checkpoint_id=cfg.checkpoint_id,
            source_id=self.id,
            subject=cfg.subject,
            phase="final",
            channel="external_api",
            data=data,
        )
        blob = b"".join(response.body for response in bodies.values())
        record = ProvenanceRecord(
            evidence_id=item.id,
            collector_id=self.id,
            collector_version=self.version,
            source="GitHub REST (read-only GET)",
            invocation=f"GET {repo_base} (pull request {cfg.pr_number}: {', '.join(sorted(bodies))})",
            captured_at=item.captured_at,
            subject=cfg.subject,
            sha256=hashlib.sha256(blob).hexdigest(),
            raw_bytes=len(blob),
            normalized_bytes=len(canonical_json(data).encode("utf-8")),
        )
        return CollectionResult(
            collector_id=self.id,
            collector_version=self.version,
            evidence=(item,),
            provenance=(record,),
        )


def _map_http_error(response: HttpResponse) -> None:
    """Map non-2xx statuses to collector codes (abstention, never failure)."""
    if 200 <= response.status < 300:
        return
    remaining = next(
        (value for key, value in response.headers.items() if key.lower() == "x-ratelimit-remaining"),
        None,
    )
    if response.status == 401:
        raise CollectorError(CollectorErrorCode.AUTH_MISSING)
    if response.status == 429 or (response.status == 403 and remaining == "0"):
        raise CollectorError(CollectorErrorCode.UNAVAILABLE)  # rate limited right now
    if response.status == 404:
        raise CollectorError(CollectorErrorCode.UNAVAILABLE)
    if 500 <= response.status < 600:
        raise CollectorError(CollectorErrorCode.UNAVAILABLE)
    if 400 <= response.status < 500:
        raise CollectorError(CollectorErrorCode.CONFIG_INVALID)
    raise CollectorError(CollectorErrorCode.EXCEPTION)


def _review_decision(reviews: Any) -> str | None:
    """Derive APPROVED / CHANGES_REQUESTED / REVIEW_REQUIRED from REST reviews.

    The latest APPROVED or CHANGES_REQUESTED review per reviewer wins;
    APPROVED requires at least one approval and no outstanding change
    request. An approximation of GraphQL's review_decision, kept REST-only
    per the plan.
    """
    if not isinstance(reviews, list) or not reviews:
        return None
    latest: dict[str, str] = {}
    for review in reviews:
        if not isinstance(review, Mapping):
            continue
        state = str(review.get("state", ""))
        if state in ("APPROVED", "CHANGES_REQUESTED"):
            login = str(review.get("user", {}).get("login", ""))
            if login:
                latest[login] = state
    if "CHANGES_REQUESTED" in latest.values():
        return "CHANGES_REQUESTED"
    if "APPROVED" in latest.values():
        return "APPROVED"
    return "REVIEW_REQUIRED"


COLLECTOR = GithubCollector()
