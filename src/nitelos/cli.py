"""The ``nitelos`` debug CLI (plan section F1, NIT-017; ADR-014).

One subcommand today: ``nitelos collect <kind> --config FILE --out FILE``
(or, from a checkout before the console script is installed,
``python -m nitelos.cli collect …``). Exit codes: 0 collected; 2 bad args,
unknown kind, invalid config, or an existing ``--out`` (opened with mode "x"
so even a concurrent creator cannot be overwritten); 3 collection error, with
the COLLECTOR_* code printed. Stdout carries a safe summary (counts, codes)
only; the evidence (v0.1 wire form), provenance and error go to ``--out`` as
JSON.

The kind table is fixed in code — no entry-point scan (doc 04). It ships
EMPTY: real kinds (git, junit) arrive with NIT-018/019. Each entry maps a kind
to ``"module:attribute"``, imported lazily so a missing extra never breaks an
unrelated invocation; an unloadable module maps to COLLECTOR_UNAVAILABLE
(ADR-014 finding 2). Configs validate through the collector's own
``config_model`` in JSON mode, so kind-specific subclass fields and JSON
shapes (arrays for ``redact_pointers``) work.
"""

from __future__ import annotations

import argparse
import importlib
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

KIND_TARGETS: dict[str, str] = {
    "junit": "nitelos.collect.test_results:COLLECTOR",  # NIT-019
}  # NIT-018 adds "git"


def _error_document(code: Any, message: str) -> dict[str, Any]:
    return {
        "collector": {"id": "", "version": ""},
        "evidence": [],
        "provenance": [],
        "error": {"code": code.value, "safe_message": message},
    }


def _write_out_exclusive(path: Path, document: dict[str, Any]) -> bool:
    """Create ``path`` (never overwrite, even under a race); False on failure."""
    try:
        with path.open("x", encoding="utf-8") as sink:
            sink.write(json.dumps(document, indent=2, sort_keys=True) + "\n")
    except OSError:
        print(f"cannot write output file: {path}", file=sys.stderr)
        return False
    return True


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI; returns the process exit code (see the module docstring)."""
    parser = argparse.ArgumentParser(prog="nitelos", description="Nitelos debug CLI")
    sub = parser.add_subparsers(dest="command", required=True)
    collect = sub.add_parser("collect", help="run one evidence collector for debugging")
    collect.add_argument("kind", help="collector kind (see docs/collectors.md)")
    collect.add_argument("--config", required=True, type=Path, help="collector config JSON")
    collect.add_argument("--out", required=True, type=Path, help="output JSON (must not exist)")
    args = parser.parse_args(argv)
    if args.out.exists():
        print(f"refusing to overwrite: file exists: {args.out}", file=sys.stderr)
        return 2
    target = KIND_TARGETS.get(args.kind)
    if target is None:
        known = ", ".join(sorted(KIND_TARGETS)) or "none yet"
        print(f"unknown kind {args.kind!r} (known kinds: {known})", file=sys.stderr)
        return 2

    from pydantic import ValidationError  # noqa: PLC0415 - lazy: only needed on the collect path

    from nitelos.collect import (  # noqa: PLC0415 - lazy: keep CLI startup light
        CollectorErrorCode,
        CollectorErrorInfo,
        run_collector,
    )

    module_name, _, attribute = target.partition(":")
    try:
        collector = getattr(importlib.import_module(module_name), attribute)
    except (ImportError, AttributeError):
        unavailable = CollectorErrorInfo(code=CollectorErrorCode.UNAVAILABLE)
        if not _write_out_exclusive(args.out, _error_document(unavailable.code, unavailable.safe_message)):
            return 2
        print(f"collection failed: {unavailable.code.value}")
        return 3
    try:
        config = collector.config_model.model_validate_json(args.config.read_text(encoding="utf-8"))
    except (OSError, ValidationError, ValueError, AttributeError):
        print("invalid collector config", file=sys.stderr)
        return 2

    result = run_collector(collector, config)
    document: dict[str, Any] = {
        "collector": {"id": result.collector_id, "version": result.collector_version},
        "evidence": [item.model_dump(mode="json") for item in result.evidence],
        "provenance": [record.model_dump(mode="json") for record in result.provenance],
        "error": None
        if result.error is None
        else {"code": result.error.code.value, "safe_message": result.error.safe_message},
    }
    if not _write_out_exclusive(args.out, document):
        return 2
    if result.error is not None:
        print(f"collection failed: {result.error.code.value}")
        return 3
    print(f"collected {len(result.evidence)} evidence item(s) -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
