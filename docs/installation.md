# Installation

Nitelos targets Python 3.12 and 3.13. The core needs only pydantic and pillow;
everything else is an opt-in extra.

nitelos is published on PyPI ([pypi.org/project/nitelos](https://pypi.org/project/nitelos/),
0.1.0 at the time of writing), so the commands below install the released
package. To work on the source instead, see [From a checkout](#from-a-checkout).

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

## The v0.2 integration extras

Each extra installs one integration's dependency; all of them load lazily
and importing `nitelos` never pulls them in.

| Extra | Installs | Guide |
|---|---|---|
| `nitelos[claude-code]` | nothing beyond core (the plugin launcher needs your Python) | [claude-code.md](claude-code.md) |
| `nitelos[otel]` | the OpenTelemetry API | [opentelemetry.md](opentelemetry.md) |
| `nitelos[inspect]` | inspect-ai 0.3.x | [inspect.md](inspect.md) |
| `nitelos[deepeval]` | deepeval 2.x | [deepeval.md](deepeval.md) |
| `nitelos[mcp]` | the mcp package | [mcp.md](mcp.md) |
| `nitelos[langgraph]` | langgraph 1.x | [langgraph.md](langgraph.md) |
| `nitelos[playwright]` | nothing beyond core (Playwright itself is the caller's dependency) | [collectors.md](collectors.md#the-playwright-page-state-helper-nitelosplaywright-nit-022) |

The `git`, `junit`, `github` and `http` collectors are stdlib-only and need
no extra beyond core ([collectors.md](collectors.md)).

There is no `all` extra by design: it would pull GPU stacks into core users.

## From a checkout

With [uv](https://docs.astral.sh/uv/) and the committed lockfile:

```text
uv sync --frozen                      # core plus the dev tools (pytest, ruff, mypy)
uv sync --frozen --extra eval         # the same plus the eval extra
uv sync --frozen --no-dev             # core only
uv run python examples/quickstart.py  # prints decision: success
```

`--frozen` installs exactly the locked versions; uv includes the `dev` group by
default, so `--no-dev` is the core-only install. The `local` extra resolves
torch and torchvision from the PyTorch CPU index declared in `pyproject.toml`.
