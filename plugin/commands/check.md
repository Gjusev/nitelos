---
description: Run the nitelos verification on demand (never blocks)
---

Run an on-demand nitelos verification for this repository and show the result.
It reads `.nitelos/criteria.json` from the current working directory, runs the
configured collectors and prints one outcome line per criterion. It NEVER
blocks the session.

Run:

```bash
NITELOS_HOOK_ROLE=check NITELOS_HOOK_STATE_DIR="$(mktemp -d)" \
  "${NITELOS_PYTHON:-python3}" -m nitelos.claude_code
```

Show the output to the user and, when the outcome is undecided, explain which
evidence was missing (a collector with no result means the citing criterion
abstains with MISSING_EVIDENCE). Do not modify criteria from this command.
