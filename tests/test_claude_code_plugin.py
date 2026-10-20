"""HOOK-01..12: F7 Claude Code plugin (NIT-023)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from nitelos import claude_code

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugin"

FAILING_JUNIT = (
    b'<testsuites><testsuite tests="2" failures="1" skipped="0" errors="0">'
    b'<testcase classname="tests.test_reg" name="test_ok"/>'
    b'<testcase classname="tests.test_reg" name="test_email_required">'
    b"<failure>assert False</failure></testcase>"
    b"</testsuite></testsuites>"
)


def _criteria(
    tmp: Path,
    *,
    profile: str = "custom",
    on_abstain: str = "warn",
    max_seconds: float = 30.0,
    reports: str = "reports",
) -> Path:
    nitelos_dir = tmp / ".nitelos"
    nitelos_dir.mkdir(exist_ok=True)
    doc = {
        "version": "1",
        "profile": profile,
        "checkpoint_id": "stop",
        "collectors": {
            "junit": {
                "evidence_id": "tests-1",
                "subject": {"suite": "regression"},
                "report_root": str(tmp),
                "report_glob": f"{reports}/*.xml",
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
        "on_abstain": on_abstain,
        "max_seconds": max_seconds,
    }
    path = nitelos_dir / "criteria.json"
    path.write_text(json.dumps(doc, indent=2), encoding="utf-8")
    return path


def _stop_input(cwd: Path, *, active: bool = False, last_message: str = "All tests pass.") -> str:
    return json.dumps(
        {
            "session_id": "s-1",
            "prompt_id": "p-1",
            "transcript_path": str(cwd / "transcript.jsonl"),
            "cwd": str(cwd),
            "hook_event_name": "Stop",
            "stop_hook_active": active,
            "last_assistant_message": last_message,
        }
    )


def _seed_turn_start(state_dir: Path, *, iso: str | None = None) -> None:
    from datetime import timedelta

    stamp = iso or ((datetime.now(UTC) - timedelta(seconds=60)).isoformat().replace("+00:00", "Z"))
    state_dir.mkdir(exist_ok=True)
    state_file = state_dir / "session-s-1.json"
    if not state_file.exists():  # never overwrite loop-guard state between calls
        state_file.write_text(
            json.dumps({"turn_start_key": "s-1:p-1", "turn_start": stamp}),
            encoding="utf-8",
        )


def _run_hook(stdin_text: str, state_dir: Path, cwd: Path) -> dict[str, Any]:
    _seed_turn_start(state_dir)
    document = claude_code.run_stop(stdin_text, state_dir=state_dir)
    return document


def test_hook01_agent_claims_pass_junit_shows_failure_blocks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "reports").mkdir()
    (tmp_path / "reports" / "junit.xml").write_bytes(FAILING_JUNIT)
    _criteria(tmp_path)
    state = tmp_path / "state"
    doc = _run_hook(_stop_input(tmp_path), state, tmp_path)
    assert doc["decision"] == "block"
    reason = doc["reason"]
    assert "tests-green" in reason
    assert "tests.test_reg::test_email_required" in reason
    assert doc.get("suppressOutput") in (None, True) or "decision" in doc


def test_hook02_loop_guard_warns_on_repeat_block(
    tmp_path: Path,
) -> None:
    (tmp_path / "reports").mkdir()
    (tmp_path / "reports" / "junit.xml").write_bytes(FAILING_JUNIT)
    _criteria(tmp_path)
    state = tmp_path / "state"
    first = _run_hook(_stop_input(tmp_path), state, tmp_path)
    assert first["decision"] == "block"
    second = _run_hook(_stop_input(tmp_path, active=True), state, tmp_path)
    assert "decision" not in second or second.get("decision") != "block"
    assert "systemMessage" in second
    third = _run_hook(_stop_input(tmp_path), state, tmp_path)
    assert third["decision"] == "block"


def test_hook03_missing_report_abstains_with_warning(
    tmp_path: Path,
) -> None:
    _criteria(tmp_path)
    doc = _run_hook(_stop_input(tmp_path), tmp_path / "state", tmp_path)
    assert "systemMessage" in doc
    assert "decision" not in doc
    assert "MISSING_EVIDENCE" in doc["systemMessage"]


def test_hook04_on_abstain_block_option_blocks_instead(
    tmp_path: Path,
) -> None:
    _criteria(tmp_path, on_abstain="block")
    doc = _run_hook(_stop_input(tmp_path), tmp_path / "state", tmp_path)
    assert doc["decision"] == "block"
    assert "MISSING_EVIDENCE" in doc["reason"]


def test_hook05_budget_overrun_degrades_to_warning(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "reports").mkdir()
    (tmp_path / "reports" / "junit.xml").write_bytes(FAILING_JUNIT)
    _criteria(tmp_path, max_seconds=0.005)

    real_collect = claude_code._collect_all

    def slow_collect(*args: Any, **kwargs: Any) -> Any:
        time.sleep(0.02)
        return real_collect(*args, **kwargs)

    monkeypatch.setattr(claude_code, "_collect_all", slow_collect)
    doc = _run_hook(_stop_input(tmp_path), tmp_path / "state", tmp_path)
    assert "decision" not in doc
    assert "systemMessage" in doc
    assert "budget" in doc["systemMessage"].lower()


def test_hook06_turn_start_gates_freshness(tmp_path: Path) -> None:

    (tmp_path / "reports").mkdir()
    report = tmp_path / "reports" / "junit.xml"
    report.write_bytes(FAILING_JUNIT)
    _criteria(tmp_path)
    state = tmp_path / "state"
    state.mkdir()
    stamp = (datetime.now(UTC) - timedelta(hours=3)).timestamp()
    os.utime(report, (stamp, stamp))
    _seed_turn_start(state)  # turn started 60 s ago; the report is 3 h old -> stale
    doc = claude_code.run_stop(_stop_input(tmp_path), state_dir=state)
    assert "decision" not in doc
    assert "MISSING_EVIDENCE" in doc["systemMessage"]


def test_hook07_prompt_role_records_turn_start(tmp_path: Path) -> None:
    event = json.dumps(
        {
            "session_id": "s-9",
            "prompt_id": "p-9",
            "timestamp": "2026-10-20T10:00:00.000Z",
            "hook_event_name": "UserPromptSubmit",
        }
    )
    claude_code.run_prompt(event, state_dir=tmp_path)
    data = json.loads((tmp_path / "session-s-9.json").read_text(encoding="utf-8"))
    assert data["turn_start_key"] == "s-9:p-9"
    assert data["turn_start"].startswith("2026-10-20T10:00:00")


def test_hook08_internal_error_warns_and_exits_zero(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _criteria(tmp_path)

    def boom(*_a: Any, **_k: Any) -> Any:
        raise RuntimeError("SECRET internal detail")

    monkeypatch.setattr(claude_code, "_collect_all", boom)
    doc = _run_hook(_stop_input(tmp_path), tmp_path / "state", tmp_path)
    assert "decision" not in doc
    assert "systemMessage" in doc
    assert "SECRET" not in json.dumps(doc)


def test_hook09_invalid_criteria_warns(tmp_path: Path) -> None:
    nitelos_dir = tmp_path / ".nitelos"
    nitelos_dir.mkdir()
    (nitelos_dir / "criteria.json").write_text("{ not json", encoding="utf-8")
    doc = _run_hook(_stop_input(tmp_path), tmp_path / "state", tmp_path)
    assert "decision" not in doc
    assert "systemMessage" in doc
    assert "criteria" in doc["systemMessage"].lower()


def test_hook10_missing_collector_module_warns(tmp_path: Path) -> None:
    (tmp_path / "reports").mkdir()
    (tmp_path / "reports" / "junit.xml").write_bytes(FAILING_JUNIT)
    _criteria(tmp_path)
    code = (
        "import json, sys\n"
        "from pathlib import Path\n"
        'sys.modules["nitelos.collect.test_results"] = None\n'
        "from nitelos import claude_code\n"
        "doc = claude_code.run_stop(sys.stdin.read(), state_dir=Path(sys.argv[1]))\n"
        "print(json.dumps(doc))\n"
    )
    (tmp_path / "state").mkdir(exist_ok=True)
    _seed_turn_start(tmp_path / "state")
    proc = subprocess.run(
        [sys.executable, "-c", code, str(tmp_path / "state")],
        input=_stop_input(tmp_path),
        capture_output=True,
        text=True,
        cwd=ROOT,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    doc = json.loads(proc.stdout)
    assert "decision" not in doc
    assert "systemMessage" in doc
    assert "unavailable" in doc["systemMessage"].lower()


def test_hook11_plugin_assets_present_and_consistent() -> None:
    manifest = json.loads((PLUGIN / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
    assert manifest["name"] == "nitelos"
    hooks = json.loads((PLUGIN / "hooks" / "hooks.json").read_text(encoding="utf-8"))
    events = hooks["hooks"]
    assert "Stop" in events
    assert "UserPromptSubmit" in events
    launcher = PLUGIN / "hooks" / "nitelos-hook.sh"
    text = launcher.read_text(encoding="utf-8")
    assert "nitelos.claude_code" in text
    for name in ("init", "check"):
        command = PLUGIN / "commands" / f"{name}.md"
        body = command.read_text(encoding="utf-8")
        assert body.startswith("---"), name
        assert "description:" in body.split("---")[1], name
    install = (ROOT / "docs" / "claude-code.md").read_text(encoding="utf-8")
    steps = [line for line in install.splitlines() if line.strip().startswith(("1.", "2.", "3.", "4.", "5."))]
    assert 2 <= len(steps) <= 5


def test_hook12_check_role_never_blocks(tmp_path: Path) -> None:
    (tmp_path / "reports").mkdir()
    (tmp_path / "reports" / "junit.xml").write_bytes(FAILING_JUNIT)
    _criteria(tmp_path)
    lines = claude_code.run_check(cwd=tmp_path, state_dir=tmp_path / "state")
    assert isinstance(lines, list)
    assert lines
    assert any("tests-green" in line for line in lines)
