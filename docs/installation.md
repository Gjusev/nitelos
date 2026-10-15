# Installation

Nitelos targets Python 3.12 and 3.13 and installs with no optional dependencies.

## Core (deterministic verification)

```text
pip install nitelos
```

or with uv:

```text
uv add nitelos
```

The core install verifies assertions, checks eligibility and trust, and returns
structured results — fully offline, no model.

## The `eval` extra (metrics and statistics)

```text
pip install 'nitelos[eval]'
```

NumPy and SciPy for the evaluation module: Wilson/Clopper-Pearson intervals,
group bootstrap, benchmark metrics and the sequential runner. These load lazily;
importing `nitelos` never pulls them in.

## The `local` extra (experimental visual backend)

```text
pip install 'nitelos[local]'
```

CPU-only Torch/Transformers (plus torchvision and num2words, which the processor
chain requires) for the pinned checkpoint
`HuggingFaceTB/SmolVLM2-2.2B-Instruct` @ revision
`482adb537c021c86670beed01cd58990d01e72e4` (ADR-012; the earlier
SmolVLM-500M pin failed the executability gate and is retained as history —
see [backends.md](backends.md)). Status: **Linux CPU on Python 3.12 is the
validated path** (doc 08); Windows is declared unsupported until a recorded
smoke run exists. Weights are never bundled: provision the model directory
yourself (per-file SHA-256 manifest required; see
[backends.md](backends.md)) and point `NITELOS_MODEL_DIR` at it.

There is no `all` extra by design: it would pull GPU stacks into core users.
