# Backends and compatibility

| Backend | Status | Criteria | Notes |
|---|---|---|---|
| Deterministic | Shipped, default | Assertions | JSON pointer equals/in/exists; no model, no network |
| SmolVLM (local) | Experimental; executability gate under review | Visual | CPU float32 Linux py3.12 validated path; adapter arrives with NIT-008 |

The SmolVLM backend pins `HuggingFaceTB/SmolVLM-500M-Instruct` @
`a7da5b986cb59b408707209984f360a5f4ad7e47` with a per-file SHA-256 manifest,
offline loading (local-files-only, safetensors, no remote code), greedy decode
of at most 8 tokens and a strict three-label parser. An attempt-1 G3 gate
record exists (a probe decoded `' UNKNOWN.'` → invalid under the strict
parser); the gate's outcome is pending architectural review, so the backend
status above is worded to stay true either way. No visual accuracy claim is
made. Two images per visual criterion maximum; model context is bounded (the
last eight actions by name/status, ≤2,048 text tokens, ≤4,096 processed).

Compatibility is declared per validated combination, never inferred. There is
no `all` extra and no hosted adapter in v0.1.

Verification without a visual backend is complete: every deterministic feature
works with zero optional dependencies.
