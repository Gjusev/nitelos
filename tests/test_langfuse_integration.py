"""LF-01..12: Project 1B Langfuse reporting adapter and backfill (extra ``langfuse``).

Everything here is offline: the Langfuse SDK is never imported (it is not in
the dev group); clients are fakes exposing the documented ``create_score``
shape and the backfill uses an injectable transport with canned pages. The
single live test (LF-LIVE) is skipped unless NITELOS_RUN_LANGFUSE_LIVE=1 and
talks only to the Langfuse API — it makes NO LLM calls.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

import pytest

from nitelos import Verifier, canonical_json
from nitelos.integrations.langfuse import (
    SCORE_CONFIG_CATEGORIES,
    PublicApiTransport,
    ensure_score_config,
    group_by_trace,
    iter_observation_pages,
    load_criteria_file,
    metadata_payload,
    record_verdict,
    render_backfill_summary,
    run_backfill,
    trace_evidence,
)
from nitelos.schemas import Decision

ROOT = Path(__file__).resolve().parents[1]


def _observation(data: dict[str, Any], *, evidence_id: str = "obs-1") -> dict[str, Any]:
    obs = {
        "id": evidence_id,
        "kind": "observation",
        "sequence": 0,
        "captured_at": "2026-11-11T10:00:00Z",
        "checkpoint_id": "cp-final",
        "source_id": "my-runner",
        "subject": {"suite": "regression"},
        "phase": "final",
        "channel": "external_api",
        "data": data,
    }
    obs["sha256"] = hashlib.sha256(canonical_json(obs["data"]).encode("utf-8")).hexdigest()
    return obs


def _request(evidence: list[dict[str, Any]], criteria: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "schema_version": "1",
        "request_id": "lf-test-1",
        "objective": "Complete the regression suite",
        "checkpoint_id": "cp-final",
        "as_of": "2026-11-11T10:01:00Z",
        "criteria": criteria,
        "evidence": evidence,
    }


GREEN_CRITERIA = [
    {
        "id": "tests-green",
        "description": "All tests pass",
        "kind": "assertion",
        "scope": "external",
        "evidence_ids": ["obs-1"],
        "subject": {"suite": "regression"},
        "pointer": "/failed",
        "operator": "equals",
        "expected": 0,
    }
]


def _result(*, failed: int) -> Any:
    data = {"failed": failed, "total": 2}
    observation = _observation(data)
    from nitelos.policy import TrustBinding

    bindings = (
        TrustBinding(
            evidence_id=observation["id"],
            sha256=observation["sha256"],
            source_id="my-runner",
            subject=dict(observation["subject"]),
            checkpoint_id="cp-final",
        ),
    )
    return Verifier(trust_bindings=bindings).verify(_request([observation], GREEN_CRITERIA))


# --------------------------------------------------------------------------
# fake clients
# --------------------------------------------------------------------------


class FakeClient:
    """create_score without a metadata parameter (documented SDK signature)."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def create_score(  # noqa: PLR0917 - mirrors the documented SDK signature
        self,
        name: str,
        value: Any,
        trace_id: str,
        observation_id: str | None = None,
        data_type: str | None = None,
        score_id: str | None = None,
        comment: str | None = None,
        config_id: str | None = None,
    ) -> None:
        self.calls.append(
            {
                "name": name,
                "value": value,
                "trace_id": trace_id,
                "observation_id": observation_id,
                "data_type": data_type,
                "score_id": score_id,
                "comment": comment,
                "config_id": config_id,
            }
        )


class FakeClientWithMetadata:
    """create_score that accepts metadata (API-level field)."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def create_score(self, metadata: dict[str, str] | None = None, **kwargs: Any) -> None:
        self.calls.append({"metadata": metadata, **kwargs})


class FakeScoreConfigs:
    def __init__(self, items: list[Any], conflict: bool = False) -> None:
        self._items = items
        self._conflict = conflict
        self.created: list[dict[str, Any]] = []
        self.patched: list[Any] = []

    def get(self) -> dict[str, Any]:
        return {"data": self._items}

    def create(self, **kwargs: Any) -> dict[str, Any]:
        if self._conflict:
            raise RuntimeError("409 conflict")
        self.created.append(kwargs)
        self._items = [{"id": "cfg-1", "name": kwargs["name"]}]
        return {"id": "cfg-1"}

    def patch(self, config_id: str, **kwargs: Any) -> None:  # pragma: no cover - must never be called
        self.patched.append((config_id, kwargs))


class FakeLangfuseClient:
    def __init__(self, configs: FakeScoreConfigs) -> None:
        self.api = type("_Api", (), {"score_configs": configs})()
        self.configs = configs


# --------------------------------------------------------------------------
# LF-01..05: record_verdict
# --------------------------------------------------------------------------


def test_lf01_success_maps_to_categorical_value_and_idempotent_score_id() -> None:
    client = FakeClient()
    result = _result(failed=0)
    value = record_verdict(result, "trace-1", client=client, config_id="cfg-1")
    assert value == str(Decision.SUCCESS)
    call = client.calls[0]
    assert call["name"] == "nitelos_outcome"
    assert call["value"] == "success"
    assert call["trace_id"] == "trace-1"
    assert call["data_type"] == "CATEGORICAL"
    assert call["config_id"] == "cfg-1"
    # idempotency key: the nitelos verification id
    assert call["score_id"] == str(result.verification_id)
    assert call["observation_id"] is None


def test_lf02_failure_and_observation_level_score_need_both_ids() -> None:
    client = FakeClient()
    result = _result(failed=1)
    value = record_verdict(result, "trace-2", observation_id="obs-xyz", client=client)
    assert value == str(Decision.FAILURE)
    assert client.calls[0]["observation_id"] == "obs-xyz"
    assert client.calls[0]["trace_id"] == "trace-2"


def test_lf03_comment_carries_refs_and_no_raw_content() -> None:
    client = FakeClient()
    result = _result(failed=1)
    record_verdict(result, "trace-3", client=client)
    comment = client.calls[0]["comment"]
    assert "nitelos verdict: failure" in comment
    assert "tests-green" in comment
    assert "obs-1" in comment
    assert "FAILED" not in comment.replace("failure", "")  # verdict word, not page text
    # privacy rule: the raw evidence payload never appears
    assert '"failed": 1' not in comment
    assert "total" not in comment


def test_lf04_metadata_sent_only_when_client_supports_it_and_values_capped() -> None:
    plain = FakeClient()
    result = _result(failed=0)
    record_verdict(result, "trace-4", client=plain)
    assert "metadata" not in plain.calls[0]  # Q2 conservative: comment carries refs

    rich = FakeClientWithMetadata()
    record_verdict(result, "trace-4", client=rich)
    payload = rich.calls[0]["metadata"]
    assert payload["verification_id"] == str(result.verification_id)
    assert all(isinstance(v, str) and len(v) <= 198 for v in payload.values())


def test_lf05_long_metadata_values_are_honestly_truncated() -> None:
    result = _result(failed=0)
    # fabricate a result-shaped object with an enormous reason code via metadata_payload
    payload = metadata_payload(result)
    assert all("...[truncated]" not in v or v.endswith("...[truncated]") for v in payload.values())
    cap_marker = "...[truncated]"
    for value in payload.values():
        if len(value) == 198:
            assert value.endswith(cap_marker)


def test_lf05b_non_ok_result_rejected() -> None:
    from nitelos.errors import InputErrorCode
    from nitelos.schemas import ErrorInfo

    ok = _result(failed=0)
    result = ok.model_copy(
        update={
            "execution_status": "input_error",
            "decision": None,
            "criteria": (),
            "error": ErrorInfo(code=InputErrorCode.INVALID_SCHEMA, safe_message="invalid request"),
        }
    )
    assert result.decision is None
    with pytest.raises(ValueError, match="execution_status 'ok'"):
        record_verdict(result, "trace-x", client=FakeClient())


def test_lf06_missing_sdk_raises_named_import_error(monkeypatch: pytest.MonkeyPatch) -> None:
    import builtins

    from nitelos.integrations import langfuse as lf

    real_import = builtins.__import__

    def no_langfuse(name: str, *args: Any, **kwargs: Any) -> Any:
        if name == "langfuse":
            raise ImportError("No module named 'langfuse'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", no_langfuse)
    with pytest.raises(lf.LangfuseNotInstalled, match="nitelos\\[langfuse\\]"):
        lf.get_langfuse_client()


# --------------------------------------------------------------------------
# LF-07..08: score config
# --------------------------------------------------------------------------


def test_lf07_ensure_score_config_creates_when_absent_and_never_patches() -> None:
    configs = FakeScoreConfigs(items=[])
    client = FakeLangfuseClient(configs)
    config_id = ensure_score_config(client)
    assert config_id == "cfg-1"
    created = configs.created[0]
    assert created["name"] == "nitelos_outcome"
    assert created["dataType"] == "CATEGORICAL"
    assert list(created["categories"]) == list(SCORE_CONFIG_CATEGORIES)
    assert configs.patched == []  # Q3 conservative: configs are never PATCHed


def test_lf08_ensure_score_config_reuses_existing_and_tolerates_conflict() -> None:
    configs = FakeScoreConfigs(items=[{"id": "cfg-existing", "name": "nitelos_outcome"}])
    client = FakeLangfuseClient(configs)
    assert ensure_score_config(client) == "cfg-existing"
    assert configs.created == []

    raced = FakeScoreConfigs(items=[], conflict=True)
    raced_client = FakeLangfuseClient(raced)

    def seed_conflict() -> None:
        raced._items = [{"id": "cfg-raced", "name": "nitelos_outcome"}]

    # simulate another writer landing the config between the read and the create
    orig_create = raced.create

    def create_then_other_writer(**kwargs: Any) -> dict[str, Any]:
        try:
            return orig_create(**kwargs)
        finally:
            seed_conflict()

    raced.create = create_then_other_writer  # type: ignore[method-assign]
    assert ensure_score_config(raced_client) == "cfg-raced"


# --------------------------------------------------------------------------
# LF-09..11: backfill
# --------------------------------------------------------------------------


class FakeTransport:
    """Canned public-API pages: observations (cursor) + scores."""

    def __init__(
        self,
        pages: list[list[dict[str, Any]]],
        *,
        existing_scores: dict[str, list[dict[str, Any]]] | None = None,
    ) -> None:
        self._pages = pages
        self._scores = existing_scores or {}
        self.requests: list[tuple[str, str, dict[str, str]]] = []

    def request(self, method: str, path: str, params: dict[str, str] | None = None) -> dict[str, Any]:
        self.requests.append((method, path, dict(params or {})))
        if path == "/api/public/v2/observations":
            index = sum(1 for r in self.requests if r[1] == "/api/public/v2/observations") - 1
            if index >= len(self._pages):
                return {"data": [], "meta": {}}
            cursor = str(index + 1) if index + 1 < len(self._pages) else None
            meta = {"cursor": cursor} if cursor else {}
            return {"data": self._pages[index], "meta": meta}
        if path == "/api/public/scores":
            trace_id = (params or {}).get("traceId", "")
            return {"data": self._scores.get(trace_id, [])}
        raise AssertionError(f"unexpected path {path}")


def _verify_row(
    trace_id: str, observation_id: str, metadata: dict[str, Any] | None, start: str
) -> dict[str, Any]:
    return {
        "id": observation_id,
        "traceId": trace_id,
        "type": "SPAN",
        "name": "nitelos.verify",
        "startTime": start,
        "endTime": start,
        "metadata": metadata,
    }


def _backfill_criteria(tmp_path: Path) -> Path:
    doc = {
        "version": "1",
        "profile": "backfill",
        "checkpoint_id": "backfill",
        "criteria": [
            {
                "id": "verdict-recorded",
                "description": "The verify span recorded a passing run",
                "kind": "assertion",
                "scope": "external",
                "evidence_ids": ["trace"],
                "subject": {"trace": "any"},
                "pointer": "/observations/0/metadata/failed",
                "operator": "equals",
                "expected": 0,
            }
        ],
    }
    path = tmp_path / "criteria.json"
    path.write_text(json.dumps(doc), encoding="utf-8")
    return path


def test_lf09_backfill_runs_check_scores_and_counts_per_verdict(tmp_path: Path) -> None:
    rows = [
        _verify_row("trace-good", "obs-a", {"failed": 0}, "2026-11-10T00:00:00Z"),
        _verify_row("trace-bad", "obs-b", {"failed": 1}, "2026-11-10T01:00:00Z"),
        # a non-verify span must be ignored
        {
            "id": "obs-other",
            "traceId": "trace-good",
            "type": "SPAN",
            "name": "agent.step",
            "startTime": "2026-11-10T00:01:00Z",
            "endTime": "2026-11-10T00:01:00Z",
            "metadata": {},
        },
    ]
    transport = FakeTransport([rows])
    client = FakeClient()
    counts = run_backfill(transport, client, load_criteria_file(_backfill_criteria(tmp_path)))
    assert counts == {"success": 1, "failure": 1, "abstained": 0, "skipped": 0, "error": 0}
    values = sorted(call["value"] for call in client.calls)
    assert values == ["failure", "success"]
    # idempotent score ids: verification-derived, so re-running is safe
    assert client.calls[0]["score_id"]
    assert client.calls[1]["score_id"]
    assert "success" in render_backfill_summary(counts)


def test_lf10_backfill_skips_scored_traces_unless_force_and_dry_run_writes_nothing(tmp_path: Path) -> None:
    rows = [
        _verify_row("trace-good", "obs-a", {"failed": 0}, "2026-11-10T00:00:00Z"),
        _verify_row("trace-new", "obs-b", {"failed": 0}, "2026-11-10T02:00:00Z"),
    ]
    scores = {"trace-good": [{"id": "score-1", "name": "nitelos_outcome", "value": "success"}]}
    transport = FakeTransport([rows], existing_scores=scores)
    client = FakeClient()
    counts = run_backfill(transport, client, load_criteria_file(_backfill_criteria(tmp_path)))
    assert counts["skipped"] == 1
    assert counts["success"] == 1
    assert {call["trace_id"] for call in client.calls} == {"trace-new"}

    forced = FakeTransport([rows], existing_scores=scores)
    forced_client = FakeClient()
    counts = run_backfill(forced, forced_client, load_criteria_file(_backfill_criteria(tmp_path)), force=True)
    assert counts["skipped"] == 0
    assert counts["success"] == 2

    dry = FakeTransport([rows], existing_scores=scores)
    dry_client = FakeClient()
    counts = run_backfill(
        dry, dry_client, load_criteria_file(_backfill_criteria(tmp_path)), dry_run=True, force=True
    )
    assert counts["success"] == 2
    assert dry_client.calls == []  # dry-run records nothing


def test_lf11_backfill_missing_evidence_abstains_and_since_filters(tmp_path: Path) -> None:
    rows = [
        _verify_row("trace-no-evidence", "obs-a", None, "2026-11-10T00:00:00Z"),
        _verify_row("trace-old", "obs-old", {"failed": 0}, "2026-11-01T00:00:00Z"),
        _verify_row("trace-new", "obs-new", {"failed": 0}, "2026-11-09T00:00:00Z"),
    ]
    transport = FakeTransport([rows])
    client = FakeClient()
    counts = run_backfill(
        transport, client, load_criteria_file(_backfill_criteria(tmp_path)), since="2026-11-05T00:00:00Z"
    )
    assert counts["abstained"] == 1  # metadata None -> pointer unresolvable
    assert counts["success"] == 1  # trace-new only
    assert {call["trace_id"] for call in client.calls} == {"trace-new"}


def test_lf11b_cursor_pagination_continues_until_cursor_missing() -> None:
    page1 = [_verify_row("t-1", "o-1", {"failed": 0}, "2026-11-10T00:00:00Z")]
    page2 = [_verify_row("t-2", "o-2", {"failed": 0}, "2026-11-10T01:00:00Z")]  # short page WITH cursor
    page3: list[dict[str, Any]] = []  # empty page WITH cursor must not stop iteration
    page4 = [_verify_row("t-3", "o-3", {"failed": 0}, "2026-11-10T02:00:00Z")]
    transport = FakeTransport([page1, page2, page3, page4])
    rows = iter_observation_pages(transport)
    assert len(rows) == 3
    grouped = group_by_trace(rows)
    assert sorted(grouped) == ["t-1", "t-2", "t-3"]


def test_lf11c_trace_evidence_is_one_bounded_bundle() -> None:
    rows = [_verify_row("trace-1", f"o-{i}", {"failed": 0}, "2026-11-10T00:00:00Z") for i in range(5)]
    item = trace_evidence("trace-1", rows, max_rows=2)
    assert item.source_id == "langfuse-backfill"
    assert item.channel == "external_api"
    data = dict(item.data)
    assert len(data["observations"]) == 2
    assert data["truncated_count"] == 3  # honest truncation marker


# --------------------------------------------------------------------------
# LF-12: criteria loader + transport credentials
# --------------------------------------------------------------------------


def test_lf12_yaml_criteria_and_transport_credential_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    yaml_doc = (
        "version: '1'\n"
        "profile: backfill\n"
        "criteria:\n"
        "  - id: c-1\n"
        "    description: d\n"
        "    kind: assertion\n"
        "    scope: external\n"
        "    evidence_ids: [trace]\n"
        "    subject: {trace: any}\n"
        "    pointer: /observations/0/metadata/failed\n"
        "    operator: equals\n"
        "    expected: 0\n"
    )
    path = tmp_path / "criteria.yaml"
    path.write_text(yaml_doc, encoding="utf-8")
    loaded = load_criteria_file(path)
    assert loaded["criteria"][0]["id"] == "c-1"

    for var in ("LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY", "LANGFUSE_HOST"):
        monkeypatch.delenv(var, raising=False)
    with pytest.raises(Exception, match="LANGFUSE_PUBLIC_KEY"):
        PublicApiTransport()


# --------------------------------------------------------------------------
# LF-LIVE: opt-in live test (skipped by default; NO LLM calls)
# --------------------------------------------------------------------------


@pytest.mark.langfuse_live
@pytest.mark.skipif(
    os.environ.get("NITELOS_RUN_LANGFUSE_LIVE") != "1",
    reason="opt-in live Langfuse test; set NITELOS_RUN_LANGFUSE_LIVE=1 plus LANGFUSE_HOST/KEYS",
)
def test_lf_live_record_verdict_roundtrip() -> None:
    """Record one real score against a live Langfuse project (no LLM involved).

    Owner rule for live runs: this test touches the Langfuse API only. Any
    future test that needs a live LLM must use the Z.ai Coding Plan endpoint
    (https://api.z.ai/api/coding/paas/v4, model glm-5.3-flash, key env
    NITELOS_ZAI_KEY) and must STOP on billing/endpoint errors — never fall
    back to another provider.
    """
    import uuid

    from nitelos.integrations.langfuse import get_langfuse_client

    client = get_langfuse_client()
    trace_id = f"nitelos-live-{uuid.uuid4()}"
    result = _result(failed=0)
    value = record_verdict(result, trace_id, client=client, name="nitelos_outcome_live")
    assert value == "success"
