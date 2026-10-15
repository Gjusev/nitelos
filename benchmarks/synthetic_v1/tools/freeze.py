"""Freeze procedure for nitelos-synthetic-v1 (NIT-010).

The final freeze requires a completed sign-off on every final-test oracle:
annotation_status "approved" (a future human audit) or "agent_audited_2026-10-15"
(ADR-013: two independent AI reviewers plus orchestrator adjudication — recorded
as agent identities in the annotators list, with the binding no-human-audit label
on downstream artifacts), a non-empty annotators list and a non-null sign_off.
While any record is pending_human_review the final freeze is refused (exit 1) —
agents cannot satisfy the gate by assertion alone. ``--provisional`` computes and
writes a clearly labelled provisional content digest without any freeze claim.
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path
from typing import Any

EXCLUDED_NAMES = {"freeze.sha256", "freeze.sha256.provisional"}
_SEALED_STATUSES = ("approved", "agent_audited_2026-10-15")


def _pending_final_test(bench_dir: Path) -> list[str]:
    pending = []
    for path in sorted((bench_dir / "oracle").glob("*.json")):
        record: dict[str, Any] = __import__("json").loads(path.read_text(encoding="utf-8"))
        if record.get("split") != "test":
            continue
        if (
            record.get("annotation_status") not in _SEALED_STATUSES
            or not record.get("annotators")
            or record.get("sign_off") is None
        ):
            pending.append(record["case_id"])
    return pending


def _tree_digest(bench_dir: Path) -> str:
    lines = []
    for path in sorted(p for p in bench_dir.rglob("*") if p.is_file() and p.name not in EXCLUDED_NAMES):
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        lines.append(digest)
    return hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()


def main(argv: list[str] | None = None) -> int:
    args = [a for a in (sys.argv[1:] if argv is None else argv) if not a.startswith("--")]
    bench_dir = Path(args[0]) if args else Path(__file__).resolve().parents[1]
    provisional = "--provisional" in (sys.argv[1:] if argv is None else argv)
    pending = _pending_final_test(bench_dir)
    if provisional:
        digest = _tree_digest(bench_dir)
        (bench_dir / "freeze.sha256.provisional").write_text(
            f"provisional (pre-freeze, human annotation pending)\n{digest}\n", encoding="utf-8"
        )
        print(f"provisional digest written ({len(pending)} final-test records still pending)")
        return 0
    if pending:
        print(
            f"REFUSED: {len(pending)} final-test oracles are pending_human_review; "
            "the freeze needs the human gate"
        )
        return 1
    digest = _tree_digest(bench_dir)
    (bench_dir / "freeze.sha256").write_text(f"final\n{digest}\n", encoding="utf-8")
    print(f"freeze recorded: {digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
