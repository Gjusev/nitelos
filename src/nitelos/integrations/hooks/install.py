"""Config-snippet installer for the hook adapters (``nitelos hooks install``).

Writes one config snippet per harness. Safety rule: an existing target file is
never overwritten unless ``--force`` is passed; without ``--target`` the
snippet is only printed to stdout, which can never clobber a config.

Snippets:

- ``claude-code``: ``.claude/settings.json`` fragment wiring UserPromptSubmit
  (turn-start record) and Stop (verify + block) to the plugin runtime.
- ``codex``: ``.codex/hooks.json`` with the Stop command. The snippet is
  best-effort against the documented hooks file (research Q7): Codex requires
  every non-managed hook to be reviewed and trusted per hash via ``/hooks``
  before it runs — the printed guidance says so explicitly.
- ``opencode``: ``.opencode/plugins/nitelos-observe.ts`` — the observe-only
  plugin source (no completion blocking exists in OpenCode).
"""

from __future__ import annotations

import sys
from pathlib import Path

from nitelos.integrations.hooks.opencode import plugin_source

HARNESSES = ("claude-code", "codex", "opencode")

CLAUDE_CODE_SNIPPET = """{
  "hooks": {
    "UserPromptSubmit": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "NITELOS_HOOK_ROLE=prompt python -m nitelos.claude_code",
            "timeout": 10
          }
        ]
      }
    ],
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python -m nitelos.claude_code",
            "timeout": 60
          }
        ]
      }
    ]
  }
}
"""

CODEX_SNIPPET = """{
  "hooks": {
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python -m nitelos.integrations.hooks.codex",
            "timeout": 600
          }
        ]
      }
    ]
  }
}
"""

_CODEX_TRUST_NOTE = (
    "# Codex trust step (required): after writing this file, run `/hooks` in Codex\n"
    "# and review+trust the nitelos hook (per-hash). Untrusted hooks never run.\n"
    "# Semantics: a Stop block makes Codex CONTINUE with the reason as a new\n"
    "# continuation prompt — it does not reject the turn.\n"
)

_DEFAULT_TARGETS = {
    "claude-code": ".claude/settings.json",
    "codex": ".codex/hooks.json",
    "opencode": ".opencode/plugins/nitelos-observe.ts",
}


def install_snippet(harness: str) -> str:
    """Return the config snippet text for one harness."""
    if harness == "claude-code":
        return CLAUDE_CODE_SNIPPET
    if harness == "codex":
        return _CODEX_TRUST_NOTE + CODEX_SNIPPET
    if harness == "opencode":
        return plugin_source()
    raise ValueError(f"unknown harness {harness!r}; known: {', '.join(HARNESSES)}")


def default_target(harness: str) -> Path:
    return Path(_DEFAULT_TARGETS[harness])


def write_config(harness: str, target: Path, *, force: bool = False) -> bool:
    """Write the snippet to ``target``; refuse to overwrite unless ``force``.

    Returns False (and writes nothing) when the target exists without
    ``--force``. Creates parent directories as needed.
    """
    if target.exists() and not force:
        return False
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(install_snippet(harness), encoding="utf-8")
    return True


def main(argv: list[str] | None = None) -> int:
    """``nitelos hooks install --harness HARNESS [--target FILE] [--force]``."""
    import argparse  # noqa: PLC0415 - lazy: keeps non-CLI imports light

    parser = argparse.ArgumentParser(prog="nitelos hooks install")
    parser.add_argument("--harness", required=True, choices=HARNESSES)
    parser.add_argument(
        "--target", type=Path, default=None, help="config file to write (default: print to stdout)"
    )
    parser.add_argument("--force", action="store_true", help="overwrite an existing target file")
    args = parser.parse_args(argv)
    if args.target is None:
        sys.stdout.write(install_snippet(args.harness))
        return 0
    if write_config(args.harness, args.target, force=args.force):
        print(f"wrote {args.harness} hook config to {args.target}")
        return 0
    print(
        f"refusing to overwrite existing config: {args.target} (pass --force to replace it)",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":  # pragma: no cover - module execution path
    raise SystemExit(main())
