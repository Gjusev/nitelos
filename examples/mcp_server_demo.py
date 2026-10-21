"""Drive the nitelos MCP server tools offline (extra `mcp`).

Runnable offline. It writes a tiny criteria file, pins one junit collector
config, builds the server, and calls the three tools directly through the
registered handlers (no stdio serving, no sockets). Without the `mcp`
extra installed the example exits 0 after printing the gate requirements.
"""

from __future__ import annotations

import asyncio
import json
import tempfile
from pathlib import Path
from typing import Any

try:
    from mcp.types import CallToolRequestParams
except ImportError:
    print("skip: install 'nitelos[mcp]' to run this example")
    raise SystemExit(0) from None

from nitelos.integrations.mcp_server import McpServerConfig, build_server, on_call_tool


class _Params(CallToolRequestParams):
    """The handler shape the server receives; local stand-in for the wire."""

    def __init__(self, name: str, arguments: dict[str, Any]) -> None:
        super().__init__(name=name, arguments=arguments)


def _setup(workdir: Path) -> McpServerConfig:
    (workdir / "reports").mkdir()
    (workdir / "reports" / "junit.xml").write_bytes(
        b'<testsuites><testsuite tests="2" failures="1" skipped="0" errors="0">'
        b'<testcase classname="tests.test_reg" name="test_ok"/>'
        b'<testcase classname="tests.test_reg" name="test_email_required">'
        b"<failure>assert False</failure></testcase>"
        b"</testsuite></testsuites>"
    )
    (workdir / "criteria.json").write_text(
        json.dumps(
            {
                "version": "1",
                "profile": "python",
                "criteria": [
                    {
                        "id": "tests-green",
                        "description": "All tests pass",
                        "kind": "assertion",
                        "scope": "external",
                        "evidence_ids": [],
                        "subject": {"suite": "regression"},
                        "pointer": "/failed",
                        "operator": "equals",
                        "expected": 0,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return McpServerConfig(
        criteria_path=workdir / "criteria.json",
        enabled_collectors=("junit",),
        collector_configs={
            "junit": {
                "evidence_id": "tests-1",
                "checkpoint_id": "stop",
                "subject": {"suite": "regression"},
                "report_root": str(workdir),
                "report_glob": "reports/*.xml",
            }
        },
    )


def _call(name: str, arguments: dict[str, Any]) -> Any:
    return asyncio.run(on_call_tool(None, _Params(name, arguments)))


def main() -> int:
    with tempfile.TemporaryDirectory() as workdir:
        build_server(_setup(Path(workdir)))
        described = _call("describe_criteria", {})
        print(f"criteria: {described.content[0].text[:80]}")
        collected = _call("collect", {"kind": "junit"})
        payload = json.loads(collected.content[0].text)
        print(f"collected total: {payload['evidence'][0]['data']['total']}")
        rejected = _call("collect", {"kind": "junit", "config": {"report_glob": "*"}})
        print(f"agent config rejected: {rejected.is_error}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
