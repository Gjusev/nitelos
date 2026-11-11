"""OpenCode adapter — observe-and-report ONLY (extra ``hooks``).

Explicit non-goal: completion blocking. OpenCode has no Stop-equivalent hook;
the agent finishing cannot be blocked. When a session goes idle, plugins only
receive the read-only ``session.idle`` **event** (research section 1.3), which
is observational, not a decision point. The only things OpenCode can block are
individual tool calls (``tool.execute.before`` throw / permission deny).

What this adapter ships:

- :func:`plugin_source`: the TypeScript source for
  ``.opencode/plugins/nitelos-observe.ts``. On ``session.idle`` it runs the
  Python observe command (``python -m
  nitelos.integrations.hooks.opencode observe``) with the event JSON on stdin
  and prints the report — it can never prevent the session from ending.
- the observe command itself (:func:`run_observe`): loads criteria from the
  project's ``.nitelos/``, runs the same verify pipeline, prints a report,
  and records a Langfuse categorical score when ``NITELOS_LANGFUSE_TRACE_ID``
  is set and the ``langfuse`` extra is installed. The exit code is always 0
  and it never blocks — by design, and because OpenCode gives this process no
  decision power at session end.
- an optional tool-call guard in the generated plugin, enabled by setting
  ``NITELOS_OPENCODE_TOOL_GUARD`` to a regex of tool names: ``tool.execute.before``
  throws so the call is blocked with the nitelos reason (the documented
  OpenCode mechanism). Off by default.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from nitelos import Verifier
from nitelos.claude_code import (
    _MAX_STDIN_BYTES,
    _collect_all,
    _now_iso,
    load_criteria,
)
from nitelos.schemas import VerificationResult, parse_request

OBSERVE_MODULE = "nitelos.integrations.hooks.opencode"


def verify_directory(cwd: Path) -> tuple[VerificationResult | None, str | None]:
    """Run the shared pipeline over ``cwd``; returns (result, note).

    ``result`` is ``None`` with a note when criteria are missing/invalid or the
    pipeline hits an internal error — for OpenCode these degrade to report
    lines, never failures.
    """
    try:
        criteria = load_criteria(cwd)
    except Exception as error:  # noqa: BLE001 - reported, never raised
        return None, f"criteria unavailable ({type(error).__name__}); nothing verified"
    try:
        evidence, bindings, notes, fatal = _collect_all(cwd, criteria, None)
    except Exception:  # noqa: BLE001
        return None, "internal error while collecting evidence"
    if fatal:
        return None, "; ".join(sorted(fatal))
    collected_ids = {item.id for item in evidence}
    criteria_maps = []
    for raw in criteria.criteria:
        entry = dict(raw)
        entry["evidence_ids"] = [e for e in entry.get("evidence_ids", []) if e in collected_ids]
        criteria_maps.append(entry)
    wire_evidence = [json.loads(item.model_dump_json(exclude_none=True)) for item in evidence]
    request_wire = {
        "schema_version": "1",
        "request_id": "opencode-observe",
        "objective": "Agent session verification (observe-only)",
        "checkpoint_id": criteria.checkpoint_id,
        "as_of": _now_iso(),
        "criteria": criteria_maps,
        "evidence": wire_evidence,
        "metadata": {
            "agent_report_sha256": None,
            "agent_report_chars": 0,
            "profile": criteria.profile,
            "collector_notes": notes,
            "harness": "opencode",
        },
    }
    try:
        request = parse_request(json.dumps(request_wire))
    except Exception:  # noqa: BLE001
        return None, "criteria could not be turned into a verification request"
    result = Verifier(trust_bindings=tuple(bindings)).verify(request)
    if result.execution_status != "ok":
        return None, f"verification error ({result.error.code.value if result.error else '?'})"
    return result, None


def _report_lines(result: VerificationResult | None, note: str | None, cwd: Path) -> list[str]:
    lines = [f"observe (project {cwd}):"]
    if result is None:
        lines.append(f"  {note}")
        return lines
    if result.decision == "success":
        lines.append("  outcome: success (all criteria supported)")
    elif result.decision == "failure":
        failed = [c.criterion_id for c in result.criteria if str(c.state) == "refuted"]
        lines.append(f"  outcome: FAILURE — unsupported criteria: {', '.join(failed)}")
    else:
        undecided = [c.criterion_id for c in result.criteria if str(c.state) == "unknown"]
        lines.append(f"  outcome: undecided — {', '.join(undecided) or 'no evidence'}")
    lines.append("  note: OpenCode cannot block session end; this report is informational")
    return lines


def _record_score_best_effort(result: VerificationResult) -> list[str]:
    """Record the verdict as a Langfuse trace score when the extra is installed.

    Best effort by contract: any failure (extra absent, no credentials, API
    error) becomes a report line, never an error — this command cannot affect
    the session it observes.
    """
    trace_id = os.environ.get("NITELOS_LANGFUSE_TRACE_ID") or ""
    if not trace_id:
        return []
    try:
        from nitelos.integrations.langfuse import get_langfuse_client, record_verdict  # noqa: PLC0415 - lazy extra
    except Exception:  # noqa: BLE001
        return [f"langfuse score not recorded (langfuse extra not installed; trace {trace_id[:8]}…)"]
    try:
        client = get_langfuse_client()
        value = record_verdict(result, trace_id, client=client)
        return [f"langfuse score recorded: nitelos_outcome={value} on trace {trace_id[:8]}…"]
    except Exception as error:  # noqa: BLE001
        return [f"langfuse score not recorded ({type(error).__name__})"]


def run_observe(stdin_text: str) -> list[str]:
    """The ``observe`` role: run the verifier over the project and report."""
    cwd = Path(os.getcwd())
    try:
        event = json.loads(stdin_text[:_MAX_STDIN_BYTES]) if stdin_text.strip() else {}
    except ValueError:
        event = {}
    # an explicit "directory"/"cwd" from the OpenCode event wins over the process cwd
    directory = str(event.get("directory") or event.get("cwd") or "")
    if directory and Path(directory).is_dir():
        cwd = Path(directory)
    result, note = verify_directory(cwd)
    lines = _report_lines(result, note, cwd)
    if result is not None:
        lines.extend(_record_score_best_effort(result))
    return lines


def plugin_source() -> str:
    """TypeScript source for the observe-only OpenCode plugin (V2 API)."""
    return """// nitelos OpenCode plugin — observe-and-report ONLY.
// OpenCode cannot block a session from ending (no Stop hook; session.idle is a
// read-only event). This plugin reports the nitelos verification outcome and,
// optionally (env NITELOS_OPENCODE_TOOL_GUARD=<regex>), blocks individual tool
// calls — the only blocking OpenCode supports.
import type { Plugin } from "@opencode-ai/plugin"

const FALLBACK_MODULE = "OBSERVE_MODULE_PLACEHOLDER"
const OBSERVE_COMMAND = `python -m ${process.env.NITELOS_OPENCODE_MODULE ?? FALLBACK_MODULE} observe`

export const NitelosObservePlugin: Plugin = async ({ project, client, $ }) => {
  // Optional tool-call guard (off by default): tool.execute.before can block.
  const guard = process.env.NITELOS_OPENCODE_TOOL_GUARD
  const toolHooks = guard
    ? {
        "tool.execute.before": async (input: { tool: string }, _ctx: unknown) => {
          if (new RegExp(guard).test(input.tool)) {
            throw new Error(
              `nitelos: tool '${input.tool}' blocked by NITELOS_OPENCODE_TOOL_GUARD`,
            )
          }
        },
      }
    : {}

  return {
    ...toolHooks,
    event: async ({ event }) => {
      if (event.type !== "session.idle") return
      // Observe only: report the verification outcome; never block (impossible here).
      try {
        const proc = Bun.spawn(["bash", "-lc", OBSERVE_COMMAND], {
          stdin: new Blob([
            JSON.stringify({ directory: process.cwd(), session: event.properties?.sessionID }),
          ]),
          stdout: Bun.stdout,
          stderr: Bun.stderr,
        })
        await proc.exited
      } catch (error) {
        console.error("nitelos: observe failed", error)
      }
    },
  }
}

export default NitelosObservePlugin
""".replace("OBSERVE_MODULE_PLACEHOLDER", OBSERVE_MODULE)


def main(argv: list[str] | None = None) -> int:
    """Module entry point: ``python -m nitelos.integrations.hooks.opencode observe``."""
    role = (argv[0] if argv else (sys.argv[1] if len(sys.argv) > 1 else "observe")).strip().lower()
    if role == "plugin-source":
        print(plugin_source())
        return 0
    for line in run_observe(sys.stdin.read(_MAX_STDIN_BYTES)):
        print(line)
    return 0


if __name__ == "__main__":  # pragma: no cover - module execution path
    raise SystemExit(main())
