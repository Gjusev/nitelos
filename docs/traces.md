# Traces and caller collection

Nitelos has no runtime Playwright/browser dependency and never drives the
agent. You capture, you normalize, you hand over:

1. Take a screenshot with your own stack (`page.screenshot()` or anything else).
2. Reduce page state into small JSON observations — raw HTML, accessibility
   trees and tool logs are not inputs.
3. Build evidence with the digest-computing factories
   (`Evidence.screenshot/observation/action`).
4. Either construct a `VerificationRequest` directly or record a
   `Trace` (schema 1: ordered evidence + bounded metadata, nothing else —
   no bytes, trust, policy or oracle labels) and call `trace.to_request(...)`
   when you know the request context.

The complete recipe with code is
[recipes/caller-collection.md](recipes/caller-collection.md). Facts worth
restating: normalization is the caller's job; the built-in visual adapter
takes at most two images per criterion; the model context window is the last
eight actions by name and reported status only — arguments are kept for audit
and never transmitted.

```python
from nitelos import parse_trace

trace = parse_trace(trace_json_text)
request = trace.to_request(
    objective="...",
    criteria=[...],
    request_id="...",
    checkpoint_id="...",
    as_of="2026-10-20T10:01:00Z",
)
```
