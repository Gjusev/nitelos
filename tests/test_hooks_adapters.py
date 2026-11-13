"""HOOKS-01..12: Project 1B harness adapters — Claude Code, Codex, OpenCode.

Golden stdin fixtures per harness live in ``tests/fixtures/hooks/``. All tests
run offline: collectors are real (junit reports on local temp files) or
monkeypatched; nothing touches a harness binary or the network.
"""

from __future__ import annotations

import hashlib
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from nitelos import canonical_json
from nitelos.collect import CollectionResult, ProvenanceRecord, host_trust_bindings
from nitelos.evidence import build_observation
from nitelos.integrations.hooks import codex, install, opencode

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "hooks"

FAILING_JUNIT = (
    b'<testsuites><testsuite tests="2" failures="1" skipped="0" errors="0">'
    b'<testcase classname="tests.test_reg" name="test_ok"/>'
    b'<testcase classname="tests.test_reg" name="test_email_required">'
    b"<failure>assert False</failure></testcase>"
    b"</testsuite></testsuites>"
)

PASSING_JUNIT = (
    b'<testsuites><testsuite tests="2" failures="0" skipped="0" errors="0">'
    b'<testcase classname="tests.test_reg" name="test_ok"/>'
    b'<testcase classname="tests.test_reg" name="test_email_required"/>'
    b"</testsuite></testsuites>"
)


def _criteria(
    tmp: Path,
    *,
    filename: str = "criteria.yaml",
    on_abstain: str = "warn",
) -> Path:
    """YAML criteria (the documented hooks format) wired to a junit collector."""
    nitelos_dir = tmp / ".nitelos"
    nitelos_dir.mkdir(exist_ok=True)
    doc = f"""
version: '1'
profile: custom
checkpoint_id: stop
collectors:
  junit:
    evidence_id: tests-1
    subject: {{suite: regression}}
    report_root: {tmp}
    report_glob: "reports/*.xml"
criteria:
  - id: tests-green
    description: All tests pass
    kind: assertion
    scope: external
    evidence_ids: [tests-1]
    subject: {{suite: regression}}
    pointer: /failed
    operator: equals
    expected: 0
on_abstain: {on_abstain}
max_seconds: 30.0
"""
    path = nitelos_dir / filename
    path.write_text(doc, encoding="utf-8")
    return path


def _stdin(fixture: str, **overrides: Any) -> str:
    event = json.loads((FIXTURES / fixture).read_text(encoding="utf-8"))
    event.update(overrides)
    return json.dumps(event)


def _write_report(tmp: Path, payload: bytes) -> None:
    (tmp / "reports").mkdir(exist_ok=True)
    (tmp / "reports" / "junit.xml").write_bytes(payload)


def _seed_turn_start(state_dir: Path) -> None:
    stamp = (datetime.now(UTC) - timedelta(seconds=60)).isoformat().replace("+00:00", "Z")
    state_dir.mkdir(exist_ok=True)
    (state_dir / "session-s-1.json").write_text(
        json.dumps({"turn_start_key": "s-1:p-1", "turn_start": stamp}),
        encoding="utf-8",
    )


def _fake_evidence(*, failed: int = 1) -> tuple[list[Any], tuple[Any, ...]]:
    captured = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    item = build_observation(
        id="tests-1",
        sequence=0,
        captured_at=captured,
        checkpoint_id="stop",
        source_id="junit",
        subject={"suite": "regression"},
        phase="final",
        channel="external_api",
        data={"failed": failed, "total": 2},
    )
    result = CollectionResult(
        collector_id="junit",
        collector_version="1",
        evidence=(item,),
        provenance=(
            ProvenanceRecord(
                evidence_id=item.id,
                collector_id="junit",
                collector_version="1",
                source="test",
                invocation="test",
                captured_at=captured,
                subject={"suite": "regression"},
                sha256=hashlib.sha256(b"raw").hexdigest(),
                raw_bytes=3,
                normalized_bytes=10,
            ),
        ),
    )
    return [item], host_trust_bindings(result)


# --------------------------------------------------------------------------
# HOOKS-01..04: Claude Code adapter (delegates to the NIT-023 plugin)
# --------------------------------------------------------------------------


def _load_claude_adapter() -> Any:
    from nitelos.integrations.hooks import claude_code as adapter

    return adapter


def test_hooks01_claude_code_golden_fixture_failure_blocks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _criteria(tmp_path)
    _write_report(tmp_path, FAILING_JUNIT)
    state_dir = tmp_path / "state"
    _seed_turn_start(state_dir)

    monkeypatch.setattr("nitelos.integrations.hooks.claude_code._default_state_dir", lambda: state_dir)
    document = _load_claude_adapter().handle_stop(_stdin("claude_code_stop.json", cwd=str(tmp_path)))
    assert document.get("decision") == "block"
    assert "tests-green" in document["reason"]


def test_hooks02_claude_code_criteria_yaml_loaded_via_package_loader(tmp_path: Path) -> None:
    from nitelos.claude_code import load_criteria

    _criteria(tmp_path)
    assert load_criteria(tmp_path).profile == "custom"  # YAML path
    json_doc = {
        "version": "1",
        "profile": "custom-json",
        "checkpoint_id": "stop",
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
    }
    (tmp_path / ".nitelos" / "criteria.json").write_text(json.dumps(json_doc), encoding="utf-8")
    assert load_criteria(tmp_path).profile == "custom-json"  # JSON wins when both exist
    (tmp_path / ".nitelos" / "criteria.json").unlink()
    assert load_criteria(tmp_path).criteria[0]["id"] == "tests-green"
    with pytest.raises(FileNotFoundError):
        load_criteria(tmp_path / "nonexistent")


def test_hooks03_codex_failure_blocks_with_continuation_prompt_semantics(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _criteria(tmp_path)
    evidence, bindings = _fake_evidence()
    monkeypatch.setattr(codex, "_collect_all", lambda *a, **k: (evidence, bindings, [], []))
    state_dir = tmp_path / "state"
    document = codex.run_stop(_stdin("codex_stop.json", cwd=str(tmp_path)), state_dir=state_dir)
    # Codex: `reason` becomes the new continuation prompt (never a rejection)
    assert document.get("decision") == "block"
    assert "tests-green" in document["reason"]
    assert "continue" not in document  # never emitted; continue:false would end the turn


def test_hooks04_codex_success_and_abstain_never_block(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _criteria(tmp_path)
    passing = build_observation(
        id="tests-1",
        sequence=0,
        captured_at=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        checkpoint_id="stop",
        source_id="junit",
        subject={"suite": "regression"},
        phase="final",
        channel="external_api",
        data={"failed": 0, "total": 2},
    )
    result = CollectionResult(
        collector_id="junit",
        collector_version="1",
        evidence=(passing,),
        provenance=(
            ProvenanceRecord(
                evidence_id=passing.id,
                collector_id="junit",
                collector_version="1",
                source="test",
                invocation="test",
                captured_at=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
                subject={"suite": "regression"},
                sha256=hashlib.sha256(b"raw").hexdigest(),
                raw_bytes=3,
                normalized_bytes=10,
            ),
        ),
    )
    monkeypatch.setattr(
        codex, "_collect_all", lambda *a, **k: ([passing], host_trust_bindings(result), [], [])
    )
    state_dir = tmp_path / "state"
    document = codex.run_stop(_stdin("codex_stop.json", cwd=str(tmp_path)), state_dir=state_dir)
    assert document == {}

    # abstain: no evidence produced, so the criterion cites nothing (MISSING_EVIDENCE)
    monkeypatch.setattr(codex, "_collect_all", lambda *a, **k: ([], (), [], []))
    abstain = codex.run_stop(_stdin("codex_stop.json", cwd=str(tmp_path)), state_dir=state_dir)
    assert abstain == {}
    assert "undecided" in capsys.readouterr().err
    # the module entry point always prints valid JSON on stdout (exit 0 contract)
    monkeypatch.setattr(
        sys,
        "stdin",
        type(
            "_Stdin", (), {"read": staticmethod(lambda *_a: _stdin("codex_stop.json", cwd=str(tmp_path)))}
        )(),
    )
    codex.main()
    assert json.loads(capsys.readouterr().out.strip()) == {}


def test_hooks05_codex_loop_guard_respects_stop_hook_active(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _criteria(tmp_path)
    evidence, bindings = _fake_evidence()
    monkeypatch.setattr(codex, "_collect_all", lambda *a, **k: (evidence, bindings, [], []))
    state_dir = tmp_path / "state"
    first = codex.run_stop(
        _stdin("codex_stop.json", cwd=str(tmp_path), stop_hook_active=True), state_dir=state_dir
    )
    assert first.get("decision") == "block"
    repeat = codex.run_stop(
        _stdin("codex_stop.json", cwd=str(tmp_path), stop_hook_active=True), state_dir=state_dir
    )
    assert repeat == {}  # same fingerprint while stop_hook_active: pass, warn on stderr
    assert "loop" in capsys.readouterr().err


def test_hooks06_codex_on_abstain_block_still_never_blocks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _criteria(tmp_path, on_abstain="block")
    # no evidence at all: the criterion's evidence id is filtered out -> abstain
    monkeypatch.setattr(codex, "_collect_all", lambda *a, **k: ([], (), [], []))
    document = codex.run_stop(_stdin("codex_stop.json", cwd=str(tmp_path)), state_dir=tmp_path / "s")
    assert document == {}  # abstention NEVER blocks on Codex, regardless of config
    assert "tests-green" in capsys.readouterr().err


# --------------------------------------------------------------------------
# HOOKS-07..09: OpenCode observe-only adapter
# --------------------------------------------------------------------------


def test_hooks07_opencode_observe_reports_and_never_blocks(tmp_path: Path) -> None:
    _criteria(tmp_path)
    _write_report(tmp_path, FAILING_JUNIT)
    monkey_cwd = tmp_path
    import os

    previous = os.getcwd()
    os.chdir(monkey_cwd)
    try:
        lines = opencode.run_observe(_stdin("opencode_idle.json"))
    finally:
        os.chdir(previous)
    report = "\n".join(lines)
    assert "FAILURE" in report
    assert "cannot block session end" in report  # documented non-goal
    assert not any('"decision"' in line for line in lines)  # no block document anywhere


def test_hooks08_opencode_plugin_source_is_observe_only_with_optional_tool_guard() -> None:
    source = opencode.plugin_source()
    assert "session.idle" in source
    assert "NITELOS_OPENCODE_MODULE_PLACEHOLDER" not in source  # module name substituted
    assert "nitelos.integrations.hooks.opencode" in source
    assert "tool.execute.before" in source  # optional guard (the only blockable thing)
    # no completion-blocking pretense: the idle handler emits no block document
    assert '"decision"' not in source
    assert 'decision: "block"' not in source


def test_hooks09_opencode_missing_criteria_reports_instead_of_raising(tmp_path: Path) -> None:
    import os

    previous = os.getcwd()
    os.chdir(tmp_path)
    try:
        lines = opencode.run_observe("")
    finally:
        os.chdir(previous)
    assert any("criteria unavailable" in line for line in lines)


# --------------------------------------------------------------------------
# HOOKS-10..12: installer CLI
# --------------------------------------------------------------------------


def test_hooks10_snippets_per_harness(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    # claude-code: turn-start record + Stop verify, wired to the plugin runtime
    assert "UserPromptSubmit" in install.CLAUDE_CODE_SNIPPET
    assert "NITELOS_HOOK_ROLE=prompt" in install.CLAUDE_CODE_SNIPPET
    assert "python -m nitelos.claude_code" in install.CLAUDE_CODE_SNIPPET
    # codex: Stop + the mandatory trust-review step + continuation semantics
    assert "python -m nitelos.integrations.hooks.codex" in install.CODEX_SNIPPET
    assert "trust" in install._CODEX_TRUST_NOTE.lower()
    assert "/hooks" in install._CODEX_TRUST_NOTE
    # opencode: generated plugin source
    assert "session.idle" in install.install_snippet("opencode")
    # printing path writes nothing anywhere
    assert install.main(["--harness", "claude-code"]) == 0
    assert "UserPromptSubmit" in capsys.readouterr().out
    assert not list(tmp_path.iterdir())


def test_hooks11_write_config_refuses_existing_target_without_force(tmp_path: Path) -> None:
    target = tmp_path / ".codex" / "hooks.json"
    assert install.write_config("codex", target) is True
    original = target.read_text(encoding="utf-8")
    assert install.write_config("codex", target) is False
    assert target.read_text(encoding="utf-8") == original  # untouched
    assert install.write_config("codex", target, force=True) is True
    (tmp_path / ".claude").mkdir()
    assert install.write_config("claude-code", tmp_path / ".claude" / "settings.json") is True


def test_hooks12_install_cli_end_to_end(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    target = tmp_path / ".opencode" / "plugins" / "nitelos-observe.ts"
    assert install.main(["--harness", "opencode", "--target", str(target)]) == 0
    assert "session.idle" in target.read_text(encoding="utf-8")
    assert "wrote" in capsys.readouterr().out

    existing = tmp_path / "settings.json"
    existing.write_text("{}", encoding="utf-8")
    assert install.main(["--harness", "claude-code", "--target", str(existing)]) == 2
    assert "refusing to overwrite" in capsys.readouterr().err
    assert existing.read_text(encoding="utf-8") == "{}"
    assert install.main(["--harness", "claude-code", "--target", str(existing), "--force"]) == 0
    assert "UserPromptSubmit" in existing.read_text(encoding="utf-8")

    with pytest.raises(SystemExit):
        install.main(["--harness", "jetbrains"])


def test_hooks13_golden_fixtures_are_valid_json_with_expected_fields() -> None:
    claude = json.loads((FIXTURES / "claude_code_stop.json").read_text(encoding="utf-8"))
    codex_event = json.loads((FIXTURES / "codex_stop.json").read_text(encoding="utf-8"))
    idle = json.loads((FIXTURES / "opencode_idle.json").read_text(encoding="utf-8"))
    assert claude["hook_event_name"] == "Stop"
    assert "stop_hook_active" in claude
    assert codex_event["hook_event_name"] == "Stop"
    assert codex_event["transcript_path"] is None
    assert idle["type"] == "session.idle"
    # the wire shapes stay consistent with canonical_json round-tripping
    assert json.loads(canonical_json(claude)) == claude


def test_hooks14_demo_repo_blocks_the_agents_claim() -> None:
    """DOC demo: examples/claude_code_stop_hook blocks "tests pass" while failing."""
    import subprocess
    import sys

    if sys.platform == "win32":
        # the demo drives a POSIX shell script that invokes the installed
        # `nitelos` entry point; on Windows runners Git Bash resolves neither
        # reliably (PowerShell error output leaks in as UTF-16). The demo is
        # verified on Linux/macOS; see NOTES.md Q12.
        import unittest

        raise unittest.SkipTest("demo run_demo.sh is POSIX-only (see NOTES.md)")
    demo = ROOT / "examples" / "claude_code_stop_hook"
    proc = subprocess.run(
        ["bash", str(demo / "run_demo.sh")],
        check=False,
        capture_output=True,
        text=True,
        cwd=demo,
        timeout=60,
    )
    assert proc.returncode == 0, proc.stderr
    document = json.loads(proc.stdout)
    assert document["decision"] == "block"
    assert "tests-green" in document["reason"]
    assert "test_email::test_email_requires_domain_dot" in document["reason"]
