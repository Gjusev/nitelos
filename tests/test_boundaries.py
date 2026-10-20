"""BND-01..03: v0.2 extras isolation and the ADR-015 side-effect boundary (central, NIT-017)."""

from __future__ import annotations

import ast
import email
import re
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "nitelos"

# third-party packages behind extras (v0.1 + v0.2 candidates) and the extra-only subpackages
EXTRA_MODULES = (
    "numpy",
    "scipy",
    "torch",
    "transformers",
    "defusedxml",
    "httpx",
    "playwright",
    "inspect_ai",
    "langgraph",
    "deepeval",
    "mcp",
    "opentelemetry",
    "nitelos.collect",
    "nitelos.integrations",
)
# ADR-015: process and network modules are allowed only inside nitelos/collect/
SIDE_EFFECT_MODULES = (
    "subprocess",
    "socket",
    "ssl",
    "http",
    "urllib.request",
    "httpx",
    "requests",
    "aiohttp",
)
COLLECT_DIR = SRC / "collect"


def test_bnd01_core_wheel_requires_only_pydantic_and_pillow(tmp_path: Path) -> None:
    import os
    import shutil

    uv = os.environ.get("UV") or shutil.which("uv")
    if uv is None:
        pytest.fail("uv is required to build distributions")
    subprocess.run(
        [uv, "build", "--wheel", "--no-build-isolation", "--out-dir", str(tmp_path), str(ROOT)],
        check=True,
        capture_output=True,
    )
    (wheel,) = tmp_path.glob("nitelos-*.whl")
    with zipfile.ZipFile(wheel) as zf:
        (meta_name,) = [n for n in zf.namelist() if n.endswith(".dist-info/METADATA")]
        meta = email.message_from_bytes(zf.read(meta_name))
    unconditional = {
        re.match(r"[A-Za-z0-9._-]+", req).group(0).lower()  # type: ignore[union-attr]  # PEP 508 name
        for req in meta.get_all("Requires-Dist", [])
        if "extra ==" not in req
    }
    assert unconditional == {"pydantic", "pillow"}


def test_bnd02_import_nitelos_loads_no_extra_module() -> None:
    code = (
        "import sys\n"
        "import nitelos\n"
        f"loaded = [m for m in {EXTRA_MODULES!r} if m in sys.modules]\n"
        "assert not loaded, loaded\n"
    )
    proc = subprocess.run([sys.executable, "-c", code], check=False, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.add(node.module)
            names.update(f"{node.module}.{alias.name}" for alias in node.names)
    return names


def _is_side_effect(module: str) -> bool:
    return any(module == banned or module.startswith(banned + ".") for banned in SIDE_EFFECT_MODULES)


def test_bnd03_side_effect_imports_only_inside_collect() -> None:
    offenders = []
    for path in sorted(SRC.rglob("*.py")):
        if COLLECT_DIR in path.parents:
            continue
        hits = sorted(m for m in _imported_modules(path) if _is_side_effect(m))
        if hits:
            offenders.append(f"{path.relative_to(ROOT).as_posix()}: {hits}")
    assert not offenders, offenders


def test_bnd03_scanner_detects_forbidden_imports(tmp_path: Path) -> None:
    probe = tmp_path / "probe.py"
    probe.write_text("import subprocess\nfrom urllib.request import urlopen\nimport json\n", encoding="utf-8")
    hits = {m for m in _imported_modules(probe) if _is_side_effect(m)}
    assert hits == {"subprocess", "urllib.request", "urllib.request.urlopen"}
