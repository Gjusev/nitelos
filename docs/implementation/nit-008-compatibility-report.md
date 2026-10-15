# NIT-008 compatibility and smoke report

Two checkpoint eras, recorded honestly per ADR-012. All runs: WSL Ubuntu,
Python 3.12, CPU float32, greedy, max_new_tokens 8 (40 for D3 captions),
no sampling parameters, decode-only-new, strict parser unchanged.

## Era 1 — SmolVLM-500M-Instruct @ a7da5b9 (G3 FAILED; history)

- Prompt v1 + the approved bounded iteration round (v2 instruction-last,
  v3 completion-suffix; candidates fixed before any run): **0/44 valid
  labels** — every generation decoded to exactly `' UNKNOWN.'` across all
  templates, all criteria, including trivially-decisive D1/D2 diagnostics.
- D3 open captions on smoke-01 produced accurate scene descriptions
  (pipeline and comprehension intact; failure was single-word choice-format
  compliance). Records: `benchmarks/smoke-run-local-smoke-run.json`,
  `benchmarks/iteration-round.json`, `benchmarks/d3-diagnostic.json`.
- torch 2.14.1+cpu / transformers 5.19.0; load 1754.8 ms; cold 10428.6 ms;
  warm mean 5070.8 ms; peak RSS ~3.2 GiB.

## Era 2 — SmolVLM2-2.2B-Instruct @ 482adb5 (ADR-012; G3 PASSED)

- Sanity caption (before smoke): accurate scene description of smoke-01
  ("dashboard of a software application named Orbit Export..."). Record:
  `benchmarks/d3-2.2B-sanity.json`.
- **12-case smoke with prompt v1 (hash 08fde1e3..., unchanged): 11/11
  model generations valid; 10 decisive labels (9 SUPPORTED decisions + 1
  UNKNOWN abstention from SMK-002); 0 backend errors; SMK-005 resolved by
  policy alone (ok/abstained, 74 ms, no model call).** G3 (>=1 valid
  non-abstained label) is satisfied.
- Agreement with the authored smoke labels: 4/12 matches (SMK-001, 003,
  010, 011 SUPPORTED; SMK-002 UNKNOWN; the model answered SUPPORTED on
  cases authored REFUTED/UNKNOWN — an honest over-claim bias recorded for
  AR-3; no accuracy claim is made from these dev labels).
- Environment: Linux py3.12.15, AMD Ryzen 5 7600X; torch 2.14.1+cpu,
  torchvision 0.29.1+cpu, transformers 5.19.0, num2words 0.5.14; model
  manifest 15 files verified (shards 7c88a90e.../cf3d0958...); load
  3303.7 ms; cold 52490.4 ms; warm mean 28294.9 ms (two-image cases
  ~48-51 s); wall 363.7 s; peak RSS 10,388,680 KiB (~9.9 GiB, ru_maxrss).
  Record: `benchmarks/smoke-run-2.2B.json`.

## Dependency additions (both pre-authorized "processor genuinely requires it")

- torchvision 0.29.1+cpu: transformers 5.19's smolvlm image processor
  imports torchvision.transforms.v2.functional at module level (unguarded).
- num2words 0.5.14: the SmolVLM2 processor raises ImportError without it.

## Known upstream quirks (recorded, not fixed)

- Era-1 checkpoint generation_config pad_token_id 128002 outside the
  32000-entry vocabulary (A1: accepted, config never mutated).
- transformers deprecation warnings: `torch_dtype` -> `dtype`;
  processor kwargs should move into `processor_kwargs`. Cosmetic; loads and
  generation work. No adapter change made.

## Dev-label scope

Smoke labels are development-only, authored from what a careful human sees
in the pixels; nothing here is an accuracy benchmark (doc 06), and the
4/12 agreement is reported as an observation for AR-3, not tuned on.
