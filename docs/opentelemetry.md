# OpenTelemetry export (extra `otel`)

Nitelos can export one span per verification. Export only observes: it never
changes a decision, never installs a tracer provider or exporter, never
changes global OpenTelemetry state and never adds logging handlers. The host
owns the provider, processors and exporters.

## Install

```bash
pip install "nitelos[otel]"
```

The extra adds the `opentelemetry-api` package only. To actually emit spans
somewhere you also need the OpenTelemetry SDK (a separate install, already in
the development environment for tests):

```bash
pip install opentelemetry-sdk
```

## Use

```python
from nitelos import Verifier
from nitelos.integrations.otel import verify_traced

result = verify_traced(Verifier(), request, tracer=my_tracer)
```

`verify_traced` opens exactly one span named `nitelos.verify`, calls
`verifier.verify`, sets the allowlisted attributes and returns the result
unchanged. With `tracer=None` a tracer comes from the current global
provider. Hosts that run their own spans call the pure function
`span_attributes(result)` instead.

Collector ids and per-collector durations can be attached (validated before
the span starts: ids match the nitelos ID pattern, at most 64, durations
finite and non-negative, covering exactly the given ids).

## What is exported — the full allowlist

- `nitelos.execution_status`, `nitelos.decision` (omitted when null),
  `nitelos.verification_id`
- `nitelos.criteria.count` and counts per criterion state
  (`supported`, `refuted`, `unknown`)
- `nitelos.reason_codes`, `nitelos.limitation_codes` (sorted, deduplicated
  enum values)
- `nitelos.backend.id`, `nitelos.backend.version`
- `nitelos.elapsed_ms` (the measured duration from the result diagnostics)
- `nitelos.collector.ids`, `nitelos.collector.durations_ms` (parallel tuple,
  when durations are given)
- `nitelos.evidence.cited_count` — the number of distinct evidence ids cited
  by the returned criteria
- `nitelos.error.code` (when execution failed)
- `gen_ai.evaluation.name` = `nitelos.verify` and
  `gen_ai.evaluation.score.label` = the decision value (ok results only)

Semantic-convention attributes follow opentelemetry-semantic-conventions
0.66b1 **incubating** definitions, pinned as string constants (the semconv
package is not a runtime dependency); they may change in future semconv
releases.

## What is never exported

Objective text, criterion descriptions, subjects, pointers, expected values,
observation data, error messages, model rationale, request ids (caller ids
may contain personal data) and any free text. If `verify` raises, the span
records the exception *type* only, never the message. `request_id` is
deliberately excluded; if your ids are safe to export, attach them on your
own surrounding span.

## Limitations

- No async variant; wrap `averify` in your own span using
  `span_attributes` on the result.
- A span is emitted per `verify` call; batch/post-processing concerns belong
  to the host exporter.
- See `examples/otel_trace_verification.py` for a runnable offline example
  using the console exporter.
