"""Langfuse reporting for nitelos verdicts (extra ``langfuse``; Project 1B).

Authority: docs/planning/20-hooks-and-langfuse-research.md (recommended design
item 1 and 4). This module only *reports*: it writes one categorical score per
verification result and never changes a decision, never reads agent content
beyond what the caller passes in, and sends no raw page content — the same
privacy rule as the OTel export (``nitelos.integrations.otel``): only
allowlisted codes, counts, ids and truncated digests leave the process.

The Langfuse SDK is imported lazily inside functions, so importing this module
offline (without the extra installed) never imports ``langfuse`` and tests run
against fake clients. Callers may pass any object exposing ``create_score``
(the SDK v5 ``Langfuse`` client shape; ``create_score`` is unchanged from v4)
or use :func:`get_langfuse_client` for the default client.

Score design (research section 4):

- categorical score ``nitelos_outcome`` with values ``success`` / ``failure`` /
  ``abstained`` — the three members of :class:`nitelos.schemas.Decision`;
- ``score_id`` is the nitelos verification id, which the API documents as an
  idempotency key, so re-recording the same verification is a no-op;
- observation-level scores pass BOTH ``trace_id`` and ``observation_id``
  (SDK v5 requirement); a ``config_id`` may be supplied to enforce the
  category set defined by :func:`ensure_score_config`;
- evidence references (criterion ids, evidence ids, truncated sha256 digests,
  reason codes) go into the score ``comment`` — conservative resolution of
  research question Q2: the documented ``create_score()`` signature has no
  ``metadata`` parameter. When the client's signature does accept ``metadata``
  (the public API schema has it), the bounded payload from
  :func:`metadata_payload` is sent there too; every value is capped at 200
  characters and honestly truncated. Q1 (no documented comment limit) is
  resolved by keeping the comment short and deterministic anyway.
"""

from __future__ import annotations

import inspect
import json
from typing import Any

from nitelos.schemas import Decision, VerificationResult

_SCORE_NAME = "nitelos_outcome"
# Langfuse metadata values are capped at 200 characters as JSON (SDK v5/v6
# docs; string values at most 198). We truncate honestly and say so.
_METADATA_VALUE_CAP = 198
_TRUNCATION_MARKER = "...[truncated]"
_COMMENT_CAP = 480
_MAX_EVIDENCE_REFS = 6
_MAX_REASON_CODES = 6
_MAX_CRITERIA_SHOWN = 8
# categories mirror the Decision enum; numeric values per research 2.2.2
SCORE_CONFIG_CATEGORIES: tuple[dict[str, Any], ...] = (
    {"label": "success", "value": 1},
    {"label": "failure", "value": 0},
    {"label": "abstained", "value": -1},
)


class LangfuseNotInstalled(ImportError):
    """Raised when the langfuse SDK is needed but the extra is absent."""


def _require_langfuse() -> Any:
    try:
        import langfuse  # noqa: PLC0415 - lazy: keeps the SDK optional (extra `langfuse`)
    except ImportError:
        raise LangfuseNotInstalled(
            "nitelos.integrations.langfuse requires the langfuse extra; "
            'install it with: pip install "nitelos[langfuse]"'
        ) from None
    return langfuse


def get_langfuse_client() -> Any:
    """Return the default Langfuse client (SDK ``get_client()``), lazily."""
    langfuse = _require_langfuse()
    return langfuse.get_client()


def _decision_value(result: VerificationResult) -> str:
    """Map a finished verification to its categorical score value."""
    if result.execution_status != "ok" or result.decision is None:
        raise ValueError(
            "record_verdict needs a verification with execution_status 'ok'; "
            "score non-ok executions as 'abstained' explicitly at the call site"
        )
    return str(Decision(result.decision))


def _short(value: str, cap: int = _METADATA_VALUE_CAP) -> str:
    if len(value) <= cap:
        return value
    keep = max(0, cap - len(_TRUNCATION_MARKER))
    return value[:keep] + _TRUNCATION_MARKER


def metadata_payload(result: VerificationResult) -> dict[str, str]:
    """Bounded, structured evidence references for the score ``metadata`` field.

    Every value is a string of at most 198 characters (the documented 200-char
    as-JSON cap for metadata values); over-long values are truncated with an
    explicit ``...[truncated]`` marker, never silently.
    """
    cited: list[str] = []
    for criterion in result.criteria:
        for ref in criterion.evidence_refs:
            cited.append(f"{criterion.criterion_id}:{ref.evidence_id}")
    payload = {
        "verification_id": str(result.verification_id),
        "request_id": str(result.request_id or ""),
        "reason_codes": _short(",".join(result.reason_codes[:_MAX_REASON_CODES])),
        "evidence_refs": _short(",".join(cited[:_MAX_EVIDENCE_REFS])),
        "criteria": _short(",".join(str(c.criterion_id) for c in result.criteria[:_MAX_CRITERIA_SHOWN])),
    }
    return {key: _short(value) for key, value in payload.items()}


def evidence_comment(result: VerificationResult) -> str:
    """Deterministic one-line human comment: failed/unknown criteria, refs, codes.

    Kept short and structured because the comment length limit is undocumented
    (research Q1); raw evidence content and page text are never included.
    """
    parts: list[str] = [f"nitelos verdict: {result.decision}"]
    undecided: list[str] = []
    cited: list[str] = []
    for criterion in result.criteria:
        if str(criterion.state) in ("refuted", "unknown"):
            undecided.append(f"{criterion.criterion_id}:{criterion.state}")
        for ref in criterion.evidence_refs:
            cited.append(f"{criterion.criterion_id}:{ref.evidence_id}")
    if undecided:
        parts.append("criteria=" + ",".join(undecided[:_MAX_CRITERIA_SHOWN]))
    if cited:
        parts.append("evidence=" + ",".join(cited[:_MAX_EVIDENCE_REFS]))
    if result.reason_codes:
        parts.append("codes=" + ",".join(result.reason_codes[:_MAX_REASON_CODES]))
    return _short("; ".join(parts), _COMMENT_CAP)


def _supports_metadata(client: Any) -> bool:
    """True when the client's ``create_score`` accepts a ``metadata`` kwarg.

    Conservative resolution of research Q2: the documented SDK signature shows
    no ``metadata`` parameter, so evidence ids live in the comment unless the
    client clearly supports the field.
    """
    try:
        signature = inspect.signature(client.create_score)
    except (TypeError, ValueError, AttributeError):
        return False
    params = signature.parameters
    if any(parameter.kind is inspect.Parameter.VAR_KEYWORD for parameter in params.values()):
        return True
    return "metadata" in params


def record_verdict(
    result: VerificationResult,
    trace_id: str,
    observation_id: str | None = None,
    *,
    client: Any | None = None,
    name: str = _SCORE_NAME,
    config_id: str | None = None,
) -> str:
    """Write the categorical outcome score for one verification result.

    ``result`` must have ``execution_status == "ok"`` (non-ok executions carry
    no decision; score them as ``"abstained"`` explicitly). ``score_id`` is the
    nitelos verification id — the documented idempotency key — so calling this
    twice for the same verification updates nothing semantically.

    Returns the score value written. Never sends raw evidence or page content.
    """
    if client is None:
        client = get_langfuse_client()
    value = _decision_value(result)
    kwargs: dict[str, Any] = {
        "name": name,
        "value": value,
        "trace_id": trace_id,
        "data_type": "CATEGORICAL",
        "score_id": str(result.verification_id),
        "comment": evidence_comment(result),
    }
    if observation_id is not None:
        kwargs["observation_id"] = observation_id
    if config_id is not None:
        kwargs["config_id"] = config_id
    if _supports_metadata(client):
        # Q2: only when the client exposes the API-level metadata field.
        kwargs["metadata"] = metadata_payload(result)
    client.create_score(**kwargs)
    return value


def ensure_score_config(client: Any, name: str = _SCORE_NAME) -> str | None:
    """Create the categorical score config if absent; return its ``config_id``.

    Reads existing configs first and creates with categories
    ``success=1 / failure=0 / abstained=-1`` only when the name is missing;
    a create-conflict (raced create) is tolerated by re-reading. Configs are
    never PATCHed (conservative resolution of research Q3: treat them as
    immutable; if the categories drift, surface it instead of silently
    rewriting a shared server-side config).

    Works with both SDK v4 and v5 client shapes (``client.api.score_configs``
    or ``client.api.score_configs.get``/``create``); with SDK v5 the create
    call may take the request object — both call shapes are attempted.
    """
    api = getattr(client, "api", None)
    configs_api = getattr(api, "score_configs", None) if api is not None else None
    if configs_api is None or not hasattr(configs_api, "get"):
        raise TypeError("client must expose api.score_configs.get/create (Langfuse SDK)")
    existing = _find_config(configs_api, name)
    if existing is not None:
        return existing
    create = configs_api.create
    payload: dict[str, Any] = {
        "name": name,
        "dataType": "CATEGORICAL",
        "categories": list(SCORE_CONFIG_CATEGORIES),
    }
    try:
        try:
            created = create(**payload)
        except TypeError:
            # SDK v5 low-level API takes a request object list/instance
            created = create(payload)
    except Exception:
        # raced create or archived-config conflict: re-read before giving up
        existing = _find_config(configs_api, name)
        if existing is not None:
            return existing
        raise
    return str(
        getattr(created, "id", None) or (created.get("id") if isinstance(created, dict) else None) or ""
    )


def _find_config(configs_api: Any, name: str) -> str | None:
    try:
        page = configs_api.get()
    except Exception:  # noqa: BLE001 - an unreadable configs endpoint degrades to 'absent'
        return None
    items = getattr(page, "data", None)
    if items is None and isinstance(page, dict):
        items = page.get("data", [])
    for item in items or []:
        if getattr(item, "name", None) == name or (isinstance(item, dict) and item.get("name") == name):
            item_id = getattr(item, "id", None) or (item.get("id") if isinstance(item, dict) else None)
            return str(item_id) if item_id else None
    return None


# ---------------------------------------------------------------------------
# backfill: read existing traces via the public API, re-verify, write scores
# ---------------------------------------------------------------------------


def __getattr__(name: str) -> Any:  # PEP 562: lazy re-export, no side-effect imports
    if name == "PublicApiTransport":
        from nitelos.collect.langfuse_api import PublicApiTransport  # noqa: PLC0415 - network code lives in collect (BND-03)

        return PublicApiTransport
    raise AttributeError(name)


def iter_observation_pages(
    transport: Any,
    *,
    fields: str = "core,basic,metadata,trace_context",
    page_size: int = 100,
    max_pages: int = 100,
) -> list[dict[str, Any]]:
    """Fetch all observation rows for ``nitelos.verify`` spans, cursor-based.

    Research 2.4: only a missing ``meta.cursor`` ends iteration (a page can be
    short or empty while a cursor is present); the ``fields`` groups select the
    documented subsets. ``name`` / ``since`` filtering is applied client-side
    on the returned rows (open question Q10: the exact server-side ``filter``
    shape for v2 observations was not exercised live; client-side filtering
    keeps this honest). Freshness caveat: rows from exporters that do not send
    ``x-langfuse-ingestion-version: 4`` can lag up to 15 minutes.
    """
    rows: list[dict[str, Any]] = []
    cursor: str | None = None
    for _ in range(max_pages):
        params: dict[str, str] = {"fields": fields, "limit": str(page_size)}
        if cursor:
            params["cursor"] = cursor
        page = transport.request("GET", "/api/public/v2/observations", params)
        rows.extend(page.get("data", []))
        cursor = (page.get("meta") or {}).get("cursor")
        if not cursor:
            break
    else:
        raise RuntimeError(f"backfill stopped after {max_pages} pages (raise max_pages to go further)")
    return rows


def group_by_trace(
    rows: list[dict[str, Any]], *, name: str = "nitelos.verify", since: str | None = None
) -> dict[str, list[dict[str, Any]]]:
    """Group rows by ``traceId`` keeping only ``nitelos.verify`` spans; filter ``since``.

    ``since`` is an ISO-8601 timestamp compared lexically against the row's
    ``startTime`` (both ISO strings, so lexicographic order equals time order
    for the same timezone format the API emits).
    """
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        if str(row.get("name", "")) != name:
            continue
        if since is not None and str(row.get("startTime", "")) < since:
            continue
        trace_id = str(row.get("traceId", ""))
        if trace_id:
            grouped.setdefault(trace_id, []).append(row)
    return grouped


def trace_evidence(
    trace_id: str, rows: list[dict[str, Any]], *, checkpoint_id: str = "backfill", max_rows: int = 32
) -> Any:
    """Build one nitelos observation-evidence item from a trace's verify spans.

    ``data`` carries the bounded observation rows (no raw page content beyond
    what Langfuse already returned in the ``metadata`` group); pointers in the
    criterion file reference ``/observations/<index>/<field>``. Trust: built by
    the host (backfill process) from the API response, channel ``external_api``,
    exactly like the collector framework's observations.
    """
    from nitelos.evidence import build_observation  # noqa: PLC0415 - lazy: hashing machinery
    from nitelos.schemas import Channel  # noqa: PLC0415

    kept = rows[:max_rows]
    start_times = [str(row.get("startTime", "")) for row in kept if row.get("startTime")]
    data = {
        "trace_id": trace_id,
        "observations": [
            {
                "id": str(row.get("id", "")),
                "name": str(row.get("name", "")),
                "startTime": str(row.get("startTime", "")),
                "endTime": str(row.get("endTime", "")),
                "type": str(row.get("type", "")),
                "metadata": row.get("metadata") or {},
            }
            for row in kept
        ],
        "truncated_count": max(0, len(rows) - len(kept)),
    }
    return build_observation(
        id=_safe_id(trace_id),
        sequence=0,
        captured_at=start_times[0] if start_times else "1970-01-01T00:00:00Z",
        checkpoint_id=checkpoint_id,
        source_id="langfuse-backfill",
        subject={"trace_id": _safe_id(trace_id)},
        phase="final",
        channel=Channel.EXTERNAL_API,
        data=data,
    )


def _safe_id(raw: str) -> str:
    from nitelos.schemas import _ID_RE  # noqa: PLC0415

    cleaned = "".join(ch if ch.isalnum() or ch in "_.:-" else "-" for ch in raw)[:128]
    if _ID_RE.fullmatch(cleaned) is None:
        cleaned = "trace-" + "".join(ch for ch in cleaned if ch.isalnum())[:100]
    return cleaned


def _existing_score_ids(transport: Any, trace_id: str, name: str) -> set[str]:
    """Score ids already recorded for this trace+score name (empty when unknown).

    A failed read (undocumented/changed scores endpoint, permissions) degrades
    to "cannot check": the set stays empty and idempotency still holds through
    ``score_id`` being the verification id (an upsert key server-side).
    """
    try:
        page = transport.request(
            "GET", "/api/public/scores", {"traceId": trace_id, "name": name, "limit": "100"}
        )
    except Exception:  # noqa: BLE001 - a failed scores read degrades to 'cannot check' (see docstring)
        return set()
    return {str(item.get("id", "")) for item in page.get("data", [])}


def run_backfill(
    transport: Any,
    client: Any,
    criteria: dict[str, Any],
    *,
    since: str | None = None,
    dry_run: bool = False,
    force: bool = False,
    score_name: str = _SCORE_NAME,
    config_id: str | None = None,
    max_traces: int = 500,
) -> dict[str, int]:
    """Re-verify ``nitelos.verify`` traces against a criterion file and score them.

    Idempotent: traces that already carry a score with ``score_name`` are
    skipped unless ``force``. Returns counts per verdict (``success``,
    ``failure``, ``abstained``, plus ``skipped``). Prints nothing; the CLI
    renders the counts.
    """
    from nitelos import Verifier  # noqa: PLC0415
    from nitelos.policy import TrustBinding  # noqa: PLC0415
    from nitelos.schemas import parse_request  # noqa: PLC0415

    rows = iter_observation_pages(transport)
    grouped = group_by_trace(rows, since=since)
    counts = {"success": 0, "failure": 0, "abstained": 0, "skipped": 0, "error": 0}

    for index, (trace_id, trace_rows) in enumerate(sorted(grouped.items())):
        if index >= max_traces:
            break
        if not force and _existing_score_ids(transport, trace_id, score_name):
            counts["skipped"] += 1
            continue
        evidence_item = trace_evidence(trace_id, trace_rows)
        if all(not row.get("metadata") for row in trace_rows):
            # no evidence available in the trace at all: record nothing, count abstained
            counts["abstained"] += 1
            continue
        # The backfill builds exactly one evidence bundle per trace; every
        # criterion in the file evaluates against it (pointers reference
        # /observations/<index>/<field> in that bundle).
        criteria_maps = []
        for raw in criteria.get("criteria", []):
            entry = dict(raw)
            # The backfill builds exactly one evidence bundle per trace; every
            # criterion evaluates against it (pointers reference
            # /observations/<index>/<field> in that bundle) under the bundle's
            # subject — the file's own subject names are rewritten to match.
            entry["evidence_ids"] = [evidence_item.id]
            entry["subject"] = dict(evidence_item.subject)
            criteria_maps.append(entry)
        wire_evidence = [json.loads(evidence_item.model_dump_json(exclude_none=True))]
        request_wire = {
            "schema_version": "1",
            "request_id": f"backfill-{_safe_id(trace_id)}",
            "objective": "Langfuse backfill verification",
            "checkpoint_id": "backfill",
            "as_of": trace_rows[0].get("startTime") or "1970-01-01T00:00:00Z",
            "criteria": criteria_maps,
            "evidence": wire_evidence,
            "metadata": {"profile": criteria.get("profile", "backfill")},
        }
        try:
            request = parse_request(json.dumps(request_wire))
        except Exception:  # noqa: BLE001 - unparseable trace bundle abstains, never crashes the backfill
            counts["abstained"] += 1
            continue
        # host bindings: the backfill process fetched these rows itself
        # (ADR-015 finding 4 — same authority rule as host_trust_bindings).
        bindings = (
            TrustBinding(
                evidence_id=evidence_item.id,
                sha256=evidence_item.sha256,
                source_id=evidence_item.source_id,
                subject=dict(evidence_item.subject),
                checkpoint_id=evidence_item.checkpoint_id,
            ),
        )
        result = Verifier(trust_bindings=bindings).verify(request)
        if result.execution_status != "ok" or result.decision is None:
            counts["abstained"] += 1
            continue
        decision = str(result.decision)
        counts[decision] += 1
        if not dry_run:
            record_verdict(result, trace_id, client=client, name=score_name, config_id=config_id)
    return counts


def load_criteria_file(path: Any) -> dict[str, Any]:
    """Load a criteria file for backfill: strict JSON, or YAML when parseable.

    The parsed mapping is validated against the same strict criteria schema
    the hooks use (:class:`nitelos.claude_code.CriteriaFile`), then returned
    as a plain dict. YAML support needs PyYAML; the error names the install
    command honestly (the core stays dependency-free).
    """
    import json as _json  # noqa: PLC0415
    from pathlib import Path  # noqa: PLC0415

    from nitelos.claude_code import CriteriaFile  # noqa: PLC0415

    text = Path(path).read_text(encoding="utf-8")
    try:
        loaded: object = _json.loads(text)
    except ValueError:
        try:
            import yaml  # noqa: PLC0415 - lazy: only needed for YAML criteria files
        except ImportError:
            raise ImportError(
                "criteria file is YAML but PyYAML is not installed; "
                'install it with: pip install "nitelos[hooks]"'
            ) from None
        loaded = yaml.safe_load(text)
    if not isinstance(loaded, dict):
        raise ValueError(f"criteria file must contain a mapping: {path}")
    return CriteriaFile.model_validate(loaded).model_dump()


def render_backfill_summary(counts: dict[str, int]) -> str:
    """One line per verdict plus a total, for the CLI printout."""
    total = sum(counts.values())
    lines = [f"{key}: {value}" for key, value in sorted(counts.items()) if value]
    lines.append(f"total: {total}")
    return "\n".join(lines)


__all__ = [
    "SCORE_CONFIG_CATEGORIES",
    "PublicApiTransport",  # noqa: F822 - provided via the module __getattr__ (lazy re-export)
    "ensure_score_config",
    "evidence_comment",
    "get_langfuse_client",
    "group_by_trace",
    "iter_observation_pages",
    "load_criteria_file",
    "metadata_payload",
    "record_verdict",
    "render_backfill_summary",
    "run_backfill",
    "trace_evidence",
]
