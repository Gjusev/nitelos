# Security policy

## Reporting a vulnerability

Please report vulnerabilities **privately** — do not open a public issue.

- Prefer GitHub's private vulnerability reporting on the repository, or
- email the maintainers directly (see the repository's contact information).

Include what you can of: affected versions/commits, a minimal synthetic
reproduction (never real secrets or user data), and impact assessment. We will
acknowledge private reports and coordinate fixes and disclosure with you.

## Scope notes

Nitelos treats evidence and model output as untrusted data by design
(`docs/planning/07-security-and-privacy.md` is the normative threat model).
Hardening exists for path traversal, decompression bombs, oversized payloads
and prompt-injection-style content, and errors/reprs/logs are value-free.

Out of scope by design in v0.1: Nitelos is not an adversarial process
sandbox; a custom Python backend is trusted executable code; no claim is made
that checks prove screenshots genuine or cryptographically attest external
state. A hostile host is outside the threat model.
