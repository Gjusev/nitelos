"""MCP-01..10: F11 MCP stdio server (NIT-027, extra ``mcp``).

Handler scenarios run in a subprocess (tests/_mcp_driver.py): the offline
suite's class-level socket.connect denial breaks the Windows proactor loop
self-pipe (the NIT-006 lesson), while no scenario needs any network.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("mcp", reason="nitelos[mcp] extra not provisioned in this environment yet")

ROOT = Path(__file__).resolve().parents[1]
DRIVER = ROOT / "tests" / "_mcp_driver.py"


@pytest.fixture(scope="module")
def report() -> dict[str, Any]:
    proc = subprocess.run(
        [sys.executable, str(DRIVER)],
        check=False,
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def test_mcp01_tools_are_the_three_planned(report: dict[str, Any]) -> None:
    assert report["tool_names"] == ["verify_outcome", "collect", "describe_criteria"]


def test_mcp02_verify_outcome_decides(report: dict[str, Any]) -> None:
    assert report["ok_decision"] == "success"
    assert report["ok_criterion"] == "c1"


def test_mcp03_injection_payload_is_data(report: dict[str, Any]) -> None:
    assert report["injection_decision"] == "failure"
    assert report["injection_state"] == "refuted"


def test_mcp04_config_tampering_rejected(report: dict[str, Any]) -> None:
    assert report["tamper_is_error"]
    assert "rejected by the schema" in report["tamper_text"]


def test_mcp05_agent_evidence_stays_unbound(report: dict[str, Any]) -> None:
    assert report["external_decision"] == "abstained"
    assert "UNTRUSTED_EXTERNAL" in report["external_reasons"]


def test_mcp06_collect_gated(report: dict[str, Any]) -> None:
    assert report["collect_denied_is_error"]
    assert "not enabled" in report["collect_denied_text"]


def test_mcp07_collect_returns_evidence(report: dict[str, Any]) -> None:
    assert report["collect_total"] == 1


def test_mcp08_describe_read_only(report: dict[str, Any]) -> None:
    assert report["described_version"] == "1"
    assert report["described_first_id"] == "c1"
    assert report["criteria_untouched"] is True


def test_mcp09_argument_cap(report: dict[str, Any]) -> None:
    assert report["huge_is_error"]
    assert "cap" in report["huge_text"]


def test_mcp10_unknown_tool(report: dict[str, Any]) -> None:
    assert report["unknown_is_error"]
    assert "unknown tool" in report["unknown_text"]


def test_mcp11_isolation_and_actionable_missing_extra() -> None:
    code = (
        "import sys\n"
        "sys.modules['mcp'] = None\n"
        "import nitelos\n"
        "print('core-ok')\n"
        "try:\n"
        "    import nitelos.integrations.mcp_server\n"
        "except Exception as exc:\n"
        "    print(type(exc).__name__)\n"
        "    print('nitelos[mcp]' in str(exc))\n"
        "else:\n"
        "    raise SystemExit('should have raised')\n"
    )
    proc = subprocess.run([sys.executable, "-c", code], check=False, capture_output=True, text=True, cwd=ROOT)
    assert proc.returncode == 0, proc.stderr
    assert "core-ok" in proc.stdout
    assert "True" in proc.stdout
