# Backends and compatibility

| Backend | Status | Criteria | Notes |
|---|---|---|---|
| Deterministic | Shipped, default | Assertions | JSON pointer equals/in/exists; no model, no network |
| SmolVLM2 (local) | Experimental; executability gate PASSED on the development smoke set | Visual | CPU float32 Linux py3.12 validated path; 11/11 valid labels, 10 decisive (dev-only record) |

The visual backend pins `HuggingFaceTB/SmolVLM2-2.2B-Instruct` @
`482adb537c021c86670beed01cd58990d01e72e4` (ADR-012; sharded safetensors)
with a per-file SHA-256 manifest, offline loading (local-files-only,
safetensors, no remote code), greedy decode of at most 8 tokens and a strict
three-label parser. The executability gate (G3) PASSED on the 12-case
development smoke set with the unchanged prompt v1: 11/11 generated labels
valid under the strict parser, 10 decisive, 0 backend errors. Honest
observation from that dev-only record: the model is format-compliant but
over-claiming (it answered SUPPORTED on cases authored as refuted/unknown;
agreement with the authored labels was 4/12). No accuracy claim is made from
these development labels; benchmark numbers are pending the frozen evaluation
(NIT-013). History: the original pin SmolVLM-500M-Instruct @ `a7da5b9…`
failed the gate (0/44 valid labels — every generation `' UNKNOWN.'`) and was
replaced per ADR-012; the failure records are retained. Two images per
visual criterion maximum; model context is bounded (the last eight actions by
name/status, ≤2,048 text tokens, ≤4,096 processed).

Compatibility is declared per validated combination, never inferred. There is
no `all` extra and no hosted adapter in v0.1.

Verification without a visual backend is complete: every deterministic feature
works with zero optional dependencies.
