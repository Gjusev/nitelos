"""HSF-01..02: the Stop hook survives state-write failures (NIT-023 review fix)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from nitelos import claude_code

FAILING_JUNIT = (
    b'<testsuites><testsuite tests="2" failures="1" skipped="0" errors="0">'
    b'<testcase classname="tests.test_reg" name="test_ok"/>'
    b'<testcase classname="tests.test_reg" name="test_email_required">'
    b"<failure>assert False</failure></testcase>"
    b"</testsuite></testsuites>"
)


def _criteria(tmp: Path) -> None:
    nitelos_dir = tmp / ".nitelos"
    nitelos_dir.mkdir(exist_ok=True)
    (nitelos_dir / "criteria.json").write_text(
        json.dumps(
            {
                "version": "1",
                "profile": "custom",
                "checkpoint_id": "stop",
                "collectors": {
                    "junit": {
                        "evidence_id": "tests-1",
                        "subject": {"suite": "regression"},
                        "report_root": str(tmp),
                        "report_glob": "reports/*.xml",
                    }
                },
                "criteria": [
                    {
                        "id": "tests-green",
                        "description": "All tests pass",
                        "kind": "assertion",
                        "scope": "external",
                        "evidence_ids": ["tests-1"],
                        "subject": {"suite": "regression"},
                        "pointer": "/failed",
                        "operator": "equals",
                        "expected": 0,
                    }
                ],
                "on_abstain": "warn",
                "max_seconds": 30.0,
            }
        ),
        encoding="utf-8",
    )


def _stop_input(cwd: Path, *, active: bool = False) -> str:
    return json.dumps(
        {
            "session_id": "s-hsf",
            "prompt_id": "p-hsf",
            "transcript_path": str(cwd / "t.jsonl"),
            "cwd": str(cwd),
            "hook_event_name": "Stop",
            "stop_hook_active": active,
            "last_assistant_message": "All tests pass.",
        }
    )


def _seed(state_dir: Path) -> None:
    from datetime import timedelta

    state_dir.mkdir(exist_ok=True)
    stamp = (datetime.now(UTC) - timedelta(seconds=60)).isoformat().replace("+00:00", "Z")
    (state_dir / "session-s-hsf.json").write_text(
        json.dumps({"turn_start_key": "s-hsf:p-hsf", "turn_start": stamp}),
        encoding="utf-8",
    )


def _setup(tmp_path: Path) -> Path:
    (tmp_path / "reports").mkdir()
    (tmp_path / "reports" / "junit.xml").write_bytes(FAILING_JUNIT)
    _criteria(tmp_path)
    return tmp_path / "state"


def test_hsf01_block_survives_state_write_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    state = _setup(tmp_path)
    _seed(state)

    def exploding_write(*_args: Any, **_kwargs: Any) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(claude_code, "_write_state", exploding_write)
    document = claude_code.run_stop(_stop_input(tmp_path), state_dir=state)
    assert document.get("decision") == "block"
    assert "tests-green" in document["reason"]


def test_hsf02_repeat_block_path_survives_state_write_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state = _setup(tmp_path)
    _seed(state)
    fingerprint_probe = claude_code._fingerprint  # symbol exists for the guard

    # Pre-arm the guard so the SECOND call takes the repeat-block path,
    # which performs the state write before returning the warning.
    real_write = claude_code._write_state
    captured: list[dict[str, Any]] = []

    def recording_write(state_dir: Path, session_id: str, data: dict[str, Any]) -> None:
        captured.append(data)
        real_write(state_dir, session_id, data)

    monkeypatch.setattr(claude_code, "_write_state", recording_write)
    first = claude_code.run_stop(_stop_input(tmp_path), state_dir=state)
    assert first.get("decision") == "block"

    def exploding_write(*_args: Any, **_kwargs: Any) -> None:
        raise OSError("still full")

    monkeypatch.setattr(claude_code, "_write_state", exploding_write)
    second = claude_code.run_stop(_stop_input(tmp_path, active=True), state_dir=state)
    assert "decision" not in second or second.get("decision") != "block"
    assert "systemMessage" in second
    assert fingerprint_probe is not None
    assert captured  # the arming write happened via the recording wrapper
