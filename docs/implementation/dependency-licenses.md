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
| scipy | 1.18.1 | BSD-3-Clause | github.com/scipy/scipy | **Release action**: same as numpy — BSD-3 notice retention and the bundled-math-library review once per platform at release. |

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
| fsspec | 2026.6.0 | BSD-3-Clause | github.com/fsspec/filesystem_spec |held down by the inspect tree's s3fs constraint (was 2026.9.0 before NIT-024) |
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
| torchvision | 0.29.1+cpu | BSD-3-Clause | download.pytorch.org/whl/cpu | AR-3 addition (nit/008-smolvlm @ 37e4b8a/d945626): module-level unguarded `from torchvision.transforms.v2 import functional as tvF` in transformers 5.19's smolvlm image processor — verified in the installed wheel source; **Release action**: same PyTorch legal-notice review as torch |
| num2words | 0.5.14 | MIT (verify at release) | github.com/savoirfairelinux/num2words | AR-3 addition: SmolVLM2 processor raises ImportError without it (guarded import, hard requirement at construction); pure-Python |

## Optional extra `otel` — `pip install 'nitelos[otel]'` (v0.2, NIT-028)

The extra installs the OpenTelemetry API only; the host brings its own SDK and exporter.

| Distribution | Version | License | Source | Notes |
|---|---|---|---|---|
| opentelemetry-api | 1.45.1 | Apache-2.0 | github.com/open-telemetry/opentelemetry-python | pure-Python; added 2026-10-20 (orchestrator, NIT-028 central change) |
| typing-extensions | 4.16.0 | PSF-2.0 | github.com/python/typing_extensions | shared with core |

## Development group (not shipped; distributed in-repo via the lock)

| Distribution | Version | License |
|---|---|---|
| pytest | 9.1.1 | MIT |
| opentelemetry-sdk | 1.45.1 | Apache-2.0 |
| opentelemetry-semantic-conventions | 0.66b1 | Apache-2.0 |
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
| rich | 13.9.4 | MIT |
| markdown-it-py | 4.2.0 | MIT |
| mdurl | 0.1.2 | MIT |
| anyio / httpcore2 / httpx2 / h11 / idna / truststore / shellingham / httpx2-jsfetch / setuptools | per lock | MIT / BSD-3-Clause |
| docopt | 0.6.2 | MIT | orphaned lock entry — no locked package depends on it (dev-tool resolution leftover); not in any shipped closure |
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

## Optional extra `deepeval` — `pip install 'nitelos[deepeval]'`

Added 2026-10-20 (NIT-026, central provisioning). Rows generated from the resolved
wheels' metadata against the frozen lock; ambiguous classifier licenses are marked
for verification at release. This tree is deliberately NOT in the dev group.

| Distribution | Version | License | Source | Notes |
|---|---|---|---|---|
| aiohappyeyeballs | 2.7.1 | PSF-2.0 | github.com/aio-libs/aiohappyeyeballs | |
| aiohttp | 3.14.5 | Apache-2.0 AND MIT | github.com/aio-libs/aiohttp | |
| aiosignal | 1.4.0 | Apache-2.0 | github.com/aio-libs/aiosignal | |
| anthropic | 0.49.0 | MIT | github.com/anthropics/anthropic-sdk-python | |
| attrs | 26.1.0 | MIT | pypi.org/project/attrs | |
| backoff | 2.2.1 | MIT | github.com/litl/backoff | |
| certifi | 2026.10.19 | MPL-2.0 | github.com/certifi/python-certifi | |
| cffi | 2.1.1 | MIT-0 | github.com/python-cffi/cffi | |
| charset-normalizer | 3.5.2 | MIT | pypi.org/project/charset-normalizer | |
| cryptography | 50.0.2 | Apache-2.0 OR BSD-3-Clause | github.com/pyca/cryptography | compiled wheel |
| deepeval | 2.9.3 | Apache-2.0 | github.com/confident-ai/deepeval | **Release action**: the framework can call LLM providers and ships telemetry (sentry-sdk, posthog in its tree). Our metric is deterministic and offline; verify at release that importing the metric does not enable telemetry and document the opt-out envs. |
| distro | 1.9.0 | Apache-2.0 | github.com/python-distro/distro | |
| execnet | 2.1.2 | MIT | execnet.readthedocs.io/en/latest/ | |
| frozenlist | 1.8.0 | Apache-2.0 | github.com/aio-libs/frozenlist | |
| google-auth | 2.62.0 | Apache-2.0 | github.com/googleapis/google-cloud-python | |
| google-genai | 1.75.0 | Apache-2.0 | github.com/googleapis/python-genai | |
| googleapis-common-protos | 1.75.5 | Apache-2.0 | github.com/googleapis/google-cloud-python | |
| grpcio | 1.84.0 | Apache-2.0 | grpc.io | compiled wheel |
| httpcore | 1.0.9 | BSD-3-Clause | www.encode.io/httpcore/ | |
| httpx | 0.28.1 | BSD-3 (classifier; verify at release) | github.com/encode/httpx | |
| jiter | 0.17.0 | MIT | github.com/pydantic/jiter/ | compiled wheel |
| monotonic | 1.6 | Apache-2.0 | github.com/atdt/monotonic | |
| multidict | 6.9.1 | Apache-2.0 | github.com/aio-libs/multidict | compiled wheel |
| nest-asyncio | 1.6.0 | BSD-3 (classifier; verify at release) | github.com/erdewit/nest_asyncio | |
| ollama | 0.6.3 | MIT | ollama.com | |
| openai | 3.35.1 | Apache-2.0 | github.com/openai/openai-python | |
| opentelemetry-exporter-otlp-common | 0.66b1 | Apache-2.0 | github.com/open-telemetry/opentelemetry-python | |
| opentelemetry-exporter-otlp-proto-common | 1.45.1 | Apache-2.0 | github.com/open-telemetry/opentelemetry-python | |
| opentelemetry-exporter-otlp-proto-grpc | 1.45.1 | Apache-2.0 | github.com/open-telemetry/opentelemetry-python | |
| opentelemetry-proto | 1.45.1 | Apache-2.0 | github.com/open-telemetry/opentelemetry-python | |
| portalocker | 4.4.1 | BSD-3-Clause | github.com/wolph/portalocker/ | |
| posthog | 3.25.0 | MIT | github.com/posthog/posthog-python | **Release action**: telemetry client in deepeval's tree; see the deepeval row |
| propcache | 0.5.4 | Apache-2.0 | github.com/aio-libs/propcache | compiled wheel |
| protobuf | 7.36.2 | BSD-3-Clause | developers.google.com/protocol-buffers/ | compiled wheel |
| pyasn1 | 0.6.4 | BSD-2-Clause | github.com/pyasn1/pyasn1 | |
| pyasn1-modules | 0.4.2 | BSD-3 (classifier; verify at release) | github.com/pyasn1/pyasn1-modules | |
| pycparser | 3.11 | BSD-3-Clause | github.com/eliben/pycparser | |
| pytest-repeat | 0.9.4 | MPL-2.0 | pypi.org/project/pytest-repeat | |
| pytest-rerunfailures | 12.0 | MPL-2.0 | github.com/pytest-dev/pytest-rerunfailures | |
| pytest-xdist | 3.8.0 | MIT | github.com/pytest-dev/pytest-xdist | |
| python-dateutil | 2.9.0.post0 | Apache-2.0 | github.com/dateutil/dateutil | |
| requests | 2.34.2 | Apache-2.0 | github.com/psf/requests | |
| sentry-sdk | 2.72.0 | MIT | github.com/getsentry/sentry-python | **Release action**: telemetry client in deepeval's tree; see the deepeval row |
| six | 1.17.0 | MIT | github.com/benjaminp/six | |
| sniffio | 1.3.1 | Apache-2.0 | github.com/python-trio/sniffio | |
| tabulate | 0.9.0 | MIT | github.com/astanin/python-tabulate | |
| tenacity | 9.0.0 | Apache-2.0 | github.com/jd/tenacity | |
| urllib3 | 2.8.0 | MIT | pypi.org/project/urllib3 | |
| websockets | 16.1.1 | BSD-3-Clause | github.com/python-websockets/websockets | |
| wheel | 0.48.0 | MIT | github.com/pypa/wheel | |
| yarl | 1.25.1 | Apache-2.0 | github.com/aio-libs/yarl | compiled wheel |

## Optional extra `mcp` — `pip install 'nitelos[mcp]'`

Added 2026-10-20 (NIT-027, central provisioning). Rows generated from the resolved
wheels' metadata against the frozen lock. Not in the dev group.

| Distribution | Version | License | Source | Notes |
|---|---|---|---|---|
| jsonschema | 4.26.0 | MIT | github.com/python-jsonschema/jsonschema | |
| jsonschema-specifications | 2025.9.1 | MIT | github.com/python-jsonschema/jsonschema-specifications | |
| mcp | 2.3.0 | MIT | modelcontextprotocol.io | **Release action**: server framework; telemetry-free per its metadata, re-verify at release |
| mcp-types | 2.3.0 | MIT | modelcontextprotocol.io | |
| pyjwt | 2.15.1 | MIT | github.com/jpadilla/pyjwt | |
| python-multipart | 0.0.32 | Apache-2.0 | github.com/Kludex/python-multipart | |
| pywin32 | 312 | PSF-2.0 | github.com/mhammond/pywin32 | Windows-only compiled wheel |
| referencing | 0.37.0 | MIT | github.com/python-jsonschema/referencing | |
| rpds-py | 2026.9.1 | MIT | github.com/crate-py/rpds | compiled wheel |
| sse-starlette | 3.5.0 | BSD-3-Clause | github.com/sysid/sse-starlette | |
| starlette | 1.9.0 | BSD-3-Clause | github.com/Kludex/starlette | |
| uvicorn | 0.54.0 | BSD-3-Clause | uvicorn.dev/ | |

## Optional extra `inspect` — `pip install 'nitelos[inspect]'`

Added 2026-10-21 (NIT-024, central provisioning). Rows generated from the resolved
wheels' metadata against the frozen lock; rows whose wheels carry no license
classifier state the license from the upstream repository and are release-verify
items. Not in the dev group.

| Distribution | Version | License | Source | Notes |
|---|---|---|---|---|
| agent-client-protocol | 0.12.1 | MIT | agentclientprotocol.github.io/python-sdk/ | license from its repository (classifier absent) |
| aiobotocore | 3.9.2 | Apache-2.0 | github.com/aio-libs/aiobotocore | |
| aioitertools | 0.13.0 | MIT | pypi.org/project/aioitertools | |
| beautifulsoup4 | 4.15.0 | MIT | www.crummy.com/software/BeautifulSoup/bs4/ | |
| boto3 | 1.43.106 | Apache-2.0 | github.com/boto/boto3 | license from its repository (classifier absent) |
| botocore | 1.43.106 | Apache-2.0 | github.com/boto/botocore | license from its repository (classifier absent) |
| debugpy | 1.8.22 | MIT | github.com/microsoft/debugpy | |
| docstring-parser | 0.18.0 | MIT | github.com/rr-/docstring_parser | |
| fastapi | 0.156.3 | MIT | github.com/fastapi/fastapi | |
| ijson | 3.6.0 | BSD-3-Clause AND ISC | github.com/ICRAR/ijson | compiled wheel |
| inspect-ai | 0.3.282 | MIT | github.com/UKGovernmentBEIS/inspect_ai | pinned <0.4 (API churn) |
| jmespath | 1.1.0 | MIT | github.com/jmespath/jmespath.py | |
| jsonlines | 4.0.0 | BSD-3 (classifier; verify at release) | github.com/wbolster/jsonlines | |
| jsonpatch | 1.36 | BSD-3-Clause | github.com/stefankoegl/python-json-patch | |
| jsonpath-ng | 1.11.0 | Apache-2.0 | github.com/jsonpath-ng/jsonpath-ng | |
| jsonpointer | 3.4 | BSD-3 (classifier; verify at release) | github.com/stefankoegl/python-json-pointer | |
| jsonref | 1.1.0 | MIT | github.com/gazpachoking/jsonref | license from its repository (classifier absent) |
| linkify-it-py | 2.2.0 | MIT | github.com/tsutsu3/linkify-it-py | |
| mdit-py-plugins | 0.6.1 | MIT | github.com/executablebooks/mdit-py-plugins | |
| mmh3 | 5.3.1 | MIT | pypi.org/project/mmh3 | compiled wheel |
| nest-asyncio2 | 1.7.4 | BSD-3 (classifier; verify at release) | github.com/Chaoses-Ib/nest-asyncio2 | |
| pathlib-abc | 0.5.2 | PSF-2.0 | github.com/barneygale/pathlib-abc | |
| platformdirs | 4.13.5 | MIT | github.com/tox-dev/platformdirs | |
| psutil | 7.2.2 | BSD-3-Clause | github.com/giampaolo/psutil | license from its repository (classifier absent); compiled wheel |
| python-dotenv | 1.2.4 | BSD-3-Clause | github.com/theskumar/python-dotenv | license from its repository (classifier absent) |
| s3fs | 2026.6.0 | BSD-3 (classifier; verify at release) | github.com/fsspec/s3fs/ | |
| s3transfer | 0.19.3 | Apache-2.0 | github.com/boto/s3transfer | |
| semver | 3.1.0 | BSD License | pypi.org/project/semver | |
| shortuuid | 1.0.13 | BSD-3 (classifier; verify at release) | github.com/skorokithakis/shortuuid/ | |
| soupsieve | 3.0.3 | MIT | github.com/facelessuser/soupsieve | |
| textual | 6.2.1 | MIT | github.com/Textualize/textual | |
| tiktoken | 0.14.0 | MIT | github.com/openai/tiktoken | license from its repository (classifier absent); compiled wheel |
| universal-pathlib | 0.3.10 | MIT | github.com/fsspec/universal-pathlib | |
| wrapt | 2.5.1 | BSD-2-Clause | github.com/GrahamDumpleton/wrapt | compiled wheel |
| zipfile-zstd | 0.0.4 | MIT | github.com/taisei-project/python-zipfile-zstd | |
| zipp | 4.1.1 | MIT | github.com/jaraco/zipp | |
| zstandard | 0.25.0 | BSD-3-Clause | github.com/indygreg/python-zstandard | compiled wheel |
