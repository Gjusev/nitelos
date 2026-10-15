"""NIT-013 part B: per-family tables and the over-support analysis.

Reads one or more validated run directories and emits a per-family breakdown
(decisions, model invocations, latency) plus, when the sibling oracle files are
available through the benchmark tree, the label-agreement column used to carry
the over-support observation through the report. Pure reporting: no tuning, no
re-running, no rewriting of run records.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


def load_rows(run_dir: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in (run_dir / "cases.jsonl").read_text(encoding="utf-8").splitlines()]


def family_table(run_dir: Path, oracles_dir: Path | None = None) -> dict[str, Any]:
    rows = load_rows(run_dir)
    run = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    families: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "cases": 0,
            "ok": 0,
            "errors": 0,
            "decisions": Counter(),
            "model_invoked": 0,
            "duration_ms_total": 0.0,
        }
    )
    oracles: dict[str, Any] = {}
    if oracles_dir is not None:
        for path in sorted(oracles_dir.glob("*.json")):
            record = json.loads(path.read_text(encoding="utf-8"))
            oracles[record["case_id"]] = record
    agreement = {"match": 0, "mismatch": 0, "no_oracle": 0}
    view = run["evidence_view"]
    for row in rows:
        family = families[row["primary_scenario"]]
        family["cases"] += 1
        if row["execution_status"] == "ok":
            family["ok"] += 1
            family["decisions"][row["decision"]] += 1
        else:
            family["errors"] += 1
        if row["model_invoked"]:
            family["model_invoked"] += 1
        family["duration_ms_total"] += row["duration_ms"]
        oracle = oracles.get(row["case_id"])
        if oracle is None:
            agreement["no_oracle"] += 1
            continue
        expected = oracle["expected"][view]["decision"]
        actual = row["decision"] if row["execution_status"] == "ok" else None
        if actual == expected:
            agreement["match"] += 1
        else:
            agreement["mismatch"] += 1
    table = {}
    for family in sorted(families):
        entry = families[family]
        table[family] = {
            "cases": entry["cases"],
            "ok": entry["ok"],
            "errors": entry["errors"],
            "decisions": dict(entry["decisions"]),
            "model_invoked": entry["model_invoked"],
            "mean_duration_ms": round(entry["duration_ms_total"] / entry["cases"], 1),
        }
    return {
        "run_dir": run_dir.name,
        "run_id": run["run_id"],
        "evidence_view": view,
        "backend_policy": run.get("policy_hash"),
        "families": table,
        "label_agreement_vs_dev_oracles": agreement,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dir")
    parser.add_argument("--oracles", default=None, help="benchmark oracle dir for the agreement column")
    parser.add_argument("--output", default=None)
    args = parser.parse_args(argv)
    oracles_dir = Path(args.oracles) if args.oracles else None
    report = family_table(Path(args.run_dir), oracles_dir)
    text = json.dumps(report, indent=2) + "\n"
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
        print(f"written: {args.output}")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
