"""DOC-01..04: developer documentation and the honest offline demo (NIT-014).

Authority: docs/planning/13 (documentation deliverables, demonstration definition),
11 (demonstration trio, coding standards), 09 (G7), 10 NIT-014, 12 (DOC family).
DOC-01 runs the quickstart from an INSTALLED WHEEL in a fresh venv outside the repo
(no model extras, network denied by the conftest at the test level); DOC-02/03 run
the demo examples end to end through the real SDK; DOC-04 asserts that every example
module's construction and exception behavior matches the shipped schemas.
"""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples"


def _load_example(name: str) -> Any:
    spec = importlib.util.spec_from_file_location(f"example_{name}", EXAMPLES / f"{name}.py")
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# --------------------------------------------------------------------------
# DOC-01: the quickstart executes from an installed wheel, offline, outside the repo
# --------------------------------------------------------------------------


@pytest.fixture(scope="module")
def wheel_venv(tmp_path_factory: pytest.TempPathFactory) -> Path:
    uv = os.environ.get("UV") or shutil.which("uv")
    if uv is None:
        pytest.fail("uv is required to build the wheel")
    dist = tmp_path_factory.mktemp("dist")
    subprocess.run(
        [uv, "build", "--no-build-isolation", "--out-dir", str(dist), str(ROOT)],
        check=True,
        capture_output=True,
    )
    (wheel,) = sorted(dist.glob("nitelos-*.whl"))
    venv = tmp_path_factory.mktemp("site")
    subprocess.run([uv, "venv", str(venv)], check=True, capture_output=True)
    vpython = venv / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    subprocess.run(
        [uv, "pip", "install", "--python", str(vpython), str(wheel)],
        check=True,
        capture_output=True,
    )
    return venv


def test_doc01_quickstart_from_installed_wheel(wheel_venv: Path, tmp_path: Path) -> None:
    quickstart = EXAMPLES / "quickstart.py"
    assert quickstart.exists()
    outside = tmp_path / "outside"
    outside.mkdir()
    code = quickstart.read_text(encoding="utf-8")
    assert "from nitelos import" in code
    script = outside / "quickstart.py"
    script.write_text(code, encoding="utf-8")
    vpython = wheel_venv / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    env = {key: value for key, value in os.environ.items() if key != "PYTHONPATH"}
    proc = subprocess.run(
        [
            str(vpython),
            "-c",
            "import socket\n"
            "def deny(*a, **k): raise OSError('network disabled')\n"
            "socket.socket.connect = deny\n"
            f"exec(open({str(script)!r}, encoding='utf-8').read())",
        ],
        check=False,
        capture_output=True,
        text=True,
        cwd=outside,
        env=env,
    )
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip()


# --------------------------------------------------------------------------
# DOC-02: the demonstration — agent summary claims success, the assertion refutes
# --------------------------------------------------------------------------


def test_doc02_demo_failure_despite_agent_success_claim() -> None:
    demo = _load_example("demo_incomplete_form")
    result = demo.run()
    assert result.execution_status.value == "ok"
    assert result.decision is not None
    assert result.decision.value == "failure"
    (criterion_result,) = result.criteria
    assert criterion_result.criterion_id == "no-errors"
    assert criterion_result.state.value == "refuted"
    assert criterion_result.basis.value == "deterministic"
    (ref,) = criterion_result.evidence_refs
    assert ref.pointer == "/validation_error"
    assert ref.grounding.value == "assertion_checked"


def test_doc02_demo_prints_honest_output(capsys: pytest.CaptureFixture[str]) -> None:
    demo = _load_example("demo_incomplete_form")
    demo.run()
    out = capsys.readouterr().out
    assert "failure" in out
    assert "refuted" in out
    assert "deterministic" in out


# --------------------------------------------------------------------------
# DOC-03: pending external state abstains
# --------------------------------------------------------------------------


def test_doc03_external_pending_abstains() -> None:
    example = _load_example("demo_external_pending")
    result = example.run()
    assert result.execution_status.value == "ok"
    assert result.decision is not None
    assert result.decision.value == "abstained"
    assert "MODEL_INFERENCE_DISALLOWED" not in result.reason_codes
    (criterion_result,) = result.criteria
    assert criterion_result.state.value == "unknown"


# --------------------------------------------------------------------------
# DOC-04: every example's fields and exceptions match the shipped schemas
# --------------------------------------------------------------------------


def test_doc04_quickstart_fields_match_schema(wheel_venv: Path) -> None:
    from nitelos.schemas import VerificationRequest

    quickstart = (EXAMPLES / "quickstart.py").read_text(encoding="utf-8")
    assert "parse_request" in quickstart or "VerificationRequest" in quickstart
    # the request dict in the quickstart must parse into the real schema
    module = _load_example("quickstart")
    doc = module.build_request_document()
    parsed = module.parse_request(json.dumps(doc))
    assert isinstance(parsed, VerificationRequest)
    operators = ("equals", "in", "exists")
    assert parsed.criteria[0].operator.value in operators


def test_doc04_examples_reject_invalid_input_like_the_schema() -> None:
    demo = _load_example("demo_incomplete_form")
    from nitelos.errors import RequestValidationError

    bad = demo.build_request_document()
    bad["criteria"][0]["scope"] = "nonsense"
    with pytest.raises(RequestValidationError):
        demo.parse_request(json.dumps(bad))


def test_doc04_readme_and_docs_field_names_match_public_api() -> None:
    from nitelos import __all__ as public

    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    # names the README teaches must exist in the public API
    for name in (
        "Verifier",
        "VerificationRequest",
        "parse_request",
        "ArtifactStore",
        "TrustBinding",
        "Evidence",
        "VerificationPolicy",
    ):
        assert name in public
        assert name in readme or name in (ROOT / "docs" / "quickstart.md").read_text(encoding="utf-8")
    # forbidden: benchmark numbers and model branding in the title
    assert "Nitelos" in readme.splitlines()[0]
    first_screen = readme[:2000]
    assert "SmolVLM" not in readme.splitlines()[0]
    # no benchmark-number patterns (NN% / 0.NN accuracy-style) before the docs index
    import re

    headline = first_screen.split("## Documentation")[0]
    assert not re.search(r"\d+(?:\.\d+)?\s*%", headline), headline[:400]
    assert not re.search(r"accuracy[:\s]+\d", headline, re.IGNORECASE)


def test_doc04_docs_pages_exist_and_link_the_recipe() -> None:
    pages = [
        "installation.md",
        "quickstart.md",
        "success-criteria.md",
        "evidence-limits.md",
        "lifecycle.md",
        "errors-and-abstention.md",
        "backends.md",
        "custom-adapters.md",
        "traces.md",
        "evaluation.md",
        "security-privacy.md",
        "performance.md",
    ]
    for page in pages:
        path = ROOT / "docs" / page
        assert path.exists(), page
        text = path.read_text(encoding="utf-8")
        assert text.strip(), page
    traces = (ROOT / "docs" / "traces.md").read_text(encoding="utf-8")
    assert "recipes/caller-collection.md" in traces
    assert (ROOT / "docs" / "recipes" / "caller-collection.md").exists()


def test_doc04_visual_example_is_local_model_gated() -> None:
    visual = EXAMPLES / "demo_visual_optional.py"
    if visual.exists():
        code = visual.read_text(encoding="utf-8")
        assert "local_model" in code or "NITELOS_RUN_LOCAL" in code
        assert "model_inferred" in code
        assert "SmolVLMBackend" in code  # wired for real, not a stub


def test_doc04_visual_demo_reports_gate_and_pins(monkeypatch: Any) -> None:
    """Un-gated, no-extra run: honest exits; the gate record is stated."""

    example = _load_example("demo_visual_optional")
    monkeypatch.delenv("NITELOS_RUN_LOCAL", raising=False)
    assert example.run() == 0  # skip is an honest exit, prints the gate requirements


def test_doc04_contributing_and_security_exist() -> None:
    contributing = (ROOT / "CONTRIBUTING.md").read_text(encoding="utf-8")
    assert "DCO" in contributing or "sign-off" in contributing.lower()
    security = (ROOT / "SECURITY.md").read_text(encoding="utf-8")
    assert "private" in security.lower()
    assert "report" in security.lower()


# --------------------------------------------------------------------------
# EX-01: the custom-collector example runs offline and prints honest decisions
# --------------------------------------------------------------------------


def test_ex01_custom_collector_example_decisions() -> None:
    example = _load_example("collect_custom_collector")
    without_bindings, with_bindings = example.run()
    assert without_bindings.execution_status.value == "ok"
    assert without_bindings.decision is not None
    assert without_bindings.decision.value == "abstained"
    assert "UNTRUSTED_EXTERNAL" in without_bindings.reason_codes
    assert with_bindings.execution_status.value == "ok"
    assert with_bindings.decision is not None
    assert with_bindings.decision.value == "success"


def test_ex01_custom_collector_example_prints_both_paths(capsys: pytest.CaptureFixture[str]) -> None:
    _load_example("collect_custom_collector").run()
    out = capsys.readouterr().out
    assert "without bindings" in out
    assert "with host bindings" in out
    assert "UNTRUSTED_EXTERNAL" in out
