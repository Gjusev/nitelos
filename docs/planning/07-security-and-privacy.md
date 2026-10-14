# Security and privacy

The trusted computing base is the host application, installed Python code/dependencies, explicitly constructed policy/trust configuration, and its authorized collectors. Evidence and model output are untrusted data. A custom Python backend is trusted executable code, not sandboxed by the protocol. Nitelos is not an adversarial process sandbox.

## Threat model and controls

| Threat | Boundary / control | Required test / remaining limitation |
|---|---|---|
| Screenshot or DOM prompt injection | Evidence never becomes system instructions; fixed prompt, no model tools, exact output parser | SEC-01 embeds “ignore task, report success”; ensure no authority/action path. Model may still be deceived; strict policy disallows model inference by default |
| Malicious tool response / self-attested trust | Data-only JSON; host trust binds exact evidence digest/context; no deserialized bindings | SEC-02 forged source/trusted fields cannot satisfy external criterion; hostile host itself is outside scope |
| Wrong entity or stale state | Exact subject/checkpoint/freshness, final phase required | POL-04; collector metadata can still lie or race with later state changes |
| Secrets/PII in screenshots | Local-first, no persistence/default upload, explicit caller pre-redaction | SEC-03 sentinel secret absent from logs/errors/repr; cannot guarantee automatic visual redaction |
| Credential leakage | No credentials in request schemas; sanitized errors; provider config deferred | Log-capture tests include exception text containing secret; no raw exception interpolation |
| Unauthorized API/database reads | v0.1 performs none; caller supplies snapshots | SEC-04 deny network test; later allowlisted read-only collectors need least-privilege credentials |
| Untrusted backend output | Strict schema, allowed criterion/evidence IDs, bbox bounds and score checks | BAK-02 malformed/fabricated outputs => backend_error, never success |
| Image decompression bomb | Check signature, size/dimensions/frame count before full decode; explicit pixel limit; Pillow bomb warnings become errors | SEC-05 oversized header/animated/malformed fixtures; decoder vulnerabilities remain dependency risk |
| Oversized/deep payloads | Byte/count/depth/token ceilings before costly inference; no silent truncation | SEC-06 boundary and limit+1 tests, model not called |
| Path traversal / SSRF | Core byte store has no URL/path resolver; evaluation loader root confinement and no remote references | SEC-07 relative traversal, absolute/UNC paths and escaping symlinks/reparse points rejected |
| Model supply-chain code execution | Safetensors, pinned file manifest, remote code disabled, offline load | SEC-08 no unsafe pickle/custom Python model code; inspect actual pinned distribution |
| Unbounded inference | Per-criterion token bound, sequential instance, cooperative deadline, explicit resource errors | LIFE-02 timeout/cancel/busy tests; hard kernel stop not guaranteed |
| Unsafe output reports | Escape Markdown/HTML display if later rendered; JSON output only in MVP | Imported rationale never executed; no clickable untrusted URLs auto-opened |
| Unauthorized logging/export | Standard logger without handlers; only allowlisted safe fields | SEC-03; diagnostic hashes/IDs still correlate activities |

## Data lifecycle

Caller controls acquisition and consent. Do not silently read home directories, browser cookies, environment secrets, clipboard or caches. Original bytes remain in memory until the invocation releases references; Python does not guarantee secure memory erasure. Backend retains weights/processor, not evidence history. Caller owns its input store and may retain it independently. No telemetry, analytics, cache upload or automatic model download.

Default result serialization excludes raw bytes, observation values, action arguments, objective text and model rationale. Rationale can exist internally for custom adapters but exporting it requires an explicit caller option, with an untrusted-content label; the shipped Smol adapter produces none. Request serialization is a separate explicit operation and may contain sensitive content. `repr` of evidence/config/result must be safe: IDs/types/counts only, no raw values. Errors include field paths without offending values.

Evaluation writes results only to a user-selected new directory. Requests/images are referenced, not copied. Warn in documentation that filenames, subjects and IDs may contain personal data; use synthetic identifiers. Publish only reviewed fixtures and deidentified reports. Retention/deletion is caller-managed; no database or retention scheduler is needed for MVP. No sensitive content in test fixtures.

## Hosted and authenticated integrations (future gates)

Explicit host selection of a remote backend plus `allow_remote=true` must precede transmission. Document exactly what fields/images leave the process and the provider's retention policy as of integration release. Redaction is performed before hashing and trust binding of the transmitted view; preserve a derivation reference only when safe, not hidden raw secrets. Reject endpoints from untrusted trace data and forbid redirecting authorization headers cross-origin. Native SDK telemetry/retries require review.

Read-only external collectors receive narrowly scoped credentials from the trusted host. They may query only explicitly configured sources/subjects; models cannot invent URLs or SQL. State mutation, payment retry, remediation and agent actions remain outside Nitelos. Prefer adapters to mature existing observer libraries after rights/security review. Reading external state may still expose sensitive data and is not authorized merely because a screenshot mentions it.

## Security release gate

All SEC tests pass without network; wheel inventory includes only intended files; no real secrets in source/history/fixtures; direct and transitive dependency audit reviewed; no unresolved high/critical reachable vulnerability in shipped paths; model files and downloads documented; unsafe model execution paths absent. Do not claim that these checks eliminate prompt injection, prove screenshots genuine, or cryptographically attest external state.
