# Technology decisions and dependency strategy

Single Python package, `src` layout, Python **3.12 and 3.13** tested for core; local model extra initially supported on Linux CPU Python 3.12 only, with additional platforms declared only after real smoke tests. Set package `requires-python >=3.12,<3.14` for the initial validated release; extending support is a tested minor change. This limits an initial compatibility matrix without relying on experimental interpreter/model-wheel combinations.

| Selection | Why / performance and maintenance tradeoff | Alternative and disposition |
|---|---|---|
| Pydantic v2 | Strict public JSON contracts, validation and JSON Schema; boundary overhead acceptable beside image/model work | Dataclasses smaller but require bespoke recursive validation/schema tooling; keep internal simple structures where useful |
| Pillow | Mature bounded PNG/JPEG decode and dimensions | Handwritten decoders unacceptable; OpenCV heavier and unnecessary |
| Standard library asyncio/logging/hashlib/json | Minimal lifecycle, safe diagnostics and digest code | Framework orchestration unnecessary |
| Transformers + Torch, optional `local` extra | Documented SmolVLM execution, CPU baseline, isolated heavy imports | llama.cpp/ONNX/MLX add conversion/platform variants; not first release |
| SciPy + NumPy, optional `eval` extra | Tested numerical intervals and bootstrap utilities | Pure custom statistical library is more maintenance risk; no SciPy import in normal verify |
| Hatchling | Conventional wheel/sdist build with explicit file selection | setuptools also adequate; no plugins needed |
| uv development lock | Reproducible dev/CI dependency resolution, frozen sync | pip-only requirements easier but fragmented optional environments; package remains pip-installable |
| pytest + pytest-asyncio + pytest-cov | Offline behavioral fixtures, lifecycle tests, branch visibility | unittest possible but less ergonomic parametrization |
| Ruff + mypy strict | Fast lint/format plus static contracts, typed public SDK | Pyright is credible; avoid maintaining two strict checkers |
| GitHub Actions | Linux/Windows core matrix and isolated optional smoke workflows | No external CI service needed |
| Plain Markdown documentation | Accessible, reviewable and dependency-free initial docs | MkDocs optional later, not a runtime/build prerequisite |

Do not add FastAPI (no server), Typer (no general CLI), httpx (no hosted transport yet), Playwright (caller recipe only), LangChain, a database, queue, telemetry SDK or plugin registry to runtime dependencies. Evaluation module uses argparse. Async facade is explicit and bounded, not an asynchronous workflow framework.

## Version baseline and lock procedure

Metadata was read from `https://pypi.org/pypi/NAME/json` on 2026-10-14. Candidate versions observed: Pydantic 2.14.1, Pillow 12.3.0, Transformers 5.19.0, Torch 2.14.1, pytest 9.1.1, Ruff 0.17.0, mypy 2.4.0, Hatchling 1.32.4, uv 0.13.1, SciPy 1.18.1. These are **observed candidates, not an installed or tested lock**. No compatibility claim is made for their combination.

NIT-001 resolves the core/dev matrix; NIT-008 locks the local extra after actual inference. Start with the listed versions; if model-card auto classes differ in Transformers 5, use the documented supported class for the same pinned checkpoint and record the mapping. If no compatible safe local stack can be established, stop for review. Do not quietly downgrade to a vulnerable dependency or change the model. Pin final direct and transitive dev/eval dependencies in `uv.lock`; use `uv sync --frozen` in CI. The [uv synchronization docs](https://docs.astral.sh/uv/concepts/projects/sync/) distinguish lock refresh from frozen installation.

Published library constraints should use tested compatible ranges, e.g. Pydantic major 2 and Pillow tested minor/major range, with lower bounds equal to the oldest actually tested version. Do not assert minimum versions based merely on import success. Package metadata includes `local` and `eval` extras; dev dependencies are a dependency group. Avoid an `all` extra that accidentally pulls GPU/provider stacks into core users. CPU Torch wheel source is explicitly documented for the tested Linux environment; CUDA wheels/vendors have additional distribution terms. No model weights bundled in wheel/sdist.

## Material licensing inventory

This is a release-input inventory, not a substitute for auditing resolved artifacts. License sources are upstream LICENSE files and PyPI distribution metadata. SPDX UNKNOWN/NOASSERTION requires manual review, not an assumed permissive license.

| Component | Observed license / source | Release action |
|---|---|---|
| Pydantic | MIT, [repository](https://github.com/pydantic/pydantic) | Preserve notices; inspect pydantic-core and transitive wheels |
| Pillow | MIT-CMU, [license](https://github.com/python-pillow/Pillow/blob/main/LICENSE) | Review bundled image-library notices in wheels |
| Transformers | Apache-2.0, [license](https://github.com/huggingface/transformers/blob/main/LICENSE) | Inspect Hub/tokenizer/safetensors transitive licenses |
| Torch | Composite Apache/BSD/MIT/BSL/LLVM-exception metadata; [license](https://github.com/pytorch/pytorch/blob/main/LICENSE) | Audit selected CPU wheel and third-party notices; no blanket “Torch is only BSD” assertion |
| SmolVLM checkpoint | Apache-2.0, [model card](https://huggingface.co/HuggingFaceTB/SmolVLM-500M-Instruct) | Separate optional download; preserve source/revision/license; do not redistribute training data |
| NumPy / SciPy | BSD-family, [NumPy license](https://github.com/numpy/numpy/blob/main/LICENSE.txt), [SciPy license](https://github.com/scipy/scipy/blob/main/LICENSE.txt) | Inspect binary math-library notices in resolved wheels |
| pytest / Ruff / mypy / Hatchling | MIT metadata; upstream repositories linked from PyPI | Development-only inventory; review bundled dependencies |
| uv | MIT OR Apache-2.0 metadata, [repository](https://github.com/astral-sh/uv) | Tool pin and license inventory |
| pytest-asyncio / pytest-cov / audit tooling | Exact selected-version license to verify in NIT-001/NIT-015 | No release until recorded; don't guess unseen versions |
| Authored fixtures/docs | Project contributors grant Apache-2.0 for authored material | Use original UI designs, system fonts with no redistribution, synthetic names/data |
| External datasets and screenshot assets | Individual terms, not repository code license | Not distributed in v0.1; local research only after access/rights review |

Permissive dependencies can coexist with Apache project licensing when notices and applicable conditions are preserved; this does not relicense them. [Apache third-party guidance](https://www.apache.org/legal/resolved.html) supports the review process. CC-BY-NC AbstentionBench material and unlicensed AgentHorizon/UI-Venus code/assets are not incorporated. Source links in this plan do not grant redistribution permission.

## Compatibility and performance gates

Core import test runs with no extras and network disabled. Dependency absence produces an actionable optional-extra error without a traceback containing paths/secrets. Windows core support includes path/reparse-point tests; local backend support is restricted to tested hardware. Unit tests never need model downloads. A locked optional integration job validates current Transformers/model compatibility before release; future updates repeat that gate. New dependencies require a task-linked benefit, import-size assessment, license record and ADR if they change boundaries.
