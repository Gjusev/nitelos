"""Claude Code Stop-hook adapter (extra ``hooks``) — thin delegate.

The full Claude Code plugin already lives in :mod:`nitelos.claude_code`
(NIT-023): stdin parsing, ``.nitelos/criteria.json`` / ``criteria.yaml``
loading, collectors, the verifier, block reasons, the evidence-fingerprint
loop guard keyed on ``stop_hook_active``, and abstain-as-warn. This adapter
exposes the same handlers under the hooks package so all three harnesses have
one import surface (``nitelos.integrations.hooks``) and one install command
(``nitelos hooks install --harness claude-code``).

Blocking semantics (unchanged, per the hooks reference): exit 0 with
``{"decision": "block", "reason": ...}``; ``reason`` is required and becomes
Claude's next instruction. ``stop_hook_active`` is respected: while Claude
Code is already continuing from a stop hook, the same failed verification
(identical evidence fingerprint) blocks at most once and then degrades to a
warning — Claude Code itself caps consecutive continuations at 8.
"""

from __future__ import annotations

from typing import Any

from nitelos.claude_code import (  # re-exported for the hooks CLI surface
    _default_state_dir,
    run_check,
    run_prompt,
    run_stop,
)
from nitelos.claude_code import (
    main as _plugin_main,
)

__all__ = ["main", "run_check", "run_prompt", "run_stop"]


def handle_stop(stdin_text: str) -> dict[str, Any]:
    """Stop-event handler used by tests and the golden fixtures."""
    return run_stop(stdin_text, state_dir=_default_state_dir())


def main(argv: list[str] | None = None) -> int:
    """Same entry contract as the plugin's ``nitelos-hook`` script (exit 0 always)."""
    return _plugin_main(argv)


if __name__ == "__main__":  # pragma: no cover - module execution path
    raise SystemExit(main())
