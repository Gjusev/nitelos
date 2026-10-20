"""CLI-01..03: the ``nitelos collect`` debug CLI (NIT-017, plan section F1).

Kinds ship empty by design (NIT-018/019 add git and junit); these tests patch
the fixed in-code kind table, pointing ``fake`` at objects in this very test
module (importable because the module is already in ``sys.modules``).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from nitelos import Evidence, canonical_json, cli
from nitelos.collect import (
    CollectionResult,
    CollectorCapabilities,
    CollectorError,
    CollectorErrorCode,
    ProvenanceRecord,
)

SENTINEL = "SENTINEL-SENTINEL-cli"


class _FakeCollector:
    id = "cli-fixture"
    version = "9.9.9"

    @property
    def capabilities(self) -> CollectorCapabilities:
        return CollectorCapabilities(evidence_kinds=("observation",))

    def collect(self, config: Any) -> CollectionResult:
        item = Evidence.observation(
            id=config.evidence_id,
            sequence=config.sequence_start,
            captured_at="2026-10-20T12:00:00Z",
            checkpoint_id=config.checkpoint_id,
            source_id=self.id,
            subject=config.subject,
            phase="final",
            channel="external_api",
            data={"deployed": True, "api_token": SENTINEL},
        )
        size = len(canonical_json({"deployed": True}).encode("utf-8"))
        return CollectionResult(
            collector_id=self.id,
            collector_version=self.version,
            evidence=(item,),
            provenance=(
                ProvenanceRecord(
                    evidence_id=item.id,
                    collector_id=self.id,
                    collector_version=self.version,
                    source="cli fixture",
                    invocation="static",
                    captured_at=item.captured_at,
                    subject=config.subject,
                    sha256=item.sha256,
                    raw_bytes=30,
                    normalized_bytes=size,
                ),
            ),
        )


class _FailingCollector(_FakeCollector):
    def collect(self, config: Any) -> CollectionResult:
        raise CollectorError(CollectorErrorCode.AUTH_MISSING)


_FAKE: _FakeCollector = _FakeCollector()
_FAILING: _FailingCollector = _FailingCollector()


@pytest.fixture
def fake_kind(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli, "KIND_TARGETS", {"fake": "test_cli:_FAKE"})


@pytest.fixture
def failing_kind(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli, "KIND_TARGETS", {"fake": "test_cli:_FAILING"})


def _write_config(path: Path, **over: Any) -> Path:
    values: dict[str, Any] = {
        "evidence_id": "obs-1",
        "checkpoint_id": "cp-1",
        "subject": {"repo": "example/app"},
    }
    values.update(over)
    path.write_text(json.dumps(values), encoding="utf-8")
    return path


def test_cli01_unknown_kind_exits_two(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    config = _write_config(tmp_path / "config.json")
    code = cli.main(["collect", "nope", "--config", str(config), "--out", str(tmp_path / "out.json")])
    assert code == 2
    assert not (tmp_path / "out.json").exists()
    assert "unknown kind" in capsys.readouterr().err


def test_cli01_invalid_config_exits_two(
    tmp_path: Path, fake_kind: None, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "config.json").write_text('{"evidence_id": "obs-1", "surprise": true}', encoding="utf-8")
    code = cli.main(
        ["collect", "fake", "--config", str(tmp_path / "config.json"), "--out", str(tmp_path / "out.json")]
    )
    assert code == 2
    assert not (tmp_path / "out.json").exists()
    assert "config" in capsys.readouterr().err.lower()


def test_cli01_broken_json_config_exits_two(
    tmp_path: Path, fake_kind: None, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "config.json").write_text("{ not json", encoding="utf-8")
    code = cli.main(
        ["collect", "fake", "--config", str(tmp_path / "config.json"), "--out", str(tmp_path / "out.json")]
    )
    assert code == 2


def test_cli01_existing_out_refused_and_untouched(
    tmp_path: Path, fake_kind: None, capsys: pytest.CaptureFixture[str]
) -> None:
    config = _write_config(tmp_path / "config.json")
    out = tmp_path / "out.json"
    out.write_text("PREEXISTING", encoding="utf-8")
    code = cli.main(["collect", "fake", "--config", str(config), "--out", str(out)])
    assert code == 2
    assert out.read_text(encoding="utf-8") == "PREEXISTING"
    assert "exists" in capsys.readouterr().err


def test_cli02_success_writes_wire_evidence_and_provenance(
    tmp_path: Path, fake_kind: None, capsys: pytest.CaptureFixture[str]
) -> None:
    config = _write_config(tmp_path / "config.json")
    out = tmp_path / "out.json"
    code = cli.main(["collect", "fake", "--config", str(config), "--out", str(out)])
    assert code == 0
    document = json.loads(out.read_text(encoding="utf-8"))
    assert document["collector"] == {"id": "cli-fixture", "version": "9.9.9"}
    assert document["error"] is None
    (item,) = document["evidence"]
    assert item["kind"] == "observation"
    assert item["channel"] == "external_api"
    assert item["data"] == {"deployed": True}  # secret key dropped before storage
    (record,) = document["provenance"]
    assert record["evidence_id"] == item["id"]
    assert record["redactions"]  # the dropped secret key is recorded
    summary = capsys.readouterr().out
    assert "collected 1" in summary
    assert SENTINEL not in summary


def test_cli02_out_file_carries_no_secret(tmp_path: Path, fake_kind: None) -> None:
    config = _write_config(tmp_path / "config.json")
    out = tmp_path / "out.json"
    assert cli.main(["collect", "fake", "--config", str(config), "--out", str(out)]) == 0
    assert SENTINEL not in out.read_text(encoding="utf-8")


def test_cli03_collection_error_exits_three_with_code(
    tmp_path: Path, failing_kind: None, capsys: pytest.CaptureFixture[str]
) -> None:
    config = _write_config(tmp_path / "config.json")
    out = tmp_path / "out.json"
    code = cli.main(["collect", "fake", "--config", str(config), "--out", str(out)])
    assert code == 3
    assert "COLLECTOR_AUTH_MISSING" in capsys.readouterr().out
    document = json.loads(out.read_text(encoding="utf-8"))
    assert document["error"]["code"] == "COLLECTOR_AUTH_MISSING"
    assert document["evidence"] == []


def test_cli03_known_kind_with_unimportable_module_exits_three(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(cli, "KIND_TARGETS", {"fake": "nitelos.no_such_module_thing:Collector"})
    config = _write_config(tmp_path / "config.json")
    code = cli.main(["collect", "fake", "--config", str(config), "--out", str(tmp_path / "out.json")])
    assert code == 3
    assert "COLLECTOR_UNAVAILABLE" in capsys.readouterr().out
