"""Codex CLI Stop-hook adapter (extra ``hooks``).

Semantics per the Codex hooks documentation (research section 1.2): a Stop
hook may return JSON on stdout with exit 0; ``{"decision": "block", "reason"}`
does **not** reject the turn — Codex creates a new continuation prompt whose
text is ``reason``. Exit 2 with the reason on stderr does the same. Because
any matching hook's ``continue: false`` takes precedence and lets the turn
end, this adapter never emits ``continue`` at all (staying silent on that
field is the safe default).

Abstention never blocks: it is logged to stderr (ignored on exit 0) and the
document is ``{}``. The evidence-fingerprint loop guard is shared with the
Claude Code plugin, so while ``stop_hook_active`` is set the same failed
verification blocks at most once; the repeat degrades to a stderr warning.

Trust step (research Q7): Codex requires non-managed hooks to be reviewed and
trusted per hash via ``/hooks`` before they run; ``nitelos hooks install
--harness codex`` prints that instruction with the snippet.
"""

from __future__ import annotations

import hashlib
import json
import sys
import time
from pathlib import Path
from typing import Any

from nitelos import Verifier
from nitelos.claude_code import (
    _MAX_STDIN_BYTES,
    _collect_all,
    _decide,
    _default_state_dir,
    _fingerprint,
    _now_iso,
    _read_state,
    _try_write_state,
    load_criteria,
)
from nitelos.schemas import parse_request


def _stderr(message: str) -> None:
    print(f"nitelos: {message}", file=sys.stderr)


def _empty() -> dict[str, Any]:
    return {}


def _block(reason: str) -> dict[str, Any]:
    # Codex: `reason` becomes the next continuation prompt (never a rejection).
    return {"decision": "block", "reason": f"nitelos: {reason}"}


def run_stop(stdin_text: str, *, state_dir: Path) -> dict[str, Any]:
    """Codex ``Stop`` handler: verify and return the output document.

    Differences from the Claude Code Stop hook: no turn-start requirement
    (the Codex criteria are typically git-diff/test based), abstention never
    blocks, and stdout always carries valid JSON when the process exits 0.
    """
    try:
        event = json.loads(stdin_text[:_MAX_STDIN_BYTES])
    except ValueError:
        _stderr("hook input is not valid JSON")
        return _empty()
    cwd_text = str(event.get("cwd", ""))
    if not cwd_text:
        _stderr("hook input carries no cwd")
        return _empty()
    cwd = Path(cwd_text)
    try:
        criteria = load_criteria(cwd)
    except Exception as error:  # noqa: BLE001 - any criteria failure is a warn
        _stderr(f"criteria invalid or missing ({type(error).__name__})")
        return _empty()

    started = time.monotonic()
    try:
        turn_start = None  # Codex events carry no prompt_id turn-start chain here
        evidence, bindings, notes, fatal = _collect_all(cwd, criteria, turn_start)
    except Exception:  # noqa: BLE001 - internal error path per ADR-016
        _stderr("internal error while collecting evidence")
        return _empty()
    elapsed = time.monotonic() - started
    if fatal:
        _stderr("; ".join(sorted(fatal)))
        return _empty()
    if elapsed > criteria.max_seconds:
        _stderr(f"collector budget overrun ({elapsed:.2f}s > {criteria.max_seconds}s); verification skipped")
        return _empty()

    collected_ids = {item.id for item in evidence}
    criteria_maps = []
    for raw in criteria.criteria:
        entry = dict(raw)
        entry["evidence_ids"] = [e for e in entry.get("evidence_ids", []) if e in collected_ids]
        criteria_maps.append(entry)
    wire_evidence = [json.loads(item.model_dump_json(exclude_none=True)) for item in evidence]
    message = str(event.get("last_assistant_message", ""))
    request_wire = {
        "schema_version": "1",
        "request_id": f"codex-{event.get('session_id', 'session')}",
        "objective": "Agent stop verification",
        "checkpoint_id": criteria.checkpoint_id,
        "as_of": _now_iso(),
        "criteria": criteria_maps,
        "evidence": wire_evidence,
        "metadata": {
            "agent_report_sha256": hashlib.sha256(message.encode("utf-8")).hexdigest() if message else None,
            "agent_report_chars": len(message),
            "profile": criteria.profile,
            "collector_notes": notes,
            "harness": "codex",
        },
    }
    try:
        request = parse_request(json.dumps(request_wire))
    except Exception:  # noqa: BLE001
        _stderr("criteria could not be turned into a verification request")
        return _empty()
    result = Verifier(trust_bindings=tuple(bindings)).verify(request)
    if result.execution_status != "ok":
        _stderr(f"verification error ({result.error.code.value if result.error else '?'})")
        return _empty()

    document = _decide(result, criteria, evidence)
    if result.decision == "abstained" and document.get("decision") == "block":
        # Abstention never blocks on Codex: _decide blocks abstentions only
        # when configured; override to a logged warning instead.
        undecided = [c.criterion_id for c in result.criteria if str(c.state) == "unknown"]
        _stderr("; ".join(undecided) or "undecided")
        return _empty()
    if document.get("decision") == "block":
        session_id = str(event.get("session_id", ""))
        state = _read_state(state_dir, session_id)
        fingerprint = _fingerprint(criteria, evidence, "failure")
        if event.get("stop_hook_active") and state.get("last_block_fingerprint") == fingerprint:
            _try_write_state(state_dir, session_id, state, fingerprint)
            _stderr(
                "same failed verification was already blocked once this session; "
                "passing to avoid a loop — fix the criteria or the evidence"
            )
            return _empty()
        _try_write_state(state_dir, session_id, state, fingerprint)
        return document
    if "systemMessage" in document:
        # abstain-as-warn (on_abstain default): log, never block
        _stderr(str(document["systemMessage"]))
    return _empty()


def main(argv: list[str] | None = None) -> int:
    """Console/module entry point; always exits 0 (errors are stderr notes)."""
    document = run_stop(sys.stdin.read(_MAX_STDIN_BYTES), state_dir=_default_state_dir())
    print(json.dumps(document))
    return 0


if __name__ == "__main__":  # pragma: no cover - module execution path
    raise SystemExit(main())
