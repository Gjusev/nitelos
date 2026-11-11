"""Coding-agent hook adapters (extra ``hooks``; Project 1B).

Authority: docs/planning/20-hooks-and-langfuse-research.md (recommended design
items 2 and 3, comparison table 1.4). One verify pipeline — collectors, the
v0.1 ``Verifier``, block reasons — shared with the Claude Code plugin
(``nitelos.claude_code``), wrapped in harness-specific adapters:

- ``claude_code``: Stop-hook blocking via ``{"decision": "block", "reason"}``
  (exit 0); ``stop_hook_active`` plus the evidence-fingerprint loop guard never
  block the same failed verification twice in a row.
- ``codex``: the same JSON shape, but per the Codex hooks docs a Stop block is
  an auto-created *continuation prompt* whose text is ``reason`` (never a turn
  rejection); any hook's ``continue: false`` overrides and allows the stop, so
  this adapter never emits ``continue`` at all. Abstention logs to stderr and
  never blocks.
- ``opencode``: observe-and-report ONLY. OpenCode has no completion-blocking
  hook: the agent finishing cannot be stopped; the ``session.idle`` event is
  read-only. A generated plugin (see :func:`opencode.plugin_source`) calls the
  Python observe command and reports; an optional ``tool.execute.before`` guard
  (env ``NITELOS_OPENCODE_TOOL_GUARD``) can block individual tool calls, which
  is the only thing OpenCode can block.

The ``hooks`` extra is nearly stdlib-only: PyYAML is included for
``.nitelos/criteria.yaml`` support; JSON criteria files need no dependency.
"""

from nitelos.integrations.hooks import claude_code, codex, install, opencode

__all__ = ["claude_code", "codex", "install", "opencode"]
