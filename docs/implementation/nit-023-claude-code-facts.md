# NIT-023 input: Claude Code hook and plugin facts (confirmed 2026-10-20)

Source: a claude-code-guide instance read the official docs on 2026-10-20. The quotes are WebFetch extractions,
not byte-exact copies. Recheck the live pages before relying on exact wording. Pages:
[hooks](https://code.claude.com/docs/en/hooks), [hooks guide](https://code.claude.com/docs/en/hooks-guide),
[plugin components](https://code.claude.com/docs/en/plugins/components),
[manifest reference](https://code.claude.com/docs/en/plugins/manifest-reference),
[create a plugin](https://code.claude.com/docs/en/plugins/create),
[marketplace reference](https://code.claude.com/docs/en/plugins/marketplace-reference),
[create a marketplace](https://code.claude.com/docs/en/plugins/create-marketplace),
[env vars](https://code.claude.com/docs/en/env-vars).

## Hook input (hooks reference)

- Common fields: `session_id`, `prompt_id` (absent until the first user input), `transcript_path`, `cwd`,
  `scratchpad_dir` (may be absent), `permission_mode`, `effort` (object with `level`), `hook_event_name`.
- Stop adds: `stop_hook_active` (bool), `last_assistant_message` (string), `background_tasks` (array),
  `session_crons` (array).
- SubagentStop adds: `stop_hook_active`, `agent_id`, `agent_type`, `agent_transcript_path`,
  `last_assistant_message`, `background_tasks`, `session_crons`.
- The tables give no types. Types are inferred from examples only, so parse defensively and ignore
  unknown fields.
- **No turn-start time field exists.**

## Blocking and warnings (hooks reference)

- Block a stop: exit 0 and print `{"decision": "block", "reason": "..."}` on stdout. `reason` is required and
  goes to Claude. Exit code 2 also blocks (the reason is taken from stderr) and overrides any JSON. The docs say
  to use one approach per hook. Nitelos uses JSON with exit 0.
- Warn without blocking: `systemMessage` ("Warning message shown to the user"). Whether a block reason is
  shown to the user is not documented.
- Other non-zero exit codes do not block. The user sees "hook error … Failed with non-blocking status code".
  A hook timeout discards the output, so the stop proceeds. The default timeout is 600 s for command hooks
  and can be set per handler with `timeout`. `onFailure` has no effect on Stop or SubagentStop.
- `stop_hook_active` is true when Claude is already continuing because of a stop hook. Built-in cap: after 8
  consecutive stop-hook continuations, Claude Code overrides the next block. The count resets on each tool call.
  `CLAUDE_CODE_STOP_HOOK_BLOCK_CAP` changes it.
- On SubagentStop, a block keeps the subagent running, and `reason` becomes its next instruction.
- Stop has no matcher support. A `matcher` on Stop is silently ignored.

## Transcript

- JSONL, but **the schema is not documented**. The file is written asynchronously and may lack the current
  turn at Stop time. The docs recommend `last_assistant_message` instead.

## Plugin format (plugin docs)

- Manifest: `.claude-plugin/plugin.json`. Only `name` is required. Common fields: `version`, `description`,
  `author{name}`, `homepage`, `repository`, `license`, `keywords`, `hooks`, `commands`.
- Hooks: `hooks/hooks.json` under a top-level `"hooks"` key, in the same shape as settings.json.
  `${CLAUDE_PLUGIN_ROOT}` is the absolute path of the plugin and is exported to hook processes.
- Commands: `commands/<name>.md` (frontmatter `description`) becomes `/<plugin>:<name>`, for example
  `/nitelos:init`.
- Marketplace: `.claude-plugin/marketplace.json` with `name`, `owner{name}` and `plugins[{name, source}]`.
  A GitHub source is `{"source":"github","repo":"owner/repo"}`. Install with
  `claude plugin marketplace add <owner>/<repo>`, then `claude plugin install <plugin>@<marketplace>`.

## Windows

- Shell-form hooks run in Git Bash on Windows, or PowerShell if Git Bash is absent. Exec form needs a real
  `.exe`. `.cmd`/`.bat` shims cannot be spawned without a shell.
- It is **not documented** whether a hook's PATH includes Python console-script directories.

## Consequences for NIT-023 (orchestrator rulings under ADR-016)

1. Turn start (ADR-016 finding 2): the primary source is a plugin `UserPromptSubmit` hook. It writes the
   turn-start time, keyed by `session_id` and `prompt_id`, to the same per-session temp state file as the loop
   guard. The documented chain, in order: that record, then the transcript (best effort, undocumented schema),
   then abstain with `STALE_EVIDENCE`.
2. Reported status context: take it from `last_assistant_message`, not from parsing the transcript.
3. Output: JSON with exit 0 always. Failure means `decision: block` plus `reason`. Abstain means `systemMessage`
   (or a block if `on_abstain: "block"`). Internal error means `systemMessage` plus exit 0. Nitelos never uses
   exit code 2.
4. Loop guard: keep the fingerprint guard. The built-in cap of 8 is a backstop, not a substitute.
5. The plugin's hook command must not depend on console scripts being on PATH. The install docs and
   `hooks.json` resolve the interpreter explicitly. Test this on Windows.
