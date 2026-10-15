"""Oracle derivation for nitelos-synthetic-v1 (NIT-010) — reads state ONLY.

Independently reviewable mapping from each case's fixture state record to its oracle
labels (outcome_truth, evidence_sufficiency, per-view expected decision and reason
codes, rationale). This script never opens an image and never reads a caption: it
consumes the ``state`` field of the per-case oracle files written by the generator.
The human audit (review packets) verifies that renders match state; the deterministic
dry run cross-checks the assertion-view expectations against the real policy.

Reason-code tables mirror doc 05 aggregation: the result-level aggregate code first,
then criterion reasons in criterion order, deduplicated.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

_SUCCESS = ("success", ["ALL_CRITERIA_SUPPORTED"])
_FAILURE = ("failure", ["CRITERION_REFUTED"])


def _abstained(*codes: str) -> tuple[str, list[str]]:
    return "abstained", ["INSUFFICIENT_EVIDENCE", *codes]


def _s04(state: dict[str, Any]) -> dict[str, Any]:
    if state["ledger"] == "failed":
        return _outcome("failure", "sufficient", _FAILURE, _FAILURE)
    return _outcome(
        "failure",
        "insufficient",
        _abstained("MISSING_EVIDENCE"),
        _abstained("MISSING_EVIDENCE"),
        "ledger absent from the evidence view; a known failure with insufficient evidence abstains",
    )


def _s06(state: dict[str, Any]) -> dict[str, Any]:
    return _outcome(
        "failure",
        "sufficient",
        _FAILURE,
        _abstained("MISSING_EVIDENCE"),
        "database observation refutes completion; the image-only view withholds it and abstains",
    )


def _s07(state: dict[str, Any]) -> dict[str, Any]:
    if state["variant"] == "subject_mismatch":
        return _outcome(
            "failure",
            "insufficient",
            _abstained("SUBJECT_MISMATCH"),
            _abstained("SUBJECT_MISMATCH"),
            "evidence names a different record than the criterion subject; unknown, not failure",
        )
    return _outcome("failure", "sufficient", _FAILURE, _FAILURE)


def _s08(state: dict[str, Any]) -> dict[str, Any]:
    truth = state["underlying"]
    return _outcome(
        truth,
        "insufficient",
        _abstained("MISSING_EVIDENCE"),
        _abstained("MISSING_EVIDENCE"),
        "empty evidence view; truth is known to the fixture but not established by evidence",
    )


def _s12(state: dict[str, Any]) -> dict[str, Any]:
    return _outcome(
        state["underlying"],
        "insufficient",
        _abstained("MISSING_VALUE"),
        _abstained("MODEL_UNCERTAIN"),
        "the decisive detail is unreadable/absent from the evidence; unknown expectation",
    )


def _s13(state: dict[str, Any]) -> dict[str, Any]:
    if state["status_line"] == "passed":
        return _outcome("success", "sufficient", _SUCCESS, _SUCCESS)
    return _outcome("failure", "sufficient", _FAILURE, _FAILURE)


def _s15(state: dict[str, Any]) -> dict[str, Any]:
    if state["final_predicate"] == "absent":
        return _outcome(
            "unknown",
            "insufficient",
            _abstained("MISSING_EVIDENCE"),
            _abstained("MISSING_EVIDENCE"),
            "history cannot substitute for the missing final predicate",
        )
    return _outcome("failure", "sufficient", _FAILURE, _FAILURE)


def _outcome(
    truth: str,
    sufficiency: str,
    assertion: tuple[str, list[str]],
    visual: tuple[str, list[str]],
    rationale: str = "",
) -> dict[str, Any]:
    return {
        "outcome_truth": truth,
        "evidence_sufficiency": sufficiency,
        "expected": {
            "assertion": {"decision": assertion[0], "reason_codes": assertion[1]},
            "visual": {"decision": visual[0], "reason_codes": visual[1]},
        },
        "rationale": rationale,
    }


_SIMPLE: dict[str, tuple[tuple[str, list[str]], tuple[str, list[str]]]] = {
    "S01": (_SUCCESS, _SUCCESS),
    "S02": (_FAILURE, _FAILURE),
    "S03": (_FAILURE, _FAILURE),
    "S05": (_abstained("PENDING_STATE"), _abstained("PENDING_STATE")),
    "S09": (_abstained("CONTRADICTORY_EVIDENCE"), _abstained("CONTRADICTORY_EVIDENCE")),
    "S10": (_FAILURE, _FAILURE),
    "S11": (_SUCCESS, _SUCCESS),
    "S14": (_FAILURE, _FAILURE),
}

_SIMPLE_RATIONALES = {
    "S01": "final completion state confirmed by interface and bound backend record",
    "S02": "explicit final failure in interface and backend; tool completion cannot flip it",
    "S03": "required field empty with a visible validation error refutes the no-error criterion",
    "S05": "pending phase is explicitly nonfinal; unknown, never failure",
    "S09": "two final snapshots contradict on one criterion; unknown, never source-count",
    "S10": "behavior completed but the required final state failed; behavior cannot override",
    "S11": "bound ledger confirms completion; the agent summary cannot veto it",
    "S14": "the confirmation element the criterion names does not exist in the state",
}


def derive_all(bench_dir: Path) -> None:
    for path in sorted((bench_dir / "oracle").glob("*.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        family = record["primary_family"]
        if family in _SIMPLE:
            assertion, visual = _SIMPLE[family]
            labels = _outcome(
                "success"
                if family in ("S01", "S11")
                else "unknown"
                if family in ("S05", "S09")
                else "failure",
                "contradictory" if family == "S09" else "sufficient",
                assertion,
                visual,
                _SIMPLE_RATIONALES[family],
            )
        else:
            labels = _FAMILY[family](record["state"])
        record.update(labels)
        path.write_text(
            json.dumps(record, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8"
        )


_FAMILY = {"S04": _s04, "S06": _s06, "S07": _s07, "S08": _s08, "S12": _s12, "S13": _s13, "S15": _s15}


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    bench_dir = Path(args[0]) if args else Path(__file__).resolve().parents[1]
    derive_all(bench_dir)
    print(f"oracles derived in {bench_dir / 'oracle'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
