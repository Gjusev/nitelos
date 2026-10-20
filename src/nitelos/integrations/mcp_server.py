"""The MCP stdio server (plan F11, NIT-027; extra ``mcp``).

Tools: ``verify_outcome`` (a full v0.1 request mapping, verified with the
strict policy and NO trust bindings — evidence supplied through this server
is agent evidence and stays unbound, so external-scope criteria abstain with
UNTRUSTED_EXTERNAL per ADR-015 finding 4), ``collect`` (only for the kinds
enabled in the server config; returns the collected evidence wire form or
the collector error code) and ``describe_criteria`` (read-only view of the
configured criteria: ids, descriptions, kinds, scopes — never the file).

Hard rules enforced structurally: no tool accepts criteria, config or
evidence-deletion arguments at all; the criteria file is only ever READ;
input arguments are capped (256 KiB serialized) and oversize calls fail as
tool errors; every call is logged with the tool name, the argument size and
the outcome code only — never argument content. Evidence payloads are data:
an injection string inside an observation influences nothing.

Requires the ``mcp`` extra; importing this module without the package raises
:class:`ImportError` naming the install command. Importing ``nitelos`` never
loads mcp (BND-01). The stdio entry point is ``python -m
nitelos.integrations.mcp_server``.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from nitelos import Verifier
from nitelos.collect import run_collector
from nitelos.errors import RequestValidationError
from nitelos.schemas import parse_request

try:
    from mcp.server.lowlevel import Server  # type: ignore[import-not-found, unused-ignore]  # optional mcp extra; deepeval-precedent central override may replace
    from mcp.types import (  # type: ignore[import-not-found, unused-ignore]  # optional mcp extra; deepeval-precedent central override may replace
        CallToolResult,
        ListToolsResult,
        TextContent,
        Tool,
    )
except ImportError as _exc:  # pragma: no cover - exercised via subprocess test
    raise ImportError(
        'nitelos.integrations.mcp_server requires the mcp extra; install it with: pip install "nitelos[mcp]"'
    ) from None

__all__ = ["McpServerConfig", "build_server", "main"]

_MAX_ARGUMENT_BYTES = 262_144
logger = logging.getLogger("nitelos.mcp")

_TOOLS = (
    Tool(
        name="verify_outcome",
        description=(
            "Verify an outcome from supplied evidence (strict policy, no trust "
            "bindings: external-scope criteria abstain unless the host binds "
            "evidence outside this server)."
        ),
        input_schema={
            "type": "object",
            "properties": {"request": {"type": "object"}},
            "required": ["request"],
        },
    ),
    Tool(
        name="collect",
        description="Run one enabled collector (junit, git) and return its evidence.",
        input_schema={
            "type": "object",
            "properties": {"kind": {"type": "string"}},
            "required": ["kind"],
        },
    ),
    Tool(
        name="describe_criteria",
        description="Show the configured criteria (ids, descriptions, kinds, scopes).",
        input_schema={"type": "object", "properties": {}},
    ),
)


class McpServerConfig(BaseModel):
    """Server configuration: where criteria live and which collectors run."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    criteria_path: Path
    enabled_collectors: tuple[str, ...] = Field(default=(), min_length=0)
    request_max_age_seconds: int = Field(default=300, ge=0, le=86400)


def _tool_error(message: str) -> CallToolResult:
    return CallToolResult(content=[TextContent(type="text", text=message)], is_error=True)


def _tool_text(payload: Any) -> CallToolResult:
    return CallToolResult(content=[TextContent(type="text", text=json.dumps(payload, sort_keys=True))])


async def on_list_tools(context: Any, params: Any) -> ListToolsResult:
    """The tools/list handler; static — the tool set never depends on input."""
    return ListToolsResult(tools=list(_TOOLS))


async def on_call_tool(context: Any, params: Any) -> CallToolResult:
    """The tools/call handler; every path returns a CallToolResult."""
    name = str(getattr(params, "name", ""))
    arguments = getattr(params, "arguments", None) or {}
    size = len(json.dumps(arguments, default=str).encode("utf-8"))
    logger.debug("mcp call: tool=%s argument_bytes=%d", name, size)
    if size > _MAX_ARGUMENT_BYTES:
        logger.debug("mcp call rejected: tool=%s reason=argument_too_large", name)
        return _tool_error("arguments exceed the 256 KiB cap")
    try:
        if name == "verify_outcome":
            return _verify_outcome(arguments)
        if name == "collect":
            return _collect(arguments)
        if name == "describe_criteria":
            return _describe_criteria()
    except Exception:  # noqa: BLE001 - tool errors never crash the server
        logger.debug("mcp call failed: tool=%s reason=exception", name)
        return _tool_error("tool execution failed")
    logger.debug("mcp call rejected: tool=%s reason=unknown_tool", name)
    return _tool_error(f"unknown tool: {name}")


def _verify_outcome(arguments: Mapping[str, Any]) -> CallToolResult:
    request = arguments.get("request")
    if not isinstance(request, Mapping):
        return _tool_error("request must be an object")
    try:
        parsed = parse_request(json.dumps(dict(request)))
    except (RequestValidationError, ValueError, TypeError):
        return _tool_error(
            "request rejected by the schema (unknown fields, trust-looking keys "
            "and malformed evidence are refused)"
        )
    result = Verifier().verify(parsed)
    payload = {
        "execution_status": str(result.execution_status),
        "decision": str(result.decision) if result.decision is not None else None,
        "reason_codes": [str(code) for code in result.reason_codes],
        "criteria": [
            {
                "criterion_id": c.criterion_id,
                "state": str(c.state),
                "basis": str(c.basis),
                "reason_codes": [str(code) for code in c.reason_codes],
            }
            for c in result.criteria
        ],
    }
    logger.debug(
        "verify_outcome: status=%s decision=%s criteria=%d",
        str(result.execution_status),
        str(result.decision),
        len(result.criteria),
    )
    return _tool_text(payload)


def _collect(arguments: Mapping[str, Any]) -> CallToolResult:
    import importlib  # noqa: PLC0415 - lazy: collector modules load only on demand

    from nitelos.cli import KIND_TARGETS  # noqa: PLC0415 - lazy: keeps import light for non-collect calls

    kind = str(arguments.get("kind", ""))
    config = _ACTIVE_CONFIG[0]
    if kind not in config.enabled_collectors or kind not in KIND_TARGETS:
        return _tool_error(f"collector kind not enabled on this server: {kind}")
    target = KIND_TARGETS[kind]
    module_name, _, attribute = target.partition(":")
    try:
        collector = getattr(importlib.import_module(module_name), attribute)
    except Exception:  # noqa: BLE001 - missing extra
        return _tool_error(f"collector {kind} unavailable (install its nitelos extra)")
    collect_config = dict(arguments.get("config", {}))
    collect_config.setdefault("evidence_id", f"mcp-{kind}")
    collect_config.setdefault("checkpoint_id", "stop")
    collect_config.setdefault("subject", {"source": "mcp"})
    result = run_collector(collector, collect_config)
    if result.error is not None:
        logger.debug("collect: kind=%s error=%s", kind, result.error.code.value)
        return _tool_text({"collector_error": result.error.code.value})
    logger.debug("collect: kind=%s evidence=%d", kind, len(result.evidence))
    return _tool_text(
        {"evidence": [json.loads(item.model_dump_json(exclude_none=True)) for item in result.evidence]}
    )


def _describe_criteria() -> CallToolResult:
    config = _ACTIVE_CONFIG[0]
    try:
        document = json.loads(config.criteria_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return _tool_error("criteria file unreadable (configure the server host-side)")
    raw_criteria = document.get("criteria") if isinstance(document, dict) else None
    criteria = raw_criteria if isinstance(raw_criteria, list) else []
    view = [
        {
            "id": c.get("id"),
            "description": c.get("description"),
            "kind": c.get("kind"),
            "scope": c.get("scope"),
        }
        for c in criteria
        if isinstance(c, dict)
    ]
    logger.debug("describe_criteria: criteria=%d", len(view))
    return _tool_text({"version": document.get("version"), "criteria": view})


_ACTIVE_CONFIG: list[McpServerConfig] = [McpServerConfig(criteria_path=Path(".nitelos/criteria.json"))]


def build_server(config: McpServerConfig) -> Server:
    """Wire the handlers into a lowlevel Server (constructor registration)."""
    _ACTIVE_CONFIG[0] = config
    return Server("nitelos", on_list_tools=on_list_tools, on_call_tool=on_call_tool)


async def _run_stdio(config: McpServerConfig) -> None:
    from mcp.server.stdio import stdio_server  # type: ignore[import-not-found, unused-ignore]  # optional mcp extra  # noqa: PLC0415  # lazy: serving path only

    server = build_server(config)
    options = server.create_initialization_options()
    async with stdio_server() as streams:
        await server.run(streams[0], streams[1], options, raise_exceptions=True)


def main(argv: list[str] | None = None) -> int:
    """Serve MCP over stdio (python -m nitelos.integrations.mcp_server)."""
    logging.basicConfig(level=logging.DEBUG, stream=sys.stderr)
    criteria = os.environ.get("NITELOS_MCP_CRITERIA", ".nitelos/criteria.json")
    collectors = tuple(
        kind for kind in os.environ.get("NITELOS_MCP_COLLECTORS", "junit,git").split(",") if kind
    )
    config = McpServerConfig(criteria_path=Path(criteria), enabled_collectors=collectors)
    asyncio.run(_run_stdio(config))
    return 0


if __name__ == "__main__":  # pragma: no cover - module execution path
    raise SystemExit(main())
