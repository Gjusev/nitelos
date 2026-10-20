"""REL-04: the dependency/license inventory is machine-checked against the lock.

`docs/implementation/dependency-licenses.md` is asserted to match uv.lock
exactly where the lock can decide: direct core/eval/local membership (from the
nitelos package block), per-row version equality for every versioned row, and
completeness (every locked distribution appears somewhere in the inventory).
Ambiguous-license items must carry their release-action notes. If the lock
changes, this fails until the inventory is reconciled (the release rule).
"""

from __future__ import annotations

import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs" / "implementation" / "dependency-licenses.md"

# shipped closures as recorded in the inventory (AR-3 verified these against
# the resolved wheels; the lock pins the versions below)
CORE_CLOSURE = {
    "pydantic",
    "pydantic-core",
    "annotated-types",
    "typing-extensions",
    "typing-inspection",
    "pillow",
}
EVAL_CLOSURE = {"numpy", "scipy"}
OTEL_CLOSURE = {"opentelemetry-api", "typing-extensions"}
LOCAL_CLOSURE = {
    "torch",
    "transformers",
    "tokenizers",
    "safetensors",
    "huggingface-hub",
    "hf-xet",
    "filelock",
    "fsspec",
    "jinja2",
    "markupsafe",
    "mpmath",
    "sympy",
    "networkx",
    "regex",
    "tqdm",
    "pyyaml",
    "packaging",
    "typing-extensions",
    "torchvision",
    "num2words",
}
# rows that must carry a release-action / verify note (doc-12 honesty)
_FLAGGED = ("pillow", "numpy", "scipy", "torch", "torchvision", "num2words", "hf-xet", "regex", "pathspec")

DEEPEVAL_CLOSURE = {
    "aiohappyeyeballs",
    "aiohttp",
    "aiosignal",
    "anthropic",
    "attrs",
    "backoff",
    "certifi",
    "cffi",
    "charset-normalizer",
    "cryptography",
    "deepeval",
    "distro",
    "execnet",
    "frozenlist",
    "google-auth",
    "google-genai",
    "googleapis-common-protos",
    "grpcio",
    "httpcore",
    "httpx",
    "jiter",
    "monotonic",
    "multidict",
    "nest-asyncio",
    "ollama",
    "openai",
    "opentelemetry-exporter-otlp-common",
    "opentelemetry-exporter-otlp-proto-common",
    "opentelemetry-exporter-otlp-proto-grpc",
    "opentelemetry-proto",
    "portalocker",
    "posthog",
    "propcache",
    "protobuf",
    "pyasn1",
    "pyasn1-modules",
    "pycparser",
    "pytest-repeat",
    "pytest-rerunfailures",
    "pytest-xdist",
    "python-dateutil",
    "requests",
    "sentry-sdk",
    "six",
    "sniffio",
    "tabulate",
    "tenacity",
    "urllib3",
    "websockets",
    "wheel",
    "yarl",
}

MCP_CLOSURE = {
    "jsonschema",
    "jsonschema-specifications",
    "mcp",
    "mcp-types",
    "pyjwt",
    "python-multipart",
    "pywin32",
    "referencing",
    "rpds-py",
    "sse-starlette",
    "starlette",
    "uvicorn",
}


def _lock() -> tuple[dict[str, str], dict[str, list[str]]]:
    data = tomllib.loads((ROOT / "uv.lock").read_text(encoding="utf-8"))
    versions = {p["name"]: p["version"] for p in data["package"]}
    nitelos = next(p for p in data["package"] if p["name"] == "nitelos")
    direct: dict[str, list[str]] = {
        "core": [],
        "eval": [],
        "local": [],
        "otel": [],
        "deepeval": [],
        "mcp": [],
    }
    for dep in nitelos["metadata"]["requires-dist"]:
        group = "core"
        if "marker" in dep:
            if "extra == 'eval'" in dep["marker"]:
                group = "eval"
            elif "extra == 'local'" in dep["marker"]:
                group = "local"
            elif "extra == 'otel'" in dep["marker"]:
                group = "otel"
            elif "extra == 'deepeval'" in dep["marker"]:
                group = "deepeval"
            elif "extra == 'mcp'" in dep["marker"]:
                group = "mcp"
            else:
                raise AssertionError(
                    f"unrecognised extra marker for {dep['name']}: inventory test needs the group"
                )
        direct[group].append(dep["name"])
    return versions, direct


def _sections() -> dict[str, list[list[str]]]:
    """section header -> table rows (cells) parsed from the inventory."""
    sections: dict[str, list[list[str]]] = {}
    header = ""
    for line in DOC.read_text(encoding="utf-8").splitlines():
        if line.startswith("## "):
            header = line[3:].strip()
            sections.setdefault(header, [])
            continue
        if line.startswith("|") and header:
            cells = [cell.strip() for cell in line.strip("|").split("|")]
            if cells and not set(cells[0]) <= {"-", " ", ":"}:  # skip separator rows
                sections[header].append(cells)
    return sections


def _rows(sections: dict[str, list[list[str]]], needle: str) -> list[list[str]]:
    for header, rows in sections.items():
        if needle.lower() in header.lower():
            return rows
    raise AssertionError(f"no inventory section matches {needle!r}")


def test_lock_versions_match_every_versioned_row() -> None:
    versions, _ = _lock()
    matched = 0
    for rows in _sections().values():
        for cells in rows:
            name, version = cells[0].lower(), cells[1]
            if name in versions and version not in ("per lock", "—"):
                assert version == versions[name], f"{name}: doc says {version}, lock says {versions[name]}"
                matched += 1
    assert matched >= 40, f"only {matched} versioned rows matched — parser drift?"


def test_direct_dependencies_land_in_the_right_sections() -> None:
    _, direct = _lock()
    sections = _sections()
    core_rows = {cells[0].lower() for cells in _rows(sections, "Core runtime")}
    eval_rows = {cells[0].lower() for cells in _rows(sections, "extra `eval`")}
    local_rows = {cells[0].lower() for cells in _rows(sections, "extra `local`")}
    otel_rows = {cells[0].lower() for cells in _rows(sections, "extra `otel`")}
    deepeval_rows = {cells[0].lower() for cells in _rows(sections, "extra `deepeval`")}
    mcp_rows = {cells[0].lower() for cells in _rows(sections, "extra `mcp`")}
    assert set(direct["core"]) <= core_rows
    assert set(direct["eval"]) <= eval_rows
    assert set(direct["local"]) <= local_rows
    assert set(direct["otel"]) <= otel_rows
    assert set(direct["deepeval"]) <= deepeval_rows
    assert deepeval_rows >= DEEPEVAL_CLOSURE
    assert set(direct["mcp"]) <= mcp_rows
    assert mcp_rows >= MCP_CLOSURE
    # and the recorded closures are fully covered by their sections
    assert core_rows >= CORE_CLOSURE
    assert eval_rows >= EVAL_CLOSURE
    assert local_rows >= LOCAL_CLOSURE
    assert otel_rows >= OTEL_CLOSURE
    # closures are disjoint outside typing-extensions (shared core/local)
    assert not ((CORE_CLOSURE - {"typing-extensions"}) & (LOCAL_CLOSURE - {"typing-extensions"}))
    assert not (EVAL_CLOSURE & (CORE_CLOSURE | LOCAL_CLOSURE))


def test_every_locked_distribution_appears_in_the_inventory() -> None:
    versions, _ = _lock()
    listed: set[str] = set()
    for rows in _sections().values():
        for cells in rows:
            listed.update(part.strip().lower() for part in cells[0].split("/"))
    missing = sorted(name for name in versions if name != "nitelos" and name not in listed)
    assert not missing, f"locked but not inventoried: {missing}"


def test_no_empty_license_cells_and_flagged_rows_carry_notes() -> None:
    for rows in _sections().values():
        for cells in rows:
            assert len(cells) >= 3, cells
            assert cells[2].strip(), f"empty license cell for {cells[0]}"
    text = DOC.read_text(encoding="utf-8").lower()
    for name in _FLAGGED:
        assert f"| {name} |" in text, f"{name} missing from the inventory"
        # the note may live in-row or in a dedicated paragraph naming the item
        noted = any(
            name in block and ("release action" in block or "verify" in block) for block in text.split("\n\n")
        )
        assert noted, f"{name} carries no release-action/verify note"
