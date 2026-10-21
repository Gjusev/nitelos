# MCP server (extra `mcp`)

[nitelos.integrations.mcp_server](https://github.com/Gjusev/nitelos/blob/main/src/nitelos/integrations/mcp_server.py)
exposes nitelos over the Model Context Protocol on stdio, for hosts that
want an agent to trigger verification without embedding the SDK.

## Install and run

```text
pip install 'nitelos[mcp]'
```

Run (configure via environment; the collector configuration file is
host-authored JSON mapping each enabled kind to its pinned config):

```text
NITELOS_MCP_CRITERIA=.nitelos/criteria.json
NITELOS_MCP_COLLECTORS=junit
NITELOS_MCP_COLLECTOR_CONFIGS=collectors.json
python -m nitelos.integrations.mcp_server
```

Nothing runs unless the host pins it: `NITELOS_MCP_COLLECTORS` defaults to
empty and an enabled kind without a pinned config is a tool error.

## Tools

- `verify_outcome(request)`: a full v0.1 request mapping, verified with the
  strict policy and NO trust bindings. Evidence supplied through this
  server is agent evidence and stays unbound: external-scope criteria
  abstain with `UNTRUSTED_EXTERNAL`. The response carries
  `execution_status`, `decision`, reason codes and per-criterion states;
  ids and codes only, never values.
- `collect(kind)`: runs one enabled collector with the host-pinned config
  and returns its evidence wire form or the collector error code. The call
  accepts only the kind; a `config` argument is rejected.
- `describe_criteria()`: a read-only view of the configured criteria
  (ids, descriptions, kinds, scopes). The file is only ever read.

Injection payloads inside evidence are data: they change nothing. A
smuggled `trust_bindings` key is rejected by the schema with a tool error.
Arguments are capped at 256 KiB serialized; every call is logged with the
tool name, the argument size and the outcome code only. When a collector
returns no evidence, the citing criterion abstains with
`MISSING_EVIDENCE`, never STALE with zero evidence.

## Limitations

- The server adds no trust and cannot: only the host process that ran a
  collector may bind its evidence (ADR-015).
- Exit code discipline is the caller's; the server itself is single
  connection per process, and the active config is a module-level slot set
  by `build_server`.
- Importing the module without the extra raises `ImportError` naming
  `pip install "nitelos[mcp]"`.
