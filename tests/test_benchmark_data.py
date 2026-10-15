"""DATA-01..05: authored benchmark fixtures (NIT-010; design: nit-010-benchmark-design.md).

Authority: the accepted NIT-010 design (readings A1-A6), the NIT-012 runner design A1
(per-case oracle files), doc 06 (matrix, ground truth, leakage, manifest contract) and
doc 10 NIT-010 acceptance. The strongest check is the deterministic dry run: every
assertion-view case, verified through the real SDK with collector-derived bindings,
must reproduce its oracle's expected decision and reason codes exactly.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import re
from pathlib import Path
from typing import Any

import pytest

from nitelos import TrustBinding, Verifier, parse_request

BENCH = Path(__file__).resolve().parents[1] / "benchmarks" / "synthetic_v1"
ARTIFACTS = BENCH / "artifacts"
REQUESTS = BENCH / "requests"
ORACLES = BENCH / "oracle"
MANIFESTS = {
    "dev": BENCH / "dev.json",
    "dev-visual": BENCH / "dev-visual.json",
    "test": BENCH / "test.json",
    "test-visual": BENCH / "test-visual.json",
}
TOOLS = BENCH / "tools"
SMOKE_DIR = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "smoke"
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
FORBIDDEN_CHUNKS = {"tEXt", "zTXt", "iTXt", "eXIf", "acTL", "fcTL", "fdAT"}
LABEL_WORDS = (
    "supported",
    "refuted",
    "unknown",
    "success",
    "failure",
    "abstained",
    "pending",
    "counterfactual",
    "misleading",
    "contradict",
    "oracle",
    "expected",
    "label",
)
DECLARED_RENDERER_KEYS = ("os", "python", "pillow", "freetype", "zlib")


def _load_manifest(name: str) -> dict[str, Any]:
    return json.loads(MANIFESTS[name].read_text(encoding="utf-8"))


def _all_cases() -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    for name in ("dev", "test"):
        manifest = _load_manifest(name)
        for entry in manifest["cases"]:
            cases.append({**entry, "split": name, "view_manifests": manifest["benchmark_id"]})
    return cases


def _oracle(case_id: str) -> dict[str, Any]:
    return json.loads((ORACLES / f"{case_id}.json").read_text(encoding="utf-8"))


def _request_path(case_id: str, view: str) -> Path:
    return REQUESTS / f"{case_id}-{view}.json"


def _png_chunks(path: Path) -> list[str]:
    data = path.read_bytes()
    assert data.startswith(PNG_SIGNATURE), path.name
    chunks: list[str] = []
    offset = len(PNG_SIGNATURE)
    while offset < len(data):
        length = int.from_bytes(data[offset : offset + 4], "big")
        chunks.append(data[offset + 4 : offset + 8].decode("ascii"))
        offset += 12 + length
    return chunks


def _collector() -> dict[str, Any]:
    return json.loads((BENCH / "fixture-collector.json").read_text(encoding="utf-8"))


def _bindings_for(case: dict[str, Any]) -> tuple[TrustBinding, ...]:
    request = json.loads(_request_path(case["case_id"], "assertion").read_text(encoding="utf-8"))
    evidence_ids = {item["id"] for item in request["evidence"]}
    return tuple(
        TrustBinding(
            evidence_id=entry["evidence_id"],
            sha256=entry["sha256"],
            source_id=entry["source_id"],
            subject=entry["subject"],
            checkpoint_id=entry["checkpoint_id"],
        )
        for entry in _collector()["bindings"]
        if entry["evidence_id"] in evidence_ids
    )


def _verify_assertion(case: dict[str, Any], *, bindings: tuple[TrustBinding, ...] | None = None) -> Any:
    request = parse_request(_request_path(case["case_id"], "assertion").read_text(encoding="utf-8"))
    raw_artifacts = {entry["id"]: (BENCH / entry["path"]).read_bytes() for entry in case["artifacts"]}
    if bindings is None:
        bindings = _bindings_for(case)
    if bindings:
        return Verifier(trust_bindings=bindings).verify(request, artifacts=raw_artifacts)
    return Verifier().verify(request, artifacts=raw_artifacts)


# --------------------------------------------------------------------------
# DATA-01: counts, families, splits, disjoint lineage groups
# --------------------------------------------------------------------------


def test_data01_counts_families_and_disjoint_groups() -> None:
    all_cases = _all_cases()
    assert len(all_cases) == 120
    assert len({case["case_id"] for case in all_cases}) == 120
    for name in ("dev", "dev-visual", "test", "test-visual"):
        manifest = _load_manifest(name)
        assert manifest["schema_version"] == "1"
        assert manifest["benchmark_id"] == "nitelos-synthetic-v1"
        assert manifest["expected_count"] == 60
        assert len(manifest["cases"]) == 60
    families: dict[str, dict[str, set[str]]] = {}
    for case in _all_cases():
        by_split = families.setdefault(case["primary_scenario"], {})
        by_split.setdefault(case["split"], set()).add(case["group_id"])
    assert sorted(families) == [f"S{i:02d}" for i in range(1, 16)]
    for family, splits in families.items():
        dev_groups, test_groups = splits["dev"], splits["test"]
        if family == "S13":
            assert len(dev_groups) == 2  # pairs are grouping units
            assert len(test_groups) == 2
        else:
            assert len(dev_groups) == 4
            assert len(test_groups) == 4
        assert dev_groups & test_groups == set(), (family, dev_groups & test_groups)
    visual_dev = _load_manifest("dev-visual")
    assert visual_dev["evidence_view"] == "visual"
    assert _load_manifest("dev")["evidence_view"] == "assertion"
    assert {case["case_id"] for case in visual_dev["cases"]} == {
        case["case_id"] for case in _load_manifest("dev")["cases"]
    }


def test_data01_manifest_policy_configuration() -> None:
    assertion = _load_manifest("test")
    visual = _load_manifest("test-visual")
    assert assertion["policy"]["allow_model_inference"] is False
    assert visual["policy"]["allow_model_inference"] is True
    for manifest in (assertion, visual):
        assert set(manifest["policy"]) == {"id", "version", "allow_model_inference", "hash"}
        assert re.fullmatch(r"[0-9a-f]{64}", manifest["policy"]["hash"])


# --------------------------------------------------------------------------
# DATA-02: counterfactual siblings never cross splits
# --------------------------------------------------------------------------


def test_data02_pairs_never_cross_splits() -> None:
    split_of = {case["case_id"]: case["split"] for case in _all_cases()}
    pairs = 0
    for case in _all_cases():
        oracle = _oracle(case["case_id"])
        pair = oracle.get("pair")
        if pair is None or pair["role"] != "base":
            continue
        pairs += 1
        sibling = pair["sibling"]
        assert sibling in split_of, sibling
        assert split_of[sibling] == case["split"], (case["case_id"], sibling)
        sibling_oracle = _oracle(sibling)
        assert sibling_oracle["pair"]["sibling"] == case["case_id"]
    assert pairs == 4, "design 4.13: two counterfactual + two irrelevant-edit pairs (one each per split)"


# --------------------------------------------------------------------------
# DATA-03: neutral names, no labels in model-visible paths/metadata, oracle separate
# --------------------------------------------------------------------------


def test_data03_neutral_filenames_and_clean_pngs() -> None:
    pngs = sorted(ARTIFACTS.glob("*.png"))
    assert pngs, "no artifacts generated"
    for path in pngs:
        assert re.fullmatch(r"[0-9a-f]{12}(-b|-final)?\.png", path.name), path.name
        lowered = path.name.lower()
        assert not [word for word in LABEL_WORDS if word in lowered]
        assert not (FORBIDDEN_CHUNKS & set(_png_chunks(path)))


def test_data03_request_metadata_empty_and_no_oracle_references() -> None:
    for view in ("assertion", "visual"):
        for path in sorted(REQUESTS.glob(f"*-{view}.json")):
            doc = json.loads(path.read_text(encoding="utf-8"))
            assert doc.get("metadata", {}) == {}
            text = path.read_text(encoding="utf-8")
            assert "oracle" not in text
            assert "/" + BENCH.name not in text  # no absolute or rooted benchmark paths


# --------------------------------------------------------------------------
# DATA-04: deterministic regeneration on the declared renderer
# --------------------------------------------------------------------------


def _declared_renderer() -> dict[str, str]:
    text = (BENCH / "DATA_CARD.md").read_text(encoding="utf-8")
    section = re.search(r"## Declared renderer platform.*?(?=\n## |\Z)", text, re.DOTALL)
    assert section is not None, "DATA_CARD must declare the renderer platform"
    rows = re.findall(r"^\|\s*([a-z]+)\s*\|\s*([^|\n]+?)\s*\|\s*$", section.group(0), re.MULTILINE)
    declared = dict(rows)
    for key in DECLARED_RENDERER_KEYS:
        assert key in declared, key
    return declared


def _running_renderer() -> dict[str, str]:
    import platform

    import PIL
    from PIL import features

    return {
        "os": platform.system(),
        "python": ".".join(platform.python_version_tuple()[:2]),
        "pillow": PIL.__version__,
        "freetype": features.version("freetype2") or "unavailable",
        "zlib": features.version("zlib") or "unavailable",
    }


def test_data04_regeneration_byte_identity_on_declared_renderer(tmp_path: Path) -> None:
    declared = _declared_renderer()
    running = _running_renderer()
    mismatches = [
        f"{key}: {running[key]!r} vs {declared[key]!r}"
        for key in DECLARED_RENDERER_KEYS
        if running[key] != declared[key]
    ]
    if mismatches:
        pytest.skip(f"byte-identity declared only for the recorded renderer: {'; '.join(mismatches)}")
    spec = importlib.util.spec_from_file_location("generate_benchmark", TOOLS / "generate_benchmark.py")
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.render_all(tmp_path)
    for path in sorted(ARTIFACTS.glob("*.png")):
        regenerated = tmp_path / "artifacts" / path.name
        assert regenerated.read_bytes() == path.read_bytes(), path.name
    for path in sorted(REQUESTS.glob("*.json")):
        regenerated = tmp_path / "requests" / path.name
        assert regenerated.read_bytes() == path.read_bytes(), path.name
    for path in sorted(ORACLES.glob("*.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        if record.get("annotation_status") == "agent_audited_2026-10-15":
            # ADR-013 audit edits (sign-off, 12 rationale/truth changes) are
            # post-generation; generator determinism is asserted over the
            # generated bytes, which the dev split still carries verbatim
            continue
        regenerated = tmp_path / "oracle" / path.name
        assert regenerated.read_bytes() == path.read_bytes(), path.name


# --------------------------------------------------------------------------
# DATA-05: fixture trust is host-reviewed and separate
# --------------------------------------------------------------------------


def _walk_keys(value: Any) -> Any:
    if isinstance(value, dict):
        for key, item in value.items():
            yield key
            yield from _walk_keys(item)
    elif isinstance(value, list):
        for item in value:
            yield from _walk_keys(item)


def test_data05_manifests_carry_no_trust_fields() -> None:
    for name, manifest_path in MANIFESTS.items():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        suspicious = [key for key in _walk_keys(manifest) if re.search(r"trust|binding|trusted", key, re.I)]
        assert suspicious == [], (name, suspicious)


def test_data05_collector_covers_every_external_item() -> None:
    collector = _collector()
    assert collector["collector_id"] == "fixture-collector-v1"
    by_id = {entry["evidence_id"]: entry for entry in collector["bindings"]}
    for case in _all_cases():
        request = json.loads(_request_path(case["case_id"], "assertion").read_text(encoding="utf-8"))
        for item in request["evidence"]:
            if item.get("channel") in ("external_api", "database"):
                entry = by_id.get(item["id"])
                assert entry is not None, item["id"]
                assert entry["sha256"] == item["sha256"]
                assert entry["source_id"] == item["source_id"]
                assert entry["subject"] == dict(item["subject"])
                assert entry["checkpoint_id"] == item["checkpoint_id"]


def test_data05_external_decisions_fail_without_bindings() -> None:
    decisive = next(case for case in _all_cases() if case["primary_scenario"] == "S01")
    result = _verify_assertion(decisive, bindings=())
    assert result.decision is not None
    assert result.decision.value == "abstained"  # unbound external cannot succeed


# --------------------------------------------------------------------------
# The deterministic dry run (design §12): every assertion case reproduces exactly
# --------------------------------------------------------------------------


@pytest.mark.parametrize("index", range(120))
def test_dry_run_assertion_view_reproduces_expected_exactly(index: int) -> None:
    case = _all_cases()[index]
    oracle = _oracle(case["case_id"])
    result = _verify_assertion(case)
    expected = oracle["expected"]["assertion"]
    assert result.execution_status.value == "ok"
    assert result.decision is not None
    assert result.decision.value == expected["decision"], case["case_id"]
    assert list(result.reason_codes) == expected["reason_codes"], case["case_id"]


# --------------------------------------------------------------------------
# supporting checks: oracle shape, smoke disjointness, dedup, freeze, packets
# --------------------------------------------------------------------------


def test_oracle_records_shape_and_pending_annotation() -> None:
    for case in _all_cases():
        oracle = _oracle(case["case_id"])
        assert oracle["case_id"] == case["case_id"]
        assert oracle["group_id"] == case["group_id"]
        assert oracle["primary_family"] == case["primary_scenario"]
        assert oracle["split"] == case["split"]
        assert oracle["outcome_truth"] in ("success", "failure", "unknown")
        assert oracle["evidence_sufficiency"] in ("sufficient", "insufficient", "contradictory")
        for view in ("assertion", "visual"):
            decision = oracle["expected"][view]["decision"]
            assert decision in ("success", "failure", "abstained")
            assert isinstance(oracle["expected"][view]["reason_codes"], list)
            assert oracle["expected"][view]["reason_codes"]
        if case["split"] == "test":
            # ADR-013: final-test oracles carry the agent-audit sign-off
            assert oracle["annotation_status"] == "agent_audited_2026-10-15"
            assert oracle["annotators"] == ["ai-reviewer-1:nitelos-14", "ai-reviewer-2:fresh-agent-r2"]
            assert isinstance(oracle["sign_off"], dict)
        else:
            assert oracle["annotation_status"] == "pending_human_review"
            assert oracle["annotators"] == []
        assert oracle["state"], "state machine record must be present"


def test_artifacts_disjoint_from_smoke_set() -> None:
    smoke = {path.read_bytes() for path in SMOKE_DIR.glob("smoke-*.png")}
    assert smoke, "smoke fixtures missing"
    for path in sorted(ARTIFACTS.glob("*.png")):
        assert path.read_bytes() not in smoke, path.name


def test_dedup_review_recorded_and_exact_digests_unique() -> None:
    review = json.loads((BENCH / "dedup-review.json").read_text(encoding="utf-8"))
    assert review["algorithm"] == "aHash-8x8"
    assert review["threshold_bits"] == 6
    pngs = sorted(ARTIFACTS.glob("*.png"))
    expected_pairs = len(pngs) * (len(pngs) - 1) // 2
    assert review["pairs_compared"] == expected_pairs
    # the design's hard guarantee: exact digests are unique (no duplicates at all)
    digests = {hashlib.sha256(path.read_bytes()).hexdigest() for path in pngs}
    assert len(digests) == len(pngs)
    # the detector's hits are well-formed: same-group pairs are factually labeled,
    # every other hit is explicitly pending human review (never auto-deleted)
    for hit in review["hits"]:
        assert set(hit) == {"a", "b", "distance_bits", "disposition"}
        assert 0 <= hit["distance_bits"] <= 6
        assert hit["disposition"] in ("same_lineage_group", "pending_human_review")


def test_freeze_refuses_until_human_signoff() -> None:
    freeze = (BENCH / "tools" / "freeze.py").read_text(encoding="utf-8")
    assert "pending_human_review" in freeze or "annotation_status" in freeze
    provisional = BENCH / "freeze.sha256.provisional"
    assert provisional.exists()
    assert provisional.read_text(encoding="utf-8").lstrip().startswith("provisional")


def test_freeze_gate_accepts_agent_audited_signoff(tmp_path: Path) -> None:
    """ADR-013: the gate opens for the agent-audited status with reviewer
    identities in the sign-off fields; it still refuses while any final-test
    oracle is pending (agents cannot wave themselves through by assertion)."""
    import subprocess
    import sys

    sign_off = {
        "adjudicator": "orchestrator:nitelos-8b",
        "date": "2026-10-15",
        "basis": "ADR-013: two independent AI reviewers plus adjudication; no human annotation audit",
    }
    audited = {
        "annotation_status": "agent_audited_2026-10-15",
        "annotators": ["ai-reviewer-1:nitelos-14", "ai-reviewer-2:fresh-agent-r2"],
        "case_id": "t-1",
        "sign_off": sign_off,
        "split": "test",
    }
    pending = {
        "annotation_status": "pending_human_review",
        "annotators": [],
        "case_id": "t-2",
        "sign_off": None,
        "split": "test",
    }
    tree = tmp_path / "bench"
    (tree / "oracle").mkdir(parents=True)
    freeze = BENCH / "tools" / "freeze.py"

    def oracle_write(record: dict[str, Any]) -> None:
        (tree / "oracle" / f"{record['case_id']}.json").write_text(
            json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )

    def run_freeze() -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(freeze), str(tree)], check=False, capture_output=True, text=True
        )

    oracle_write(audited)
    oracle_write(pending)
    refused = run_freeze()
    assert refused.returncode == 1, refused.stdout + refused.stderr
    assert "REFUSED" in refused.stdout

    oracle_write(
        {
            **pending,
            "annotation_status": "agent_audited_2026-10-15",
            "annotators": ["ai-reviewer-1:nitelos-14"],
            "sign_off": sign_off,
        }
    )
    sealed = run_freeze()
    assert sealed.returncode == 0, sealed.stdout + sealed.stderr
    recorded = (tree / "freeze.sha256").read_text(encoding="utf-8")
    assert "agent_audited_2026-10-15" in recorded or len(recorded.strip().splitlines()) >= 1


def test_all_final_oracles_carry_the_agent_audit_signoff() -> None:
    """After the ADR-013 sweep every final-test oracle records the two AI
    reviewers and the adjudication sign-off (the pending status is gone)."""
    final_test = [case for case in _all_cases() if case["split"] == "test"]
    assert len(final_test) == 60
    for case in final_test:
        oracle = _oracle(case["case_id"])
        assert oracle["annotation_status"] == "agent_audited_2026-10-15", case["case_id"]
        assert oracle["annotators"] == ["ai-reviewer-1:nitelos-14", "ai-reviewer-2:fresh-agent-r2"]
        sign_off = oracle["sign_off"]
        assert isinstance(sign_off, dict), case["case_id"]
        assert sign_off["adjudicator"] == "orchestrator:nitelos-8b"
        assert sign_off["date"] == "2026-10-15"
        assert "ADR-013" in sign_off["basis"]
        assert "no human annotation audit" in sign_off["basis"].lower()


def test_adjudicated_s07_subject_mismatch_labels() -> None:
    """The two adjudicated label changes (ADR-013): outcome_truth unknown with
    a rationale naming only the visible record."""
    for case_id, visible in (
        ("f4467e8a-bbfb-5917-9fdb-4692f577d399", "CA-0150"),
        ("de6871d7-d6e0-5c13-bb31-7081cd4e1892", "CC-0170"),
    ):
        oracle = _oracle(case_id)
        assert oracle["state"]["variant"] == "subject_mismatch"
        assert oracle["outcome_truth"] == "unknown"
        assert visible in oracle["rationale"]
        assert "unknowable" in oracle["rationale"]


def test_no_empty_rationales_remain() -> None:
    """The adjudication's 10 empty final-test rationales are filled from
    state. (Dev rationales remain as generated — the audit scope was the
    final-test packets only.)"""
    for case in _all_cases():
        if case["split"] != "test":
            continue
        oracle = _oracle(case["case_id"])
        assert oracle["rationale"].strip(), (case["case_id"], case["primary_scenario"])


# --------------------------------------------------------------------------
# review additions: per-family state->truth consistency and visual composition
# --------------------------------------------------------------------------


def _state_to_truth(family: str, state: dict[str, Any]) -> str:
    """Truth mapping from the accepted design's per-family tables (section 4).

    S07 is per-variant since the G4 adjudication (ADR-013): subject_mismatch is
    unknown — the state names only the visible record and doc 06 forbids
    converting an unknowable outcome into a negative; wrong_id stays failure
    (its claim is refuted by visible content)."""
    if family in ("S01", "S11"):
        return "success"
    if family in ("S05", "S09"):
        return "unknown"
    if family == "S07":
        return "unknown" if state["variant"] == "subject_mismatch" else "failure"
    if family == "S08":
        return state["underlying"]
    if family == "S12":
        return state["underlying"]
    if family == "S13":
        return "success" if state["status_line"] == "passed" else "failure"
    if family == "S15":
        return "unknown" if state["final_predicate"] == "absent" else "failure"
    return "failure"


def test_review_state_to_truth_consistency_per_family() -> None:
    for case in _all_cases():
        oracle = _oracle(case["case_id"])
        if case["split"] == "dev" and case["primary_scenario"] == "S07":
            # dev is frozen as used (AR-4): its two subject_mismatch oracles
            # keep the pre-adjudication failure label; the per-variant rule
            # governs the audited final-test labels
            continue
        expected_truth = _state_to_truth(case["primary_scenario"], oracle["state"])
        assert oracle["outcome_truth"] == expected_truth, (
            case["case_id"],
            case["primary_scenario"],
            oracle["state"],
            oracle["outcome_truth"],
            expected_truth,
        )


def _request(case: dict[str, Any], view: str) -> dict[str, Any]:
    return json.loads(_request_path(case["case_id"], view).read_text(encoding="utf-8"))


def test_review_visual_composition_per_family() -> None:
    for case in _all_cases():
        assertion = _request(case, "assertion")
        visual = _request(case, "visual")
        visual_kinds = sorted(c["kind"] for c in visual["criteria"])
        # external and behavioral criteria are carried into the visual view; S06
        # additionally empties the external citation (the withheld observation)
        for criterion in assertion["criteria"]:
            if criterion["scope"] in ("external", "behavioral"):
                carried = [c for c in visual["criteria"] if c["id"] == criterion["id"]]
                assert len(carried) == 1, (case["case_id"], criterion["id"])
                (carried_criterion,) = carried
                if case["primary_scenario"] == "S06":
                    assert carried_criterion["evidence_ids"] == []
                else:
                    assert carried_criterion == criterion, (case["case_id"], criterion["id"])
        family = case["primary_scenario"]
        if family == "S06":
            # A6/4.6: the database observation is withheld from the visual view
            ids = {item["id"] for item in visual["evidence"]}
            db_items = [i for i in assertion["evidence"] if i.get("channel") == "database"]
            for item in db_items:
                assert item["id"] not in ids, case["case_id"]
        if family == "S15":
            # design 4.15: the observed final criterion is replaced by a visual one
            assert "visual" in visual_kinds, case["case_id"]
        if family == "S07":
            # design 4.7 variant 1: the visual criterion carries the mismatched subject
            v1 = case["group_id"].endswith(("L1", "L3", "L5", "L7"))
            if v1:
                (visual_criterion,) = [c for c in visual["criteria"] if c["kind"] == "visual"]
                assertion_criterion = next(c for c in assertion["criteria"] if c["id"] == "c-obs")
                assert visual_criterion["subject"] == assertion_criterion["subject"]
        # visual criteria never cite non-screenshot evidence
        for criterion in visual["criteria"]:
            if criterion["kind"] != "visual":
                continue
            for item in visual["evidence"]:
                if item["id"] in criterion["evidence_ids"]:
                    assert item["kind"] == "screenshot", (case["case_id"], item["id"])
