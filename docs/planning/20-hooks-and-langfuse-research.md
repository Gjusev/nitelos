# 20 — Coding-agent hooks and Langfuse v4 research

Status: research only (no code, no PR). Written 2026-11-11 for the v0.2 line; feeds
the integration work described in
[17-v0.2-product-and-plan.md](17-v0.2-product-and-plan.md) and complements
[docs/comparison.md](../comparison.md) ("we ship the OTel export, not a Langfuse
integration") and [docs/implementation/nit-023-claude-code-facts.md](../implementation/nit-023-claude-code-facts.md).

Method and honesty rules:

- Every external claim cites a numbered source `[n]`; all sources are official
  documentation or the official OpenAPI spec, **read on 2026-11-11**. The full
  URL list with the read date is in [Sources](#sources) at the bottom.
- Nothing is claimed from memory: where the docs do not answer a question, it is
  listed as an open question (section 5), not filled in.
- Repo facts (no `[n]`) come from this repository's source and docs at v0.2.0rc1
  (`src/nitelos/schemas.py`, `src/nitelos/integrations/otel.py`, `docs/claude-code.md`,
  `plugin/hooks/`, `docs/comparison.md`).
- Web access and cloning both worked on 2026-11-11; no source failed to load.
  One task premise was corrected by the research: see 2.1.

---

## 1. Coding-agent hooks (official docs only)

### 1.1 Claude Code

Read from the hooks reference [1] (read 2026-11-11). This confirms and extends
the 2026-10-20 facts recorded in nit-023 [repo: docs/implementation/nit-023-claude-code-facts.md].

**Hook events.** Hooks are user-defined command, HTTP, MCP-tool, prompt (LLM), or
agent handlers fired at lifecycle points. Per-session: `SessionStart`,
`SessionEnd`. Per-turn: `UserPromptSubmit`, `Stop`, `StopFailure`. Per tool call:
`PreToolUse`, `PostToolUse` (plus `PostToolUseFailure`, `PostToolBatch`,
`PermissionRequest`, `PermissionDenied`, compaction events, and task/teammate
events) [1].

**stdin JSON shape (command hooks).** Every event receives common fields on
stdin: `session_id`, `prompt_id` (absent until first user input; matches the
OpenTelemetry `prompt.id` attribute), `transcript_path` (written asynchronously,
may lag the conversation — the docs direct hooks that need the final assistant
text to `last_assistant_message` instead), `cwd`, `scratchpad_dir` (absent when
the session has none; requires Claude Code v2.1.257+), `permission_mode`,
`effort.level`, `hook_event_name`, plus `agent_id`/`agent_type` when the hook
fires inside a subagent or teammate [1]. `Stop` additionally carries
`stop_hook_active`, `last_assistant_message`, `background_tasks` (array of
in-flight tasks) and `session_crons` [1]. `SubagentStop` carries
`stop_hook_active`, `agent_id`, `agent_type`, `agent_transcript_path` (nested
`subagents/` folder) and `last_assistant_message` [1].

**Blocking and feeding a reason back.** Two mechanisms; the docs say to use one
per hook [1]:

- exit `0` and print JSON `{"decision": "block", "reason": "..."}` on stdout;
  `reason` is required and is fed to Claude as its next instruction;
- exit code `2`: on `Stop` and `SubagentStop` this also blocks (stderr becomes
  the continuation reason). On other events exit 2 has per-event meanings; on
  `StopFailure` output is ignored entirely [1].

`Stop`/`SubagentStop` also accept `hookSpecificOutput.additionalContext` for
non-error guidance: the conversation continues through the same loop protections
but the transcript labels it "Stop hook feedback" instead of a hook error [1].
New today (not in nit-023): a `StopFailure` event fires instead of `Stop` on API
errors, and its output is ignored [1].

**Loop protections.** `stop_hook_active` is `true` when Claude Code is already
continuing because of a stop hook. Claude Code applies an 8-consecutive-
continuation cap — after eight stop-hook continuations in a row it overrides the
next block and ends the turn; the count resets each time Claude calls a tool;
`CLAUDE_CODE_STOP_HOOK_BLOCK_CAP` raises the cap [1]. This matches nit-023 and
the plugin's own fingerprint loop guard [repo: docs/claude-code.md].

**Timeouts.** Default `timeout` is 600 s for `command`, `http`, and `mcp_tool`
hooks (30 s for `prompt`, 60 s for `agent`; lowered defaults on
`UserPromptSubmit`/model-switch events). A hook canceled at its timeout has its
output discarded, so on `Stop` a timed-out verification degrades to "stop
proceeds" [1] — the nitelos plugin's degrade-to-warning behavior is correct
[repo: docs/claude-code.md].

**Evidence available to a hook.** `transcript_path` (async JSONL; schema not
documented; may lack the current turn at Stop time — the docs recommend
`last_assistant_message` for the final claim), `cwd`, `scratchpad_dir`,
`session_id`/`prompt_id`, `last_assistant_message`, `background_tasks`,
`session_crons`. Tool-level evidence comes from `PreToolUse` (`tool_name`,
`tool_input`, `tool_use_id`, `mcp_server` for MCP tools) and `PostToolUse`
(`tool_input` and `tool_response`, tool-specific schema) [1]. There is **no
turn-start time field** [1][repo: nit-023], so the plugin's
`UserPromptSubmit`-written state file remains the right turn-start source.

### 1.2 Codex CLI

Read from the official Codex hooks documentation [2] (read 2026-11-11).

**Model.** Codex has a hook framework: command or MCP-tool handlers configured
in `hooks.json` or inline `[hooks]` tables next to active config layers
(`~/.codex/`, project `.codex/`), or bundled by plugins (`hooks/hooks.json` in
the plugin root). Non-managed hooks must be **reviewed and trusted** (per-hash)
before they run, via `/hooks`; `--dangerously-bypass-hook-trust` exists for
vetted one-off automation; `[features] hooks = false` turns hooks off [2].
Events: during a turn `PreToolUse`, `PermissionRequest`, `PostToolUse`,
`PreCompact`, `PostCompact`, `UserPromptSubmit`, `SubagentStop`, `Stop`; per
model request `PreModelRequest`/`PostModelRequest`; `Interrupt`;
`SessionStart`/`SubagentStart`; `SessionEnd` [2].

**stdin JSON shape.** Common fields: `session_id`, `transcript_path`
(`string | null` — "the transcript format isn't a stable interface for hooks"),
`cwd`, `hook_event_name`, `model`, and `permission_mode` on turn-scoped events.
`Stop` adds `turn_id`, `stop_hook_active`, `last_assistant_message` [2].
`PreToolUse` adds `turn_id`, `tool_name`, `tool_use_id`, `tool_input` [2].

**Blocking and reason.** Yes, a Stop hook can keep Codex working — with a
different mechanism than Claude Code: `Stop` expects JSON on stdout when it
exits `0` (plain text is invalid). Returning `{"decision": "block", "reason":
"..."}` **does not reject the turn**; it makes Codex continue by automatically
creating a new continuation prompt that acts as a new user prompt, using
`reason` as the prompt text. Exit code `2` with the reason on stderr does the
same. If any matching hook returns `continue: false`, that takes precedence over
continuation decisions (the turn is allowed to end). `matcher` is ignored for
`Stop` [2]. `SubagentStop` works the same; `reason` keeps the subagent running
[2]. `PreToolUse` can deny a supported tool call via
`hookSpecificOutput.permissionDecision: "deny"` + `permissionDecisionReason`
(an older `{decision, reason}` shape is also accepted) [2]. `SessionEnd` and
`Interrupt` cannot prevent anything [2]. Default hook `timeout` is 600 s [2].

**Consequence for nitelos:** the shape is close enough to Claude Code that the
existing Stop-hook pipeline (collectors → verifier → block reason) ports
directly; the differences are the trust-review step, the "continuation prompt"
semantics of a block, and `continue: false` needing an explicit "never
continue" exit path.

### 1.3 OpenCode

Read from the official plugins and plugin-server docs [3][6][7] (read
2026-11-11). Note: OpenCode's docs currently describe a **V2** plugin API
(official documentation for OpenCode V2 [3][6][7]) while V1 remains supported;
the migration page maps old hook names to new APIs [7].

**Mechanism.** A plugin is a JavaScript/TypeScript module. V2: a default export
with `id` and `setup(ctx)` (`Plugin.define`), registered from `.opencode/plugins/`
directories, the `plugins` array in `opencode.json(c)`, or npm packages [3][6].
Hooks are registered per domain inside `setup` and return disposables [6]:
`ctx.session.hook("prompt" | "context" | "compaction" | ...)` (prompt admission
transform, model-request transforms), `ctx.tool.hook("execute.before" |
"execute.after")`, `ctx.shell.hook("create.before")`,
`ctx.permission.hook("evaluate")` [6].

**What can and cannot block.**

- **The agent finishing cannot be blocked.** There is no Stop-equivalent hook.
  When a session goes idle, plugins only receive the `session.idle` **event** on
  the read-only event stream (`ctx.event.subscribe()`, the V2 replacement for
  V1's `event` hook; the migration page's own example just logs "Session
  completed") [7][6]. Events are observational, not decision points.
- **Tool calls can be blocked**: the documented pattern for
  `tool.execute.before` throws an error to stop the call (V1 example:
  `throw new Error("Do not read .env files")`; the V2 example uses the same
  throw pattern) [7]. A permission-hook deny or a rejection with feedback
  "rejects with a `Tool.Error` that carries the reason, so the model sees it and
  continues" [6].
- **Prompt admission cannot reject**: the `prompt` hook transforms an incoming
  prompt (text, files, skills, delivery) but "does not expose a typed rejection
  API" [6].

**Consequence for nitelos:** on OpenCode the verifier can gate individual tool
calls and can *record* verification outcomes at `session.idle` / on tool events,
but it cannot stop the agent from ending a turn while claiming success. The
correct v0.2 scope here is observe-and-report (plus optional tool-call guards),
not stop-blocking.

### 1.4 Comparison table

| Harness | Event when agent claims done | Can block? | How to return a reason | Evidence available |
|---|---|---|---|---|
| Claude Code [1] | `Stop` (main agent), `SubagentStop` (subagents); `StopFailure` on API errors, output ignored | Yes. JSON `decision: "block"` (exit 0) or exit code 2; subject to `stop_hook_active` and the 8-continuation cap (`CLAUDE_CODE_STOP_HOOK_BLOCK_CAP`) | `reason` (required with `decision: "block"`) becomes Claude's next instruction; exit 2 uses stderr; `hookSpecificOutput.additionalContext` for non-error guidance | `session_id`, `prompt_id`, `transcript_path` (async, schema undocumented), `cwd`, `scratchpad_dir`, `permission_mode`, `last_assistant_message`, `stop_hook_active`, `background_tasks`, `session_crons`; per-tool: `tool_name`, `tool_input`, `tool_response`, `tool_use_id` |
| Codex CLI [2] | `Stop` / `SubagentStop` (`matcher` ignored on Stop); `SessionEnd` after the fact | Yes, but "block" = auto-created continuation prompt, not turn rejection; any hook's `continue: false` overrides and allows the stop | `reason` becomes the new continuation-prompt text (JSON stdout, exit 0) or stderr on exit code 2 | `session_id`, `transcript_path` (nullable, format unstable), `cwd`, `hook_event_name`, `model`, `permission_mode`, `turn_id`, `stop_hook_active`, `last_assistant_message`; per-tool: `tool_name`, `tool_use_id`, `tool_input` |
| OpenCode [3][6][7] | No completion hook; `session.idle` event on the read-only stream | **No** at completion. Tool calls can be blocked (`tool.execute.before` throw; permission deny returns `Tool.Error` with reason); prompt admission has no rejection API | No reason-back channel at done. Nearest: permission-deny / tool-guard reason reaches the model as a tool error; at `session.idle` only side channels (logs, score export) | Plugin context: `project`, `directory`, `worktree`; mutable `event.tool` / `event.input` / `event.result` on tool hooks; session data via event stream and `ctx.session` client |

---

## 2. Langfuse v4 (SDKs and public API)

All Langfuse claims below were read 2026-11-11 from the cited official pages.

### 2.1 Version landscape (premise correction)

- Langfuse v4 is GA; "Langfuse Cloud, where v4 has been rolling out in preview
  since March 2026, will switch to v4 as the only experience" — Langfuse Cloud
  v3 is marked "Deprecated as of Nov 16, 2026" [8]. The 2026-11-16 deadline in
  the task matches [8].
- The **current GA Python SDK is v5** (PyPI latest: 5.2.0 on 2026-11-11 [16]);
  Python SDK v5 and JS/TS SDK v6 were released 2026-10-14, built for Langfuse
  v4 [8][9]. Python SDK v5 requires Langfuse Cloud or self-hosted ≥ v4.59.0 and
  Python ≥ 3.11; on Python 3.10, `pip install langfuse` resolves to the latest
  v4 (PyPI latest 4.x: 4.18.0 [16]) [9].
- **The task's "Python SDK v4.x" premise is therefore out of date for new
  work**: v4.x is still the choice only for Python < 3.11 or self-hosted v3
  servers [8][9]. Everything below notes v4-vs-v5 differences where the docs
  state them.

### 2.2 Categorical scores on a trace and on an observation

Score data types are `NUMERIC`, `CATEGORICAL`, `BOOLEAN`, `TEXT`; categorical
values are passed as strings and are intended for "discrete classifications
where the set of possible values is known upfront" [4][5].

**Python SDK (v5 syntax; the low-level methods are unchanged from v4 — see
2.2.3)** [4]:

```python
from langfuse import get_client

langfuse = get_client()

# Trace-level categorical score
langfuse.create_score(
    name="outcome",
    value="success",  # string for categorical
    trace_id="trace_id_here",
    data_type="CATEGORICAL",
    comment="...",  # optional
    score_id="...",  # optional idempotency key
    config_id="...",  # optional ScoreConfig enforcement
)

# Observation-level: provide BOTH trace_id and observation_id
langfuse.create_score(
    name="outcome",
    value="abstained",
    trace_id="trace_id_here",
    observation_id="observation_id_here",
    data_type="CATEGORICAL",
)
```

Context helpers also exist: `span.score(...)` (score the current observation)
and `span.score_trace(...)` / `langfuse.score_current_trace(...)` (score the
trace) [4]. Scores can also target sessions (`session_id`) and dataset runs
[4][5]. A score ingested with a `trace_id` before the trace exists is linked
once the trace with that id is created — no ordering constraint for backfill
[4].

**Public API.** `POST /api/public/scores` accepts a **list** of
`CreateScoreRequest` objects, returns 202 when all scores are accepted or 207
with accepted/rejected counts and error messages ("Do not automatically retry a
207 batch") [11]. Relevant `CreateScoreRequest` fields in the spec [11]:
`id` (nullable — usable as idempotency key), `traceId`, `observationId`,
`sessionId`, `datasetRunId`, `name`, `value` (number or string — "must be
passed as string for categorical and text scores"), `comment` (string,
nullable), **`metadata`** (object with `additionalProperties: true`,
nullable), `environment`, `queueId`, `dataType` (inferred when `configId` is
passed; otherwise must be passed or defaults to numeric), `configId`, `source`
(ANNOTATION requires a configId unless dataType is CORRECTION; EVAL "is
reserved for internal evaluator outputs and is not accepted on this endpoint").
`DELETE /api/public/scores/{scoreId}` exists [11].

**2.2.1 Score configs enforcing categories.** A `ScoreConfig` has name, dataType
(`NUMERIC`/`CATEGORICAL`/`BOOLEAN`/`TEXT`), and for categorical a `categories`
list of `{label, value}` objects (`value` numeric) [5][11]. Validation rules
when a score carries a `configId`: score name must equal the config name,
dataType must match, and a categorical value "must map to one of the categories
defined in the config" [4]. Configs are created in the UI (Project Settings →
Scores/Evaluation) or via the API; the SDK uses `langfuse.api...` for the
endpoints [10]. The OpenAPI spec has `POST /api/public/score-configs` (name:
max 80 characters, restricted character set; `dataType` and `categories` etc.),
`GET /api/public/score-configs`, and `PATCH /api/public/score-configs/{configId}`
(`UpdateScoreConfigRequest`: name, categories, min/max, description,
isArchived) [11]. **Conflict to resolve before implementing:** the data-model
page says "Configs are immutable but can be archived (and restored anytime)"
[5], while the FAQ describes updating configs ("Score configs may be updated at
any time") and the spec ships a PATCH endpoint [10][11] — see open question Q3.

**2.2.2 Score-config creation endpoint for nitelos.** `POST
/api/public/score-configs` with `{name, dataType: "CATEGORICAL", categories:
[{label: "success", value: 1}, {label: "failure", value: 0}, {label:
"abstained", value: -1}]}` matches the documented schema [11]; the numeric
`value` per category is a required property of `ConfigCategory` [11].

**2.2.3 v4 → v5 differences that touch scoring.** `create_score()`,
`span.score()`, and `span.score_trace()` are unchanged in v5 [9]. v5 sends
scores in batches to `POST /api/public/scores` instead of the legacy ingestion
endpoint; on HTTP 207 the SDK logs accepted/rejected counts and does not retry
rejected scores; network errors, 429 and 5xx are retried with backoff [9].
Breaking in v5: `api.scores.create(name=..., value=..., ...)` becomes
`api.scores.create(request=[CreateScoreRequest(...)])`, and score reads moved
to `api.scores.get_many` [9].

### 2.3 Where evidence references go: comment vs metadata, size limits

- The score object has a dedicated `comment` field ("Evaluation comment,
  commonly used for user feedback, eval reasoning output or internal notes")
  [5]. **No maximum length for `comment` is documented** — neither the data
  model [5] nor the OpenAPI spec [11] declares a `maxLength` for it. The only
  platform-wide limit found is Langfuse Cloud's "5 MB per request and 5 MB per
  response" [15]. → open question Q1.
- The score object also has a `metadata` object at the API level [11], but the
  documented `create_score()` signature shows no `metadata` parameter [4] →
  open question Q2.
- Trace/observation **metadata** values are strictly capped: in Python SDK v5
  and JS/TS SDK v6 each value must be ≤ 200 characters *as JSON* (so a string
  can have at most 198 characters); longer values are dropped with a warning.
  In Python SDK v4 and JS/TS SDK v5, use string values ≤ 200 characters [14].
- Nitelos evidence references (criterion ids, evidence ids, sha256 digests,
  reason codes) are short, structured strings — they fit the metadata caps
  comfortably, but nitelos must serialize them itself (it currently exposes
  them as `CriterionResult.evidence_refs` and allowlisted OTel attributes
  [repo: src/nitelos/schemas.py, src/nitelos/integrations/otel.py]).

### 2.4 Fetching traces/observations for backfill (Observations API v2)

- Endpoint: `GET /api/public/v2/observations` [11][12]. Available on Langfuse
  Cloud (all plans) and self-hosted **Langfuse v4+**; on self-hosted v3 use the
  v1 endpoint `GET /api/public/observations` [12]. v1
  `/api/public/observations` and `/api/public/observations/{id}` are listed as
  deprecated with Observations API v2 as the replacement [8].
- Cursor-based pagination with a `cursor` request/response token; `limit`
  defaults to 50 with a documented maximum (1,000) [11][12]; a page can be
  short or empty while `meta.cursor` is present, so only a missing cursor ends
  iteration [11].
- Selective field groups via `fields` (comma-separated): `core`, `basic`,
  `time`, `io`, `metadata`, `model`, `usage`, `prompt`, `metrics`,
  `trace_context`; default `core,basic`; `trace_context` denormalizes the
  parent trace's `tags`, `release`, `traceName` onto each row [11][12].
- The v2 endpoint returns **observation rows, not trace objects**: group rows by
  `traceId` to reconstruct a trace; trace-level fields (name, user, session,
  tags, input/output) sit on the root observation [12]. There is no get-by-id
  route; for a single observation pass a URL-encoded `filter` on the `id`
  column [12]. `parseIoAsJson` defaults to false [11][12].
- **Freshness caveat:** data from older SDKs (`langfuse-python` < 4.7.0,
  `langfuse-js` < 5.4.0) or direct OTel exporters that do not send
  `x-langfuse-ingestion-version: 4` can be delayed by up to 15 minutes on v2
  endpoints [12]. This matters for nitelos backfill: nitelos's OTel export is
  host-driven (the host owns the exporter [repo: docs/opentelemetry.md]), so
  whether the host's exporter sends that header decides backfill latency.
- Python SDK v5 read path: `api.observations.get_many(trace_id=...)` /
  `iter_observation_pages` replace `api.trace.get`/`api.trace.list` and the
  legacy observations endpoints [9]; `run_batched_evaluation()` in v5 "reads
  observations only" [9].

### 2.5 Langfuse experiment GitHub Action: can it gate on a categorical score rate?

The official action is `langfuse/experiment-action` [13][17]. Mechanics per
the CI/CD docs [13] (read 2026-11-11):

- The workflow runs the action with `experiment_path` (a script file, directory,
  or glob; Python/TS/JS), optional `dataset_name` + `dataset_version`, and
  Langfuse credentials. The action installs the **latest** SDK by default
  (`python_sdk_version` input overrides); it "requires Langfuse Python SDK
  v4.6.0+ or JS SDK v5.3.0+" [13].
- Each script must define `experiment(context)`; the action builds a
  `RunnerContext` (client init, dataset loading, GitHub metadata such as commit
  SHA/branch/job URL) and the script calls `context.run_experiment(...)` with
  per-item `evaluators` and run-level `run_evaluators` [13].
- **The gate is `RegressionError` raised by your own script.** The documented
  pattern reads `result.run_evaluations`, finds a run-level evaluation by name,
  compares its numeric `value` to a threshold, and raises `RegressionError(...)`
  (with `result`, `metric`, `value`, `threshold`). The action then fails the CI
  job when `should_fail_on_regression` (default `true`) is set, or on any script
  crash (`should_fail_on_script_error`, default `true`); it posts a PR comment
  and exposes `failed` / `result_json` outputs [13][17].
- **Answer: there is no built-in categorical-score-rate gate.** The action has
  no input for "minimum categorical rate" [13]; the threshold comparison is user
  code over `Evaluation.value` [13]. Gating on a categorical rate **is
  achievable**: your run evaluator counts the categorical outcomes of the item
  evaluators (e.g. `success` / total decided) into a numeric rate `Evaluation`
  and the script raises `RegressionError` below the threshold — exactly the
  documented structure, with the rate computed from categorical item results
  [13]. What the docs do not show is whether an item `Evaluation` may itself
  carry a categorical string value (all examples are numeric) — open question
  Q4, but it does not block: nitelos can emit numeric 1/0 evaluations plus a
  categorical comment, and compute the rate in the run evaluator.

---

## 3. Mapping: what nitelos already exposes vs what is missing

What nitelos exposes today (repo sources, v0.2.0rc1): `Decision` =
`success`/`failure`/`abstained` and `VerificationResult` with `execution_status`,
`decision`, per-`CriterionResult` `{state: supported/refuted/unknown, basis,
scope, evidence_refs, reason_codes, limitations, evaluations}` and diagnostics
(`src/nitelos/schemas.py`); evidence with sha256 digests, provenance and limits
(`src/nitelos/evidence.py`, docs/evidence-limits.md); collectors (git, junit,
github, http, Playwright capture) with caps/redaction (`src/nitelos/collect/`);
OTel export — one `nitelos.verify` span per verification with an allowlist
including `nitelos.decision`, `nitelos.reason_codes`,
`nitelos.evidence.cited_count` and `gen_ai.evaluation.score.label` = the
decision (`src/nitelos/integrations/otel.py`); and a Claude Code plugin whose
Stop hook already blocks with a reason, has a loop guard, a state file, and
abstention semantics (`plugin/hooks/`, `docs/claude-code.md`).

| Target capability (sections 1–2) | nitelos has | Missing |
|---|---|---|
| Stop-hook blocking with reason (Claude Code) | Full pipeline: collectors → `Verifier` → block reason listing failed criteria + observed values + evidence refs; loop guard; abstain-as-warn (`docs/claude-code.md`) | `SubagentStop` wiring (explicitly deferred); nothing blocking — port as-is |
| Stop-hook blocking (Codex) | The verify pipeline and reason rendering are harness-independent | A Codex adapter: `hooks.json` shape, trust-review guidance, continuation-prompt semantics of `decision: "block"`, explicit `continue: false` exit path |
| Completion gating (OpenCode) | Verifier + collectors | Decision: no stop-blocking exists in OpenCode [6][7] — scope an observe-only plugin (`session.idle`) and/or tool guards; nothing exists yet |
| Categorical verdict score on trace/observation | `Decision` maps 1:1 to categories `success`/`failure`/`abstained`; `Score`/`ScoreKind` types exist for backend findings (numeric only today) | A Langfuse integration module: `create_score` call with `data_type="CATEGORICAL"`, `config_id`, idempotent `score_id`; nothing Langfuse-specific exists (`docs/comparison.md`: OTel only) |
| Score config enforcement | The `Decision` enum is the single source of the category set | Config bootstrap (idempotent create/archive-tolerant `POST /api/public/score-configs` [11]) and a documented config id |
| Evidence references → comment/metadata | Structured `CriterionResult.evidence_refs`, sha256 digests, provenance records | A bounded serializer (short string form; respects the 200-char metadata value cap [14]); decision comment-vs-metadata (Q1/Q2) |
| OTel path to Langfuse | `verify_traced` / `span_attributes` with semantic-convention labels | Guidance on `x-langfuse-ingestion-version: 4` (host-side exporter) to avoid the 15-min v2 delay [12]; decision whether scores go via OTel attributes (not scores) or via `POST /api/public/scores` (recommended) |
| Backfill from Langfuse | `nitelos.verify` span name and `nitelos.verification_id` attribute identify results; `nitelos.evidence.cited_count` is exported | A backfill job using Observations API v2 (`filter` on name, `fields` groups, cursor loop) and score upsert keyed by `verification_id`; nothing exists |
| CI gate on verdict rate | Per-item `Decision` incl. `abstained` semantics | An experiment script (dataset item → run nitelos → numeric `Evaluation` per item, rate run-evaluator, `RegressionError` on threshold) and an explicit abstention policy for the gate |

---

## 4. Recommended design (one page)

**Scope:** a Langfuse reporting adapter, two new thin hook adapters (Codex,
OpenCode), a backfill job, and a CI gate recipe — all reusing the existing
`Verifier` pipeline and the Claude Code plugin's structure.

1. **`nitelos.integrations.langfuse`** (new optional extra `langfuse`, adds no
   hard dependency — accept a client or use `get_client()`):
   - `report_score(client, result, *, trace_id, observation_id=None, name="nitelos_outcome", config_id=None)`:
     maps `result.decision` to the categorical string, calls
     `client.create_score(..., data_type="CATEGORICAL", score_id=result.verification_id ...)`.
     `score_id` = verification id gives free idempotency (score `id` is an
     idempotency key [5][11]).
   - `ensure_score_config(client, name="nitelos_outcome")`: create the config
     with categories `success`/`failure`/`abstained` if absent (POST
     `/api/public/score-configs` [11]); tolerate 409/exists and the
     archived-config state; never PATCH silently (Q3).
   - `evidence_comment(result)`: deterministic short string — failed/unknown
     criterion ids, first N evidence ids, sha256 digests (truncated), reason
     codes — capped well under the metadata value cap (200 chars [14]) since
     the comment limit is undocumented (Q1). If Q2 resolves in favor of
     `metadata`, put the structured dict there and keep the comment human-text.
2. **Codex adapter:** same collectors + verifier; `Stop` handler emits
   `{"decision": "block", "reason": ...}` (exit 0) and treats a hook returning
   `continue: false` (any hook) as "allow the stop"; document the `/hooks`
   trust step in the install guide. Keep the loop guard keyed on
   `stop_hook_active` plus the existing fingerprint.
3. **OpenCode adapter (observe-only, explicit non-goal: blocking):** plugin
   listens on the event stream for `session.idle`, runs the verifier over
   collector results, reports via `report_score` and a `systemMessage`-
   equivalent log line; optional `tool.execute.before` guard mode (throw with
   criterion reason) behind config.
4. **Backfill job:** `GET /api/public/v2/observations` (or SDK
   `iter_observation_pages`) filtered on `name = nitelos.verify`, `fields =
   core,basic,metadata,trace_context`, cursor loop [11][12]; group by
   `traceId`; for each root+span pair write the trace-level score (and optional
   observation-level score) via `report_score`; resumable via cursor. Document
   the exporter header requirement (`x-langfuse-ingestion-version: 4`) to keep
   delay out of backfill [12].
5. **CI gate recipe:** dataset items = recorded tasks; the experiment task runs
   the agent + nitelos verification per item; per-item evaluator emits numeric
   1 (`success`) / 0 (`failure`) with the categorical verdict in `comment`;
   run evaluator computes `success_rate = successes / decided` with a
   configurable abstention policy (`abstained` excludes from the denominator by
   default, so MISSING_EVIDENCE cannot pass silently); script raises
   `RegressionError` below threshold — the action then fails the job [13].

Priority: (1) + (4) first (they are pure SDK work and make nitelos verdicts
queryable in Langfuse), then (2), then (5), with (3) last and smallest.

---

## 5. Open questions

- **Q1 — score `comment` size limit:** none documented (no `maxLength` in the
  OpenAPI spec [11]; only the platform 5 MB request/response limit [15]).
  Determine empirically before relying on long comments.
- **Q2 — does `create_score()` expose `metadata`?** The API schema has score
  `metadata` [11], the documented SDK signature does not show it [4]. If not,
  evidence refs must live in `comment` (or use `api.scores.create`).
- **Q3 — score-config mutability:** data-model says configs are immutable but
  archivable [5]; the FAQ documents updating configs [10] and the spec ships
  `PATCH /api/public/score-configs/{configId}` [11]. Resolve which behavior is
  current before writing `ensure_score_config`.
- **Q4 — categorical values in experiment item evaluators:** the CI/CD docs
  show only numeric `Evaluation.value` [13]; whether an item evaluation may
  carry a categorical string is undocumented. Does not block the gate design
  (numeric 1/0 + rate computation works regardless).
- **Q5 — experiment-action and Python SDK v5:** the action "requires Langfuse
  Python SDK v4.6.0+" and installs the latest SDK by default [13]; whether the
  tested path accepts v5.x (current GA [8][16]) is not stated. Pin
  `python_sdk_version` in the recipe until confirmed.
- **Q6 — OpenCode plugin API generation:** docs are V2 [3][6][7] with V1
  supported [7]; which API a nitelos plugin should target depends on the
  released versions users run. Also re-check whether any released OpenCode
  version adds a completion-blocking hook (none documented today [6][7]).
- **Q7 — Codex hook trust distribution:** non-managed hooks (including
  plugin-bundled ones) require per-hash user trust [2]; the install guide must
  cover the `/hooks` review step, and we should confirm the 600 s default
  timeout applies to `Stop` on the then-current Codex release [2].
- **Q8 — nitelos OTel export ingestion version:** whether hosts' exporters send
  `x-langfuse-ingestion-version: 4` decides whether backfill sees fresh data
  immediately or after up to 15 minutes [12]. nitelos never installs exporters
  itself [repo: docs/opentelemetry.md], so this is a documentation item, not a
  code item.
- **Q9 — Langfuse v4.x server floor for the integration:** Python SDK v5 needs
  server ≥ 4.59.0 [9]; if nitelos supports SDK v4.x too, document both paths
  and their server floors (v4 path: latest 4.18.0 [16]).

---

## Sources

All sources read 2026-11-11 (Europe/Berlin). Official documentation only —
no blog posts, mirrors, or third-party summaries were used for claims.
[1] https://code.claude.com/docs/en/hooks — Claude Code hooks reference
[2] https://developers.openai.com/codex/hooks — Codex hooks
[3] https://opencode.ai/docs/plugins — OpenCode plugins
[4] https://langfuse.com/docs/evaluation/evaluation-methods/scores-via-sdk — Langfuse scores via API/SDK
[5] https://langfuse.com/docs/evaluation/scores/data-model — Langfuse scores data model
[6] https://opencode.ai/docs/build/plugins/server — OpenCode V2 server plugin hooks
[7] https://opencode.ai/docs/build/plugins/migrate-v1 — OpenCode plugin V1→V2 migration
[8] https://langfuse.com/docs/compatibility — Langfuse versions & compatibility
[9] https://langfuse.com/docs/observability/sdk/upgrade-path/python-v4-to-v5 — Langfuse Python SDK v4→v5 migration
[10] https://langfuse.com/faq/all/manage-score-configs — Langfuse FAQ: manage score configs
[11] https://cloud.langfuse.com/generated/api/openapi.yml — Langfuse Public API OpenAPI spec (cloud.langfuse.com)
[12] https://langfuse.com/docs/api-and-data-platform/features/public-api — Langfuse Public API features (Observations API v2)
[13] https://langfuse.com/docs/evaluation/experiments/experiments-ci-cd — Langfuse experiments in CI/CD
[14] https://langfuse.com/docs/observability/features/metadata — Langfuse metadata docs
[15] https://langfuse.com/faq/all/api-limits — Langfuse FAQ: API limits
[16] https://pypi.org/pypi/langfuse/json — PyPI langfuse releases
[17] https://langfuse.com/changelog/2026-05-25-experiment-ci-cd-gates — Langfuse changelog: experiment CI/CD gates
