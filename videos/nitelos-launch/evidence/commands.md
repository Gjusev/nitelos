# Evidence capture: the three examples (Phase A)

Captured 2026-10-20 from the main checkout at commit `64299ce` (nitelos 0.1.0,
CPython 3.12.2, Windows 11, project venv via `uv run`). Output below is literal;
any stylized terminal in the films derives from these files and is labeled
"Real output, edited visualization".

| Command | Exit | stdout file | Decision |
|---|---|---|---|
| `uv run python examples/demo_incomplete_form.py` | 0 | `demo_incomplete_form.stdout.txt` | `failure` (CRITERION_REFUTED) |
| `uv run python examples/quickstart.py` | 0 | `quickstart.stdout.txt` | `success` (ALL_CRITERIA_SUPPORTED) |
| `uv run python examples/demo_external_pending.py` | 0 | `demo_external_pending.stdout.txt` | `abstained` (INSUFFICIENT_EVIDENCE, MISSING_EVIDENCE) |

| `examples/quickstart.py` with `"validation_error": True` (one value changed via `sed` into a temp copy) | 0 | `quickstart_flipped.stdout.txt` | `failure` (CRITERION_REFUTED) |

stderr files are empty for all three runs. All three examples are synthetic
fixtures; their timestamps are fixture data, not real events.
