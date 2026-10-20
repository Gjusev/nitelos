# Claude Code plugin (extra `claude-code`)

The nitelos plugin verifies, when the agent stops, that the outcome its last
message claims is supported by evidence the plugin collects itself: JUnit XML
test reports and git repository state today. The agent's message is context
only; criteria live in `.nitelos/criteria.json`, are versioned with the code
and are never derived from the claim.

## Install (5 steps)

1. `pip install "nitelos[claude-code]"` in the Python environment Claude Code
   should use for hooks (or your project virtualenv).
2. Add the plugin from this repository:
   `claude plugin marketplace add Gjusev/nitelos`, then
   `claude plugin install nitelos@Gjusev`.
3. If the hook interpreter is not on PATH, set `NITELOS_PYTHON` in your
   environment to the absolute python executable.
4. In your project root run `/nitelos:init` and pick a profile (`python`,
   `node` or `custom`); commit `.nitelos/criteria.json`.
5. Run `/nitelos:check` once to confirm the pipeline; you are done.

## What happens on Stop

The Stop hook reads the event JSON (`session_id`, `prompt_id`,
`transcript_path`, `cwd`, `stop_hook_active`, `last_assistant_message`; parsed
defensively, unknown fields ignored). It resolves the turn start from the
plugin's own UserPromptSubmit record (a small per-session file under the OS
temp directory; the repo is never touched), falls back to the transcript best
effort, and abstains with STALE_EVIDENCE if neither exists. It then runs the
configured collectors (reports older than the turn start are excluded), binds
the evidence, and calls the verifier.

- failure blocks: the reason lists each failed criterion with its observed
  value, the evidence reference and, for test reports, the failing test ids;
- success passes silently;
- abstention warns (or blocks when `on_abstain` is `"block"`).

Loop guard: while `stop_hook_active` is set, the same failed verification is
blocked only once per session; a repeat becomes a warning and the stop passes.

## Empty collector results

A collector that returns nothing (no report files matched, or every file was
older than the turn start) yields no evidence: the citing criterion is
rewritten to cite nothing and the verifier abstains with **MISSING_EVIDENCE**
— never STALE with zero evidence. Collector-layer error codes
(COLLECTOR_UNAVAILABLE and friends) are shown next to the outcome in the
message.

## Budget (measured)

Offline collectors on the maintainer's machine (AMD Ryzen 5 7600X, Windows 11,
Python 3.12, median of 5): junit 0.8 ms per small report set; git 83.6 ms on a
fresh repository (three fixed git invocations). Both are far below the default
`max_seconds: 2.0`; an overrun degrades to a warning and the stop passes.

## Limitations

- SubagentStop is not wired in this version (blocking a subagent would change
  its next instruction; revisit deliberately).
- The transcript fallback depends on an undocumented schema; the state-file
  record is the primary turn-start source.
- The hook never uses exit code 2; internal errors warn and pass.
