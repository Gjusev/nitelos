# NIT-016 — proposed repository settings (maintainer to apply)

Prepared only; nothing here has been applied. GitHub repo settings are maintainer-owned.

## Proposed description (226 chars)

```
Verify the outcome, not the attempt. A Python SDK that checks an AI agent's claimed result against the evidence its run left behind: deterministic assertions, host-bound trust, optional experimental local visual checks.
```

## Proposed topics (13)

| Topic | Justified by |
|---|---|
| `ai-agents` | The library verifies AI agent task outcomes. |
| `agent-evaluation` | Evaluation methodology, runner and synthetic benchmark are in the repo. |
| `agent-verification` | The core product: outcome verification for agent runs. |
| `llm-agents` | Criteria and traces are designed for LLM-agent harnesses. |
| `evaluation` | `nitelos[eval]` ships metrics, a runner and a report validator. |
| `benchmark` | 120-case sealed synthetic benchmark under `benchmarks/synthetic_v1`. |
| `python-sdk` | The product is a Python SDK, src layout, py.typed. |
| `python` | Python 3.12/3.13 package. |
| `pydantic` | Public schema-1 contract is built on Pydantic v2. |
| `deterministic` | The default path is pure, offline, same-input-same-answer. |
| `evidence` | Evidence digests, eligibility and references are core concepts. |
| `computer-use-agents` | DOM/screenshot evidence views target browser-operating agents. |
| `testing` | The SDK is used as an outcome check in agent test/CI loops. |

## Notes

- No superlatives, no "first", no unqualified claims in the description.
- Topics follow GitHub rules: lowercase, hyphenated, no spaces.
