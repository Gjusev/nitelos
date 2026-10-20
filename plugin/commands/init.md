---
description: Create or update .nitelos/criteria.json for this repository
---

Create the file `.nitelos/criteria.json` in the current working directory so the
nitelos Stop hook can verify outcomes in this repository. Ask the user which
profile fits, then write the matching template and adjust paths with the user.

Profile `python` (tests from `reports/junit.xml`, clean tree optional):

```json
{
  "version": "1",
  "profile": "python",
  "checkpoint_id": "stop",
  "collectors": {
    "junit": {
      "evidence_id": "tests-1",
      "subject": {"suite": "regression"},
      "report_root": ".",
      "report_glob": "reports/junit.xml"
    }
  },
  "criteria": [
    {
      "id": "tests-green",
      "description": "All automated tests pass",
      "kind": "assertion",
      "scope": "external",
      "evidence_ids": ["tests-1"],
      "subject": {"suite": "regression"},
      "pointer": "/failed",
      "operator": "equals",
      "expected": 0
    }
  ],
  "on_abstain": "warn",
  "max_seconds": 2.0
}
```

Profile `node` is the same with `"report_glob": "junit.xml"`. Profile `custom`
starts from an empty `collectors` object and criteria the user writes by hand.

Rules: criteria describe the required final state and are versioned with the
code; they are NEVER derived from what the agent claims. The collector
`subject` must equal the citing criterion subject. Keep the file in version
control. After writing it, run `/nitelos:check` once to confirm the pipeline.
