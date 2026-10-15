# Dependency and license inventory (release grade — NIT-015)

Sources: installed distribution metadata (`importlib.metadata`, `License-Expression`/
classifiers) from the frozen `uv.lock` (recorded 2026-10-14, NIT-001; refreshed from
the integration and `nit/008-smolvlm` locks on 2026-10-16 for this audit) and
`uv.lock` package blocks read directly. Every row is re-verified against the actual
resolved wheels at release time (REL-04 makes this table machine-checked against the
lock); license expressions are SPDX. **Release action** marks items that need a human
decision or a notice, not just recording.

## Core runtime — the shipped wheel's dependency closure

`pip install nitelos` installs exactly these (pyproject dependencies: pydantic, pillow):

| Distribution | Version | License | Source | Notes |
|---|---|---|---|---|
| pydantic | 2.14.1 | MIT | github.com/pydantic/pydantic | |
| pydantic-core | 2.50.1 | MIT | github.com/pydantic/pydantic-core (Rust) | compiled wheel |
| annotated-types | 0.8.0 | MIT | github.com/annotated-types/annotated-types | |
| typing-extensions | 4.16.0 | PSF-2.0 | github.com/python/typing_extensions | |
| typing-inspection | 0.4.4 | MIT | github.com/pydantic/typing-inspection | |
| pillow | 12.3.0 | MIT-CMU | github.com/python-pillow/Pillow | **Release action**: the wheel bundles compiled image libraries (libjpeg-turbo, libwebp, libtiff, zlib, libimagequant, raqm/harfbuzz/fribidi variants per platform). MIT-CMU covers the Pillow code; carry the wheel's bundled-library notice text into NOTICE at release if the wheels embed non-MIT components (verify via `unzip -l` + the wheel's LICENSE block per platform built). |

## Optional extra `eval` — `pip install 'nitelos[eval]'`

| Distribution | Version | License | Source | Notes |
|---|---|---|---|---|
| numpy | 2.5.4 | BSD-3-Clause | github.com/numpy/numpy | **Release action**: BSD-3 requires the notice be retained; wheels bundle compiled math libraries (OpenBLAS or similar) whose notices ship inside the wheel — review once per platform at release. |
| scipy | 1.18.1 | BSD-3-Clause | github.com/scipy/scipy | same bundled-math-library review |

No further transitives (both wheels are self-contained beyond numpy).

## Optional extra `local` — `pip install 'nitelos[local]'` (experimental visual backend)

Versions from the frozen lock on the `nit/008-smolvlm` branch (`torch==2.14.1+cpu`,
`transformers==5.19.0` + transitives as locked). Membership below is the known closure;
**Release action**: re-derive with `uv tree --extra local` from the merged release
lock and reconcile (REL-04 assertion), then capture each wheel's metadata verbatim.

| Distribution | Version | License | Source | Notes |
|---|---|---|---|---|
| torch | 2.14.1+cpu | BSD-3-Clause | download.pytorch.org/whl/cpu | the +cpu local-version wheel; **Release action**: PyTorch's legal notice covers bundled components — attach the `LICENSE` / third-party notice file content review; the +cpu wheel excludes CUDA/EULA components, confirm per wheel. |
| transformers | 5.19.0 | Apache-2.0 | github.com/huggingface/transformers | |
| tokenizers | 0.23.3 | Apache-2.0 | github.com/huggingface/tokenizers (Rust) | compiled wheel |
| safetensors | 0.8.0 | Apache-2.0 | github.com/huggingface/safetensors (Rust) | compiled wheel |
| huggingface-hub | 2.2.0 | MIT | github.com/huggingface/huggingface_hub | |
| hf-xet | 1.7.0 | Apache-2.0 | github.com/huggingface/hf_xet (Rust) | **verify from wheel metadata at release** |
| filelock | 4.2.0 | Unlicense | github.com/tox-dev/filelock | public-domain-equivalent; attribution retained |
| fsspec | 2026.9.0 | BSD-3-Clause | github.com/fsspec/filesystem_spec | |
| jinja2 | 3.1.6 | BSD-3-Clause | github.com/pallets/jinja | |
| markupsafe | 3.0.4 | BSD-3-Clause | github.com/pallets/markupsafe | compiled wheel |
| mpmath | 1.3.0 | BSD-3-Clause | github.com/mpmath/mpmath | |
| sympy | 1.14.0 | BSD-3-Clause | github.com/sympy/sympy | torch transitive |
| networkx | 3.7 | BSD-3-Clause | github.com/networkx/networkx | torch transitive |
| regex | 2026.9.29 | Apache-2.0 | github.com/mrabarnett/mrab-regex | compiled wheel; **verify expression from metadata** (historically also listed ASL/BSD dual) |
| tqdm | 4.70.1 | MPL-2.0 OR MIT | github.com/tqdm/tqdm | dual-licensed; either satisfies |
| pyyaml | 6.0.3 | MIT | github.com/yaml/pyyaml | compiled wheel (libyaml bundling varies) |
| packaging | 26.3 | Apache-2.0 OR BSD-2-Clause | github.com/pypa/packaging | |
| typing-extensions | 4.16.0 | PSF-2.0 | (see core) | shared with core |

## Development group (not shipped; distributed in-repo via the lock)

| Distribution | Version | License |
|---|---|---|
| pytest | 9.1.1 | MIT |
| pytest-asyncio | 1.4.0 | Apache-2.0 |
| pytest-cov | 7.1.0 | MIT |
| coverage | 7.16.2 | Apache-2.0 |
| ruff | 0.17.0 | MIT |
| mypy | 2.4.0 | MIT |
| mypy-extensions | 1.1.0 | MIT |
| librt | 0.16.0 | MIT |
| hatchling | 1.32.4 | MIT |
| pluggy | 1.6.0 | MIT |
| iniconfig | 2.3.1 | MIT |
| packaging | 26.3 | Apache-2.0 OR BSD-2-Clause |
| pathspec | 1.1.1 | MPL-2.0 |
| trove-classifiers | 2026.9.21.13 | Apache-2.0 |
| pygments | 2.21.0 | BSD-2-Clause |
| colorama | 0.4.6 | BSD-3-Clause (Windows only) |
| tomlkit | 0.15.1 | MIT |
| annotated-doc | 0.0.5 | MIT |
| ast-serialize | 0.13.0 | MIT |
| click | 8.5.0 | BSD-3-Clause |
| typer | 0.27.3 | MIT |
| rich | 15.0.0 | MIT (+ markdown-it-py MIT, mdurl MIT, pygments BSD-2) |
| anyio / httpcore2 / httpx2 / h11 / idna / truststore / shellingham / httpx2-jsfetch / setuptools | per lock | MIT / BSD-3-Clause |
| filelock, fsspec, tqdm, pyyaml, networkx, packaging (shared with groups above) | per lock | as above |

**pathspec (MPL-2.0) release action**: MPL-2.0 is a weak copyleft license. It appears
only in the dev group (hatchling build backend / tooling) and is NOT part of any
shipped wheel or installable extra. No notice obligation attaches to distribution of
the wheel; the in-repo lock distributes metadata only. Record this determination at
release. If a future change moves pathspec into a runtime closure, MPL-2.0 filing
duties apply — treat that as a gate.

## Model checkpoints — separately provisioned, never redistributed

No model weights are bundled in the wheel, sdist or repository. Users download them
from the Hugging Face Hub under the upstream license.

| Checkpoint | Role | Revision | License | Provenance record |
|---|---|---|---|---|
| HuggingFaceTB/SmolVLM2-2.2B-Instruct | **Current pin** (ADR-012, user-approved 2026-10-15) | `482adb5…` | Apache-2.0 (model card) | per-file SHA-256 manifest verified against upstream LFS oids at provision time; the re-run smoke report records the manifest digests. Note: the "2.2B" size does not exist in the original SmolVLM series — the pin refers to the SmolVLM2 series (ADR-012 records the swap rationale). |
| HuggingFaceTB/SmolVLM-500M-Instruct | Historical (original pin; superseded) | `a7da5b986cb59b408707209984f360a5f4ad7e47` | Apache-2.0 | probe record: `model.safetensors` SHA-256 equals the upstream LFS oid `d05b567e…`; G3 history (format instruction-following failure under the strict parser) is retained in the NIT-008 iteration/D3 records |

**Release action**: at release, attach the final reviewed model manifest (revision +
per-file SHA-256 + upstream LFS oid match) for whichever checkpoint the release
candidate documents; restate "no redistribution" in the release notes; confirm PKG
tests' forbidden-suffix bans still pass (they already assert no weights ship).

## Tooling

uv (0.9.21 Windows dev host / 0.13.1 WSL Ubuntu) — MIT OR Apache-2.0. GitHub Actions
pinned by SHA: actions/checkout v7.0.1 `3d3c42e5…`, astral-sh/setup-uv v10.3.0
`1c37ad07…`; new actions introduced by the release workflow are pinned and recorded
before landing (release-workflow.md).

## Open verification items (tracked in release-checklist.md)

1. Capture `License-Expression` verbatim from every resolved wheel of the local extra
   at release (the two Rust wheels and `regex` are the flagged ones).
2. Pillow/NumPy/SciPy bundled-library notice review per built platform.
3. The `uv tree` closure reconciliation (REL-04 machine check).
