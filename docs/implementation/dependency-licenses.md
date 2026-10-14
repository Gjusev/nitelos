# Dependency and license inventory (working record)

Source: installed distribution metadata (`importlib.metadata`, `License-Expression`/classifiers) from the
frozen `uv.lock`, recorded 2026-10-14 during NIT-001. This is a working record; NIT-015 performs the
final release audit of resolved wheels, bundled binaries and notices.

## Core runtime (wheel dependencies)

| Distribution | Version | License |
|---|---|---|
| pydantic | 2.14.1 | MIT |
| pydantic-core | 2.50.1 | MIT |
| annotated-types | 0.8.0 | MIT |
| typing-extensions | 4.16.0 | PSF-2.0 |
| typing-inspection | 0.4.4 | MIT |
| pillow | 12.3.0 | MIT-CMU (bundled image libraries: review wheel notices in NIT-015) |

## Development group (not shipped)

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
| pathspec | 1.1.1 | MPL-2.0 (classifier; build-time only, not redistributed) |
| trove-classifiers | 2026.9.21.13 | Apache-2.0 (classifier) |
| pygments | 2.21.0 | BSD-2-Clause |
| colorama | 0.4.6 | BSD (classifier; Windows only) |

Tooling: uv 0.9.21 (Windows dev host) and 0.13.1 (WSL Ubuntu), MIT OR Apache-2.0.
GitHub Actions pinned by SHA: actions/checkout v7.0.1 `3d3c42e5…`, astral-sh/setup-uv v10.3.0 `1c37ad07…`.
