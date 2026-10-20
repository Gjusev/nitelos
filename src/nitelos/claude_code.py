"""The Claude Code plugin runtime (plan F7, NIT-023; extra ``claude-code``).

Authority: the hook process is the trusted host (ADR-015 finding 3). It loads
versioned criteria from ``.nitelos/criteria.json`` in the working directory —
never from the agent's claim — runs the configured collectors itself, binds
only the evidence those collectors produced in this invocation, and calls the
v0.1 ``Verifier``.

Decision mapping (ADR-016): failure blocks (JSON ``{"decision": "block",
"reason": ...}`` with exit 0); success passes silently; abstention warns via
``systemMessage`` unless ``on_abstain`` is ``block``; internal errors warn and
exit 0. Exit code 2 is never used.

Empty collector results: a criterion that cites an evidence id no collector
produced is rewritten to cite nothing, so the verifier abstains with
MISSING_EVIDENCE (never STALE with zero evidence). The collector-layer error
codes are shown next to the outcome in messages.

Turn start (no field exists on Stop): the plugin's own UserPromptSubmit hook
writes the turn start, keyed by session and prompt id, to a per-session state
file under the OS temp directory (the only write; the repo is never touched).
The chain is: that record, then the transcript (best effort, undocumented
schema), then abstention with STALE_EVIDENCE.

The loop guard never blocks twice on the same evidence fingerprint while
``stop_hook_active`` is set: one repeat block degrades to a warning.
"""

from __future__ import annotations

import hashlib
import importlib
import json
import logging
import os
import re
import sys
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from nitelos import Verifier, canonical_json
from nitelos.collect import CollectorError, host_trust_bindings, run_collector
from nitelos.schemas import parse_request

_MAX_STDIN_BYTES = 1_048_576
logger = logging.getLogger("nitelos.hook")
_STATE_SESSION_RE = re.compile(r"[^A-Za-z0-9._-]")
_SAFE_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}")


def _now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


class CriteriaFile(BaseModel):
    """``.nitelos/criteria.json`` schema v1 (strict; unknown fields reject)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    version: str
    profile: str
    checkpoint_id: str = "stop"
    collectors: dict[str, dict[str, Any]] = Field(default_factory=dict)
    criteria: list[dict[str, Any]] = Field(min_length=1)
    on_abstain: str = "warn"
    max_seconds: float = Field(default=2.0, gt=0.0, le=600.0)


def _warn(message: str) -> dict[str, Any]:
    return {"systemMessage": f"nitelos: {message}"}


def _block(reason: str) -> dict[str, Any]:
    return {"decision": "block", "reason": f"nitelos: {reason}"}


def _state_path(state_dir: Path, session_id: str) -> Path:
    safe = _STATE_SESSION_RE.sub("-", session_id)[:64] or "session"
    return state_dir / f"session-{safe}.json"


def _read_state(state_dir: Path, session_id: str) -> dict[str, Any]:
    try:
        loaded: dict[str, Any] = json.loads(_state_path(state_dir, session_id).read_text(encoding="utf-8"))
        return loaded
    except (OSError, ValueError):
        return {}


def _write_state(state_dir: Path, session_id: str, data: dict[str, Any]) -> None:
    state_dir.mkdir(parents=True, exist_ok=True)
    path = _state_path(state_dir, session_id)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data), encoding="utf-8")
    tmp.replace(path)


def _try_write_state(state_dir: Path, session_id: str, state: dict[str, Any], fingerprint: str) -> None:
    """Best-effort loop-guard write: never let it break the block/warn path.

    A failed state write (unwritable temp dir, transient OSError) only means
    the loop guard may repeat a block; the decision document is unaffected,
    per ADR-016 ("on internal error, warn and exit 0").
    """
    try:
        _write_state(state_dir, session_id, {**state, "last_block_fingerprint": fingerprint})
    except OSError:
        logger.debug("loop-guard state write failed (best-effort; block unaffected)")


def run_prompt(event_text: str, *, state_dir: Path) -> dict[str, Any]:
    """UserPromptSubmit role: record the turn start; silent on success."""
    try:
        event = json.loads(event_text)
        session_id = str(event.get("session_id", ""))
        prompt_id = str(event.get("prompt_id", ""))
        timestamp = event.get("timestamp") or _now_iso()
        if not _SAFE_ID_RE.fullmatch(session_id):
            return {}
        _write_state(
            state_dir,
            session_id,
            {
                "turn_start_key": f"{session_id}:{prompt_id}",
                "turn_start": str(timestamp),
                "wall": time.time(),
            },
        )
    except (ValueError, TypeError):
        return {}
    return {}


def _resolve_turn_start(event: dict[str, Any], state_dir: Path) -> tuple[str | None, str]:
    session_id = str(event.get("session_id", ""))
    prompt_id = str(event.get("prompt_id", ""))
    state = _read_state(state_dir, session_id)
    if state.get("turn_start_key") == f"{session_id}:{prompt_id}" and state.get("turn_start"):
        return str(state["turn_start"]), "state"
    transcript = str(event.get("transcript_path", ""))
    if transcript:
        try:
            stamp = _last_user_timestamp(Path(transcript))
            if stamp:
                return stamp, "transcript"
        except OSError:
            pass
    return None, "none"


def _last_user_timestamp(transcript: Path) -> str | None:
    """Best effort: the timestamp of the last user line in a session JSONL."""
    stamp: str | None = None
    with transcript.open("rb") as handle:
        handle.seek(0, 2)
        size = handle.tell()
        handle.seek(max(0, size - 262_144))
        for line in handle.read().splitlines()[-200:]:
            try:
                entry = json.loads(line)
            except ValueError:
                continue
            if entry.get("type") == "user" and entry.get("timestamp"):
                stamp = str(entry["timestamp"])
    return stamp


def _collect_all(
    cwd: Path,
    criteria: CriteriaFile,
    turn_start: str | None,
) -> tuple[list[Any], list[Any], list[str], list[str]]:
    """Run every configured collector; returns (evidence, bindings, notes, fatal)."""
    from nitelos.cli import KIND_TARGETS  # noqa: PLC0415 - lazy: keeps nitelos import light for prompt/check roles

    evidence: list[Any] = []
    bindings: list[Any] = []
    notes: list[str] = []
    fatal: list[str] = []
    for kind, raw_config in criteria.collectors.items():
        target = KIND_TARGETS.get(kind)
        if not target:
            fatal.append(f"collector kind {kind} is not known")
            continue
        module_name, _, attribute = target.partition(":")
        try:
            collector = getattr(importlib.import_module(module_name), attribute)
        except Exception:  # noqa: BLE001 - any import failure means the extra is absent
            fatal.append(f"collector {kind} unavailable (install its nitelos extra)")
            continue
        config_map: dict[str, Any] = dict(raw_config)
        config_map["checkpoint_id"] = criteria.checkpoint_id
        if turn_start is not None and "turn_start" in collector.config_model.model_fields:
            config_map["turn_start"] = turn_start
        try:
            result = run_collector(collector, config_map)
        except CollectorError as error:
            notes.append(f"collector {kind}: {error.code.value}")
            continue
        if result.error is not None:
            notes.append(f"collector {kind}: {result.error.code.value}")
            continue
        evidence.extend(result.evidence)
        bindings.extend(host_trust_bindings(result))
    return evidence, bindings, notes, fatal


def _observed_value(criterion: dict[str, Any], evidence_by_id: dict[str, Any]) -> str:
    pointer = str(criterion.get("pointer", "")).lstrip("/")
    node: Any = None
    for evidence_id in criterion.get("evidence_ids", []):
        item = evidence_by_id.get(evidence_id)
        if item is not None:
            node = dict(item.data) if hasattr(item, "data") else None
            break
    if node is None:
        return "<unavailable>"
    for raw_token in pointer.split("/") if pointer else []:
        token = raw_token.replace("~1", "/").replace("~0", "~")
        if isinstance(node, dict):
            node = node.get(token)
        elif isinstance(node, list) and token.isdigit():
            node = node[int(token)] if int(token) < len(node) else None
        else:
            return "<unavailable>"
        if node is None:
            return "<unavailable>"
    return json.dumps(node)[:120]


def _fingerprint(criteria: CriteriaFile, evidence: list[Any], decision: str) -> str:
    payload = {
        "criteria": hashlib.sha256(canonical_json(criteria.criteria).encode("utf-8")).hexdigest(),
        "decision": decision,
        "evidence": sorted((item.id, item.sha256) for item in evidence),
    }
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def _decide(result: Any, criteria: CriteriaFile, evidence: list[Any]) -> dict[str, Any]:
    evidence_by_id = {item.id: item for item in evidence}
    if result.decision == "failure":
        failed = [c for c in result.criteria if str(c.state) == "refuted"]
        unknown = [c for c in result.criteria if str(c.state) == "unknown"]
        parts = []
        for item in failed:
            raw = next((c for c in criteria.criteria if c.get("id") == item.criterion_id), {})
            value = _observed_value(raw, evidence_by_id)
            ref = item.evidence_refs[0].evidence_id if item.evidence_refs else "-"
            detail = ""
            cited = raw.get("evidence_ids", [])
            source = evidence_by_id.get(cited[0]) if cited else None
            if source is not None and hasattr(source, "data"):
                failed_ids = dict(source.data).get("failed_ids")
                if isinstance(failed_ids, (list, tuple)) and failed_ids:
                    shown = ", ".join(str(fid) for fid in list(failed_ids)[:5])
                    detail = f" failing: {shown}"
            parts.append(
                f"criterion {item.criterion_id} ({raw.get('description', '')}): "
                f"observed {value} via {ref}.{detail}"
            )
        reason = "verification FAILED — " + "; ".join(parts)
        if unknown:
            reason += (
                f" (undecided: {', '.join(c.criterion_id for c in unknown)} — supply the missing evidence)"
            )
        return _block(reason)
    if result.decision == "abstained":
        lines = [
            f"{c.criterion_id}: {', '.join(c.reason_codes)}"
            for c in result.criteria
            if str(c.state) == "unknown"
        ]
        message = "undecided — " + "; ".join(lines)
        return _block(message) if criteria.on_abstain == "block" else _warn(message)
    return {}


def run_stop(stdin_text: str, *, state_dir: Path, require_turn_start: bool = True) -> dict[str, Any]:
    """The Stop hook: run one verification and return the output document."""
    try:
        event = json.loads(stdin_text[:_MAX_STDIN_BYTES])
    except ValueError:
        return _warn("hook input is not valid JSON")
    cwd_text = str(event.get("cwd", ""))
    if not cwd_text:
        return _warn("hook input carries no cwd")
    cwd = Path(cwd_text)
    try:
        criteria = CriteriaFile.model_validate(
            json.loads((cwd / ".nitelos" / "criteria.json").read_text(encoding="utf-8"))
        )
    except Exception as error:  # noqa: BLE001 - any criteria failure is a warn
        return _warn(
            f"criteria invalid or missing ({type(error).__name__}); "
            "run /nitelos:init to create .nitelos/criteria.json"
        )

    turn_start, source = _resolve_turn_start(event, state_dir)
    if require_turn_start and turn_start is None:
        return (
            _warn(
                "undecided — STALE_EVIDENCE: no turn-start record "
                "(UserPromptSubmit hook) and no usable transcript timestamp"
            )
            if criteria.on_abstain != "block"
            else _block("undecided — STALE_EVIDENCE: no turn start available")
        )

    started = time.monotonic()
    try:
        evidence, bindings, notes, fatal = _collect_all(cwd, criteria, turn_start)
    except Exception:  # noqa: BLE001 - internal error path per ADR-016
        return _warn("internal error while collecting evidence")
    elapsed = time.monotonic() - started
    if fatal:
        return _warn("; ".join(sorted(fatal)))
    if elapsed > criteria.max_seconds:
        return _warn(
            f"collector budget overrun ({elapsed:.2f}s > {criteria.max_seconds}s); "
            "verification skipped — check the criteria or raise max_seconds"
        )

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
        "request_id": f"hook-{event.get('session_id', 'session')}",
        "objective": "Agent stop verification",
        "checkpoint_id": criteria.checkpoint_id,
        "as_of": _now_iso(),
        "criteria": criteria_maps,
        "evidence": wire_evidence,
        "metadata": {
            "agent_report_sha256": hashlib.sha256(message.encode("utf-8")).hexdigest() if message else None,
            "agent_report_chars": len(message),
            "profile": criteria.profile,
            "turn_start_source": source,
            "collector_notes": notes,
        },
    }
    try:
        request = parse_request(json.dumps(request_wire))
    except Exception:  # noqa: BLE001 - request build failure is an internal warn
        return _warn("criteria could not be turned into a verification request")
    result = Verifier(trust_bindings=tuple(bindings)).verify(request)
    if result.execution_status != "ok":
        return _warn(f"verification error ({result.error.code.value if result.error else '?'})")
    document = _decide(result, criteria, evidence)
    if document.get("decision") == "block":
        session_id = str(event.get("session_id", ""))
        state = _read_state(state_dir, session_id)
        fingerprint = _fingerprint(criteria, evidence, "failure")
        if event.get("stop_hook_active") and state.get("last_block_fingerprint") == fingerprint:
            _try_write_state(state_dir, session_id, state, fingerprint)
            return _warn(
                "same failed verification was already blocked once this session; "
                "passing to avoid a loop — fix the criteria or the evidence"
            )
        _try_write_state(state_dir, session_id, state, fingerprint)
    return document


def run_check(*, cwd: Path, state_dir: Path) -> list[str]:
    """/nitelos:check role: same pipeline, human summary, never blocks."""
    event = {
        "session_id": "check",
        "prompt_id": "check",
        "cwd": str(cwd),
        "stop_hook_active": False,
        "last_assistant_message": "",
        "hook_event_name": "Stop",
    }
    document = run_stop(json.dumps(event), state_dir=state_dir, require_turn_start=False)
    lines = ["nitelos check:"]
    if document.get("decision") == "block":
        # /nitelos:check never blocks; it reports what the Stop hook would do.
        lines.append(f"  outcome: WOULD BLOCK — {document['reason']}")
    elif "systemMessage" in document:
        lines.append(f"  outcome: warning — {document['systemMessage']}")
    else:
        lines.append("  outcome: success (all criteria supported)")
    return lines


def _default_state_dir() -> Path:
    override = os.environ.get("NITELOS_HOOK_STATE_DIR")
    return Path(override) if override else Path(tempfile.gettempdir()) / "nitelos-hooks"


def main(argv: list[str] | None = None) -> int:
    """Console entry point; always exits 0 (see the module docstring)."""
    role = os.environ.get("NITELOS_HOOK_ROLE", "stop").strip().lower()
    state_dir = _default_state_dir()
    if role == "prompt":
        document = run_prompt(sys.stdin.read(_MAX_STDIN_BYTES), state_dir=state_dir)
    elif role == "check":
        for line in run_check(cwd=Path(os.getcwd()), state_dir=state_dir):
            print(line)
        return 0
    else:
        document = run_stop(sys.stdin.read(_MAX_STDIN_BYTES), state_dir=state_dir)
    if document:
        print(json.dumps(document))
    return 0


if __name__ == "__main__":  # pragma: no cover - module execution path
    raise SystemExit(main())
