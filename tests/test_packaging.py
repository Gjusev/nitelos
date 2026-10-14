"""PKG-01..03: packaging, import hygiene and supported-Python metadata (NIT-001)."""

from __future__ import annotations

import email
import os
import shutil
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
HEAVY_MODULES = ("torch", "transformers", "scipy", "numpy", "playwright", "httpx")
FORBIDDEN_SUFFIXES = (".safetensors", ".bin", ".pt", ".pth", ".onnx", ".gguf", ".env", ".pem", ".key")


@pytest.fixture(scope="session")
def dist_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    uv = os.environ.get("UV") or shutil.which("uv")
    if uv is None:
        pytest.fail("uv is required to build distributions")
    out = tmp_path_factory.mktemp("dist")
    subprocess.run(
        [uv, "build", "--no-build-isolation", "--out-dir", str(out), str(ROOT)],
        check=True,
        capture_output=True,
    )
    return out


def _one(dist: Path, pattern: str) -> Path:
    found = sorted(dist.glob(pattern))
    assert len(found) == 1, found
    return found[0]


def test_import_has_no_side_effects_and_no_heavy_imports() -> None:
    code = (
        "import logging, socket, sys\n"
        "def deny(*a, **k): raise OSError('network disabled')\n"
        "socket.socket.connect = deny\n"
        "before = list(logging.getLogger().handlers)\n"
        "import nitelos\n"
        "assert nitelos.__version__ == '0.1.0', nitelos.__version__\n"
        "assert logging.getLogger().handlers == before\n"
        "assert logging.getLogger('nitelos').handlers == []\n"
        f"heavy = [m for m in {HEAVY_MODULES!r} if m in sys.modules]\n"
        "assert not heavy, heavy\n"
    )
    proc = subprocess.run([sys.executable, "-c", code], check=False, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout == ""


def test_pkg01_built_wheel_imports_without_extras_or_network(dist_dir: Path, tmp_path: Path) -> None:
    wheel = _one(dist_dir, "nitelos-*.whl")
    target = tmp_path / "site"
    with zipfile.ZipFile(wheel) as zf:
        zf.extractall(target)  # noqa: S202 - our own freshly built wheel
    code = (
        "import socket, sys\n"
        "def deny(*a, **k): raise OSError('network disabled')\n"
        "socket.socket.connect = deny\n"
        "import nitelos\n"
        f"assert nitelos.__file__.startswith({str(target)!r}), nitelos.__file__\n"
        "print(nitelos.__version__)\n"
    )
    env = {"PYTHONPATH": str(target), "SYSTEMROOT": _systemroot()}
    proc = subprocess.run(
        [sys.executable, "-c", code], check=False, capture_output=True, text=True, env=env, cwd=tmp_path
    )
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == "0.1.0"


def test_pkg02_wheel_contains_py_typed_and_no_weights_or_secrets(dist_dir: Path) -> None:
    wheel = _one(dist_dir, "nitelos-*.whl")
    with zipfile.ZipFile(wheel) as zf:
        names = zf.namelist()
    assert "nitelos/py.typed" in names
    assert "nitelos/__init__.py" in names
    assert not [n for n in names if n.lower().endswith(FORBIDDEN_SUFFIXES)]
    assert not [n for n in names if n.startswith(("tests/", "docs/", "benchmarks/", "reports/"))]


def test_pkg02_sdist_contains_no_weights_or_secrets(dist_dir: Path) -> None:
    sdist = _one(dist_dir, "nitelos-*.tar.gz")
    with tarfile.open(sdist) as tf:
        names = tf.getnames()
    assert any(n.endswith("src/nitelos/py.typed") for n in names)
    assert not [n for n in names if n.lower().endswith(FORBIDDEN_SUFFIXES)]
    assert not [n for n in names if "/.venv/" in n or "/models/" in n]


def test_pkg03_supported_python_metadata(dist_dir: Path) -> None:
    wheel = _one(dist_dir, "nitelos-*.whl")
    with zipfile.ZipFile(wheel) as zf:
        meta_name = next(n for n in zf.namelist() if n.endswith(".dist-info/METADATA"))
        meta = email.message_from_bytes(zf.read(meta_name))
    assert meta["Requires-Python"] == "<3.14,>=3.12"
    classifiers = meta.get_all("Classifier") or []
    assert "Programming Language :: Python :: 3.12" in classifiers
    assert "Programming Language :: Python :: 3.13" in classifiers
    assert meta["License-Expression"] == "Apache-2.0"
    assert sys.version_info[:2] in ((3, 12), (3, 13))


def _systemroot() -> str:
    return os.environ.get("SYSTEMROOT", "")
