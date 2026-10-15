# Evidence and provenance limits

What Nitelos can and cannot tell you about the evidence it judged:

- **Digests detect change, not forgery.** A SHA-256 catches later byte
  modifications; it cannot prove a screenshot was honest when captured, that a
  source label is truthful, or that metadata was not manipulated before you
  supplied it.
- **Trust is host-constructed only.** `TrustBinding` objects bind an evidence
  id, digest, source, subject and checkpoint after *you* independently
  authorized the collection. Nothing parsed from request/trace JSON can create
  one, and a forged `source_id` satisfies nothing without the exact digest.
- **Scope cannot promote itself.** Visual, observed, behavioral and external
  criteria stay in their lanes; an HTTP 200 or a tool status is behavioral
  evidence at best.
- **Deduplicated bytes keep their events.** Identical image bytes may appear
  in several capture events; each event keeps its own identity and timestamps.
- **Model rationale is untrusted** diagnostic text: excluded from default
  serialization, never part of policy logic.
- **Model preprocessing is declared, not hidden.** Any resize/conversion is
  recorded in diagnostics; original evidence digests are never rewritten.

There is no claim that any check proves screenshots genuine or attests external
state cryptographically.
