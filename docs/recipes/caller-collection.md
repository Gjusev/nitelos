# Recipe: caller-side collection for Nitelos

Nitelos verifies outcomes from evidence **you** capture. This recipe shows the caller
side: taking a screenshot, normalizing what your agent did into JSON observations, and
handing both to Nitelos. Everything here is illustrative — nothing in this file is
imported by tests, and none of it is a runtime dependency of Nitelos.

Read this first, plainly:

- **Nitelos has no runtime Playwright dependency.** The browser example below uses the
  caller's own stack; any screenshot source works.
- **Nitelos never drives the browser.** It observes snapshots; it never clicks,
  navigates, retries an agent action, or follows instructions found in evidence.
- **Normalization is the caller's responsibility.** Raw HTML, accessibility trees and
  full tool logs are not Nitelos inputs; you reduce them to small JSON observations.
- **The built-in visual adapter takes at most two images per visual criterion.**
- **The model context window is bounded:** the last eight actions (name and reported
  status only) at or before the newest cited screenshot; older ones are recorded as
  omitted, never silently truncated.

## 1. Capture evidence during your agent run

```python
from nitelos import Evidence


def collect_evidence(page, store_items: dict[str, bytes]) -> list:
    """Caller-side collection: you own the browser and the normalization."""
    evidence = []

    # A final screenshot after your agent finishes (or an earlier one for context).
    png = page.screenshot(full_page=True)
    store_items["art-final"] = png
    evidence.append(
        Evidence.screenshot(
            id="shot-final",
            artifact_id="art-final",
            data=png,
            sequence=0,
            captured_at="2024-06-01T10:00:00Z",
            checkpoint_id="cp",
            source_id="my-agent-runner",
            subject={"form": "registration-1"},
            phase="final",
        )
    )

    # A normalized DOM observation: YOU turn the page state into a small JSON object.
    validation_error = page.locator(".form-error").count() > 0
    evidence.append(
        Evidence.observation(
            id="obs-form",
            sequence=1,
            captured_at="2024-06-01T10:00:01Z",
            checkpoint_id="cp",
            source_id="my-agent-runner",
            subject={"form": "registration-1"},
            phase="final",
            channel="dom",
            data={"validation_error": validation_error, "email_filled": True},
        )
    )

    # Agent actions, with an optional later tool-channel result.
    evidence.append(
        Evidence.action(
            id="act-submit",
            sequence=2,
            captured_at="2024-06-01T10:00:02Z",
            checkpoint_id="cp",
            source_id="my-agent-runner",
            subject={"form": "registration-1"},
            phase="final",
            name="submit-form",
            arguments={"button": "#submit"},  # audit-only; never sent to the model
            reported_status="completed",
        )
    )
    return evidence
```

The factories compute the evidence digests (exact PNG bytes; canonical JSON for
observation and action payloads) — you never hash anything by hand.

## 2. Record a trace, or build a request directly

A trace is just the ordered evidence plus bounded metadata; convert it when you know
the request context:

```python
from nitelos import parse_trace

trace = parse_trace(
    {
        "schema_version": "1",
        "evidence": [item.model_dump(mode="json") for item in collect_evidence(page, store)],
        "metadata": {"run_id": "run-42"},
    }
)
request = trace.to_request(
    objective="Complete the registration form",
    criteria=[
        {
            "id": "no-errors",
            "description": "No validation error remains on the form",
            "kind": "assertion",
            "scope": "observed_state",
            "evidence_ids": ["obs-form"],
            "subject": {"form": "registration-1"},
            "pointer": "/validation_error",
            "operator": "equals",
            "expected": False,
        }
    ],
    request_id="req-42",
    checkpoint_id="cp",
    as_of="2024-06-01T10:01:00Z",
)
```

## 3. Verify, with external trust only where YOU established it

```python
from nitelos import ArtifactStore, TrustBinding, VerificationPolicy, Verifier

verifier = Verifier(
    policy=VerificationPolicy(),
    trust_bindings=(
        # Only for facts you read through YOUR OWN authorized integration.
        # A binding is host configuration, never something a trace can carry.
        TrustBinding(
            evidence_id="ledger-1",
            sha256=observed_ledger_digest,
            source_id="my-ledger-reader",
            subject={"form": "registration-1"},
            checkpoint_id="cp",
        ),
    ),
)
result = verifier.verify(request, artifacts=ArtifactStore(store))
print(result.decision)  # success | failure | abstained
```

If the criterion needs a state you did not capture through an authorized reader,
expect `abstained` — an agent's own "it worked" summary or a tool-completion record is
context, never proof of an external outcome.

## Notes

- Initial screenshots are ordinary screenshots with an earlier checkpoint; there is no
  special before/after wrapper.
- Action `arguments` are kept for audit and never transmitted to the shipped visual
  model; the model sees only `name` and `reported_status` for the bounded window.
- Use `Evidence.action(..., tool_result_id="...")` only to link a tool-channel
  observation that appears **later** in the trace with a higher sequence.
