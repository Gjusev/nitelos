"""REL-01..03: release conformance mechanics (NIT-015).

Installed-wheel conformance, sdist independence, extras isolation. The dist
fixtures build once per session; the venv fixtures install ONLY the built
artifact (plus pytest/hatchling pinned to the locked dev versions so the
installs resolve from the local uv cache, never an index drift). Test-time
dependencies come from the frozen lock (pytest 9.1.1, hatchling 1.32.4).
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples"
CONFORMANCE_SELECTION = (
    "test_contract.py",
    "test_evidence.py",
    "test_deterministic.py",
    "test_policy.py",
    "test_verifier.py",
    "test_lifecycle.py",
    "test_backend_contract.py",
    "test_trace.py",
)
FORBIDDEN_SUFFIXES = (".safetensors", ".bin", ".pt", ".pth", ".onnx", ".gguf", ".env", ".pem", ".key")
_LOCKED_TEST_DEPS = ("pytest==9.1.1", "pytest-asyncio==1.4.0")  # asyncio: the repo ini names its option


def _uv() -> str:
    uv = os.environ.get("UV") or shutil.which("uv")
    if uv is None:
        pytest.fail("uv is required for the release-conformance tests")
    return uv


def _venv_python(venv: Path) -> Path:
    return venv / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")


def _outside_env() -> dict[str, str]:
    # no PYTHONPATH: the child must resolve nitelos from its own site-packages
    return {key: value for key, value in os.environ.items() if key != "PYTHONPATH"}


def _run(venv_python: Path, args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(venv_python), *args], check=False, capture_output=True, text=True, cwd=cwd, env=_outside_env()
    )


@pytest.fixture(scope="module")
def built_dist(tmp_path_factory: pytest.TempPathFactory) -> Path:
    out = tmp_path_factory.mktemp("dist")
    subprocess.run(
        [_uv(), "build", "--no-build-isolation", "--out-dir", str(out), str(ROOT)],
        check=True,
        capture_output=True,
    )
    names = {p.name for p in out.iterdir()}
    assert "nitelos-0.1.0-py3-none-any.whl" in names
    assert "nitelos-0.1.0.tar.gz" in names
    assert names <= {"nitelos-0.1.0-py3-none-any.whl", "nitelos-0.1.0.tar.gz", ".gitignore"}
    return out


@pytest.fixture(scope="module")
def wheel_venv(built_dist: Path, tmp_path_factory: pytest.TempPathFactory) -> Path:
    wheel = built_dist / "nitelos-0.1.0-py3-none-any.whl"
    venv = tmp_path_factory.mktemp("wheel-venv")
    subprocess.run([_uv(), "venv", str(venv)], check=True, capture_output=True)
    vpython = _venv_python(venv)
    subprocess.run(
        [_uv(), "pip", "install", "--python", str(vpython), str(wheel), *_LOCKED_TEST_DEPS],
        check=True,
        capture_output=True,
    )
    return venv


@pytest.fixture(scope="module")
def sdist_venv(built_dist: Path, tmp_path_factory: pytest.TempPathFactory) -> Path:
    sdist = built_dist / "nitelos-0.1.0.tar.gz"
    venv = tmp_path_factory.mktemp("sdist-venv")
    subprocess.run([_uv(), "venv", str(venv)], check=True, capture_output=True)
    vpython = _venv_python(venv)
    # the build backend comes from the locked dev group (local uv cache);
    # --no-build-isolation keeps the sdist install offline after that
    subprocess.run(
        [_uv(), "pip", "install", "--python", str(vpython), "hatchling==1.32.4"],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        [_uv(), "pip", "install", "--python", str(vpython), "--no-build-isolation", str(sdist)],
        check=True,
        capture_output=True,
    )
    return venv


# --------------------------------------------------------------------------
# REL-01: the installed wheel runs the offline conformance selection + demos
# --------------------------------------------------------------------------


def test_rel01_conformance_selection_from_installed_wheel_outside_repo(
    wheel_venv: Path, tmp_path: Path
) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    vpython = _venv_python(wheel_venv)
    # nitelos must resolve from the venv's site-packages, never a checkout
    where = _run(vpython, ["-c", "import nitelos; print(nitelos.__file__)"], outside)
    assert where.returncode == 0, where.stderr
    assert str(wheel_venv) in where.stdout, where.stdout
    # the suite's own conftest denies network access for every test (SEC-04)
    selection = [str(ROOT / "tests" / name) for name in CONFORMANCE_SELECTION]
    proc = _run(vpython, ["-m", "pytest", "-q", "-p", "no:cacheprovider", *selection], outside)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert " passed" in proc.stdout


def test_rel01_examples_run_from_installed_wheel(wheel_venv: Path, tmp_path: Path) -> None:
    vpython = _venv_python(wheel_venv)
    outside = tmp_path / "outside"
    outside.mkdir()
    for name in ("quickstart.py", "demo_incomplete_form.py"):
        source = EXAMPLES / name
        assert source.exists(), name
        script = outside / name
        script.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
        proc = _run(
            vpython,
            [
                "-c",
                "import socket\n"
                "def deny(*a, **k): raise OSError('network disabled')\n"
                "socket.socket.connect = deny\n"
                f"exec(open({str(script)!r}, encoding='utf-8').read())",
            ],
            outside,
        )
        assert proc.returncode == 0, f"{name}: {proc.stderr}"
        assert proc.stdout.strip(), name


# --------------------------------------------------------------------------
# REL-02: the sdist is independently complete and installable
# --------------------------------------------------------------------------


def test_rel02_sdist_contents(built_dist: Path) -> None:
    sdist = built_dist / "nitelos-0.1.0.tar.gz"
    with tarfile.open(sdist) as tf:
        names = tf.getnames()
    # fixtures ship (the smoke set is part of the distribution)
    assert any("/tests/fixtures/smoke/smoke-01.png" in name for name in names)
    assert any("/tests/fixtures/smoke/cases.json" in name for name in names)
    assert any(name.endswith("/src/nitelos/py.typed") for name in names)
    # nothing that must not ship
    assert not [n for n in names if n.lower().endswith(FORBIDDEN_SUFFIXES)]
    assert not [n for n in names if "/.venv/" in n or "/models/" in n]
    assert not [n for n in names if "/benchmarks/" in n or "/reports/" in n]


def test_rel02_sdist_installs_and_imports_in_fresh_venv(sdist_venv: Path, tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    vpython = _venv_python(sdist_venv)
    proc = _run(
        vpython,
        [
            "-c",
            "import socket, sys\n"
            "def deny(*a, **k): raise OSError('network disabled')\n"
            "socket.socket.connect = deny\n"
            "import nitelos\n"
            "assert nitelos.__version__ == '0.1.0'\n"
            f"assert nitelos.__file__.startswith({str(sdist_venv)!r})\n"
            f"exec(open({str(EXAMPLES / 'quickstart.py')!r}, encoding='utf-8').read())",
        ],
        outside,
    )
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip()


# --------------------------------------------------------------------------
# REL-03: extras isolation
# --------------------------------------------------------------------------


def test_rel03_core_import_light_with_eval_extra_installed() -> None:
    """This environment carries the eval extra (numpy/scipy installed) yet a
    bare `import nitelos` pulls none of it."""
    code = (
        "import sys\n"
        "import nitelos\n"
        "heavy = [m for m in ('numpy', 'scipy', 'torch', 'transformers') if m in sys.modules]\n"
        "assert not heavy, heavy\n"
    )
    proc = subprocess.run(
        [sys.executable, "-c", code], check=False, capture_output=True, text=True, env=_outside_env()
    )
    assert proc.returncode == 0, proc.stderr


def test_rel03_core_import_light_with_local_extra_installed() -> None:
    """Gated: run only where a local-extra venv is provisioned (torch etc.).
    Point NITELOS_LOCAL_EXTRA_VENV at its root; the release workflow's audit
    job provisions it (uv sync --extra local --extra eval)."""
    venv = os.environ.get("NITELOS_LOCAL_EXTRA_VENV")
    if not venv:
        pytest.skip("NITELOS_LOCAL_EXTRA_VENV not set (local-extra venv not provisioned here)")
    vpython = _venv_python(Path(venv))
    assert vpython.exists(), f"{vpython} does not exist"
    code = (
        "import sys\n"
        "import torch, transformers, numpy, scipy\n"  # the extra really is installed
        "for m in ('torch', 'transformers', 'numpy', 'scipy'):\n"
        "    sys.modules.pop(m, None)\n"
        "import nitelos\n"
        "heavy = [m for m in ('numpy', 'scipy', 'torch', 'transformers') if m in sys.modules]\n"
        "assert not heavy, heavy\n"
    )
    proc = subprocess.run(
        [str(vpython), "-c", code], check=False, capture_output=True, text=True, env=_outside_env()
    )
    assert proc.returncode == 0, proc.stderr


def test_rel03_local_extra_absent_actionable_error(wheel_venv: Path, tmp_path: Path) -> None:
    """Without the local extra the adapter fails with the actionable hint
    (DEPENDENCY_MISSING + the install line), never a bare traceback."""
    outside = tmp_path / "outside"
    outside.mkdir()
    vpython = _venv_python(wheel_venv)
    proc = _run(
        vpython,
        [
            "-c",
            "from nitelos.backends.smolvlm import _import_torch\n"
            "try:\n"
            "    _import_torch()\n"
            "except Exception as error:\n"
            "    print(type(error).__name__, getattr(error, 'issue', None) and error.issue.code, error)\n"
            "else:\n"
            "    raise SystemExit('torch unexpectedly importable in the wheel venv')\n",
        ],
        outside,
    )
    assert proc.returncode == 0, proc.stderr
    assert "DEPENDENCY_MISSING" in proc.stdout, proc.stdout
    assert "local" in proc.stdout.lower(), proc.stdout


def test_rel03_cli_smolvlm_without_model_dir_is_actionable(wheel_venv: Path, tmp_path: Path) -> None:
    from test_evaluation import build_mini_benchmark

    bench = build_mini_benchmark(tmp_path / "bench")
    vpython = _venv_python(wheel_venv)
    proc = _run(
        vpython,
        [
            "-m",
            "nitelos.evaluation",
            "run",
            "--manifest",
            str(bench.manifest_path),
            "--artifacts",
            str(bench.root),
            "--output",
            str(tmp_path / "out"),
            "--backend",
            "smolvlm",
        ],
        tmp_path,
    )
    assert proc.returncode == 2, proc.stdout + proc.stderr
    assert "--model-dir" in (proc.stderr + proc.stdout)
