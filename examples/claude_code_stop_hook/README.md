# Claude Code Stop-hook demo: "tests pass" while they fail

A tiny demo repo showing the nitelos Claude Code Stop hook catching the classic
failure mode: the agent *claims* the tests pass while the test report says
otherwise.

## Layout

```
claude_code_stop_hook/
├── README.md                <- this file
├── .nitelos/criteria.json   <- the verification contract the hook enforces
├── src_app.py               # the "app under test": a broken email validator
├── test_email.py            # a pytest file with one passing and one FAILING test
├── reports/junit.xml        # what the junit collector reads (currently: 1 failure)
└── run_demo.sh              # replays a fake Stop event through the real hook code
```

## What the hook enforces

`.nitelos/criteria.json` wires the junit collector to `reports/*.xml` and
asserts, from **collected evidence only**, that `/failed == 0`. The agent's own
claim — even a verbatim "All tests pass." in `last_assistant_message` — is
hashed into the request metadata and never trusted.

```json
{
  "version": "1",
  "profile": "demo",
  "checkpoint_id": "stop",
  "collectors": {
    "junit": {
      "evidence_id": "tests-1",
      "subject": {"suite": "demo"},
      "report_root": ".",
      "report_glob": "reports/*.xml"
    }
  },
  "criteria": [
    {
      "id": "tests-green",
      "description": "All tests pass",
      "kind": "assertion",
      "scope": "external",
      "evidence_ids": ["tests-1"],
      "subject": {"suite": "demo"},
      "pointer": "/failed",
      "operator": "equals",
      "expected": 0
    }
  ],
  "on_abstain": "warn"
}
```

Note the freshness rule: evidence must be captured during the current turn, so
the report file must be newer than the turn start — `run_demo.sh` touches it to
simulate the agent having just run the tests.

## Run it (offline, no Claude Code needed)

`run_demo.sh` feeds the golden Stop-event stdin (agent says "All tests pass.")
through the actual hook runtime and prints the output document Claude Code
receives:

```bash
bash run_demo.sh
# -> {"decision": "block", "reason": "nitelos: verification FAILED — criterion
#     tests-green (All tests pass): observed 1 via tests-1. failing: test_email_required"}
```

Claude Code feeds `reason` back to the agent as its next instruction: the claim
"tests pass" is refuted by the junit report, and the agent must fix
`src_app.py` (or the test) before the stop goes through.

Fix the app (`reports/junit.xml` shows which test fails), regenerate the report
(`pytest --junitxml=reports/junit.xml`), and the same event returns exit 0 with
no output — the stop proceeds.

With Claude Code, install the plugin per [docs/claude-code.md](../../docs/claude-code.md)
(or `nitelos hooks install --harness claude-code --target .claude/settings.json`);
the hook reads this directory's `.nitelos/criteria.json` from the event's `cwd`.
