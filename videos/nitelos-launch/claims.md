# Claims map

Every factual statement in the films and the README visuals, with its source.
Editorial lines (questions, instructions to the viewer) are marked as such.

| Claim on screen | Type | Source |
|---|---|---|
| `registration succeeded` (agent summary) | fixture text | `examples/demo_incomplete_form.py`, `metadata.agent_summary` |
| `context only, never proof` | fixture text | same file, inline comment on `agent_summary` |
| `validation_error true`, `email_filled false` | fixture data | same file, observation `obs-form.data` |
| "No validation error remains on the form", `/validation_error equals false` | fixture data | same file, criterion `no-errors` |
| `decision: failure`, `criterion no-errors: refuted (basis: deterministic)`, `evidence obs-form at /validation_error (assertion_checked)`, `execution_status: ok` | executed output | `evidence/demo_incomplete_form.stdout.txt` (exit 0) |
| "The check ran fine. The outcome failed." | paraphrase of output | `execution_status: ok` + `decision: failure` in the same stdout |
| `upload-file`, `reported_status completed`, "The exported report is stored in the external system" | fixture data | `examples/demo_external_pending.py` |
| `decision: abstained`, `INSUFFICIENT_EVIDENCE`, `MISSING_EVIDENCE` | executed output | `evidence/demo_external_pending.stdout.txt` (exit 0) |
| `evidence_ids:` (empty) on the `stored` criterion | fixture data | `examples/demo_external_pending.py` (`evidence_ids: []`) |
| `decision: success`, `criterion no-errors: supported` (demo film, success card) | executed output | `evidence/quickstart.stdout.txt` (exit 0) |
| Workflow film: "No validation error remains on the form", `validation_error true`, `failure`, "refuted by evidence obs-form at /validation_error" | fixture data + executed output | `examples/demo_incomplete_form.py`; `evidence/demo_incomplete_form.stdout.txt` (`evidence obs-form at /validation_error (assertion_checked)`) |
| Workflow film: "Your agent says the task is done.", "Write down what done means.", "Hand over the evidence it left behind.", "nitelos compares the two.", "The answer, with the evidence that decided it." | editorial (steps of the API flow) | README "How it works" |
| Loop: `validation_error true` → `refuted` / `failure`, `false` → `supported` / `success`, `email_filled true` | executed output | `false`: `evidence/quickstart.stdout.txt`; `true`: the same script with that one value flipped, `evidence/quickstart_flipped.stdout.txt` (exit 0) |
| State cards: `reason_codes` lines and the example file named under each | executed output | the three `evidence/*.stdout.txt` files above |
| Social card: "A Python SDK that checks what an AI agent claims against the evidence it left." | product description | README opening paragraph |
| success = every criterion supported; failure = a criterion refuted; abstained = not enough evidence to decide | SDK semantics | strict conjunction in `src/nitelos/policy.py`; `docs/success-criteria.md`, `docs/errors-and-abstention.md` |
| "Judged only on the evidence you supply." | product boundary | README ("It never acts on the agent's behalf: no clicks, no network fetches, no retries") |
| `pip install nitelos` | distribution | PyPI `nitelos 0.1.0`, published 2026-10-16 via trusted publishing |
| "Verify the outcome, not the attempt." | brand tagline | README, `pyproject.toml` description |
| "Does the evidence agree?", "Write down what done means.", "Check it against the evidence." | editorial | n/a |

Not claimed anywhere: accuracy, speed, latency, customers, integrations,
benchmark results. The examples are synthetic fixtures; their timestamps are
fixture data, and the films carry the label `synthetic example · real output`.
