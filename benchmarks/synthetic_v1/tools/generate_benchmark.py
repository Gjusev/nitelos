"""Deterministic generator for the nitelos-synthetic-v1 benchmark (NIT-010).

Authority: docs/implementation/nit-010-benchmark-design.md (accepted readings A1-A6),
amended by the NIT-012 runner design A1 (one oracle file per case). Renders the 120
authored cases (15 families x 8, eight disjoint lineage groups per family, S13 pairs as
grouping units), builds the two request views per case with factory-accurate digests,
writes state-only oracle records (labels are filled by the separately reviewed
``derive_oracle.py``, which reads state only), the four manifests, the host-reviewed
fixture-collector authorization, review packets for the human audit, the dedup review
log and the DATA card.

Determinism: no RNG anywhere — every coordinate, color, string and ID is a fixed
constant or a deterministic function of (family, group, slot). Regeneration is
byte-identical on the declared renderer platform (recorded in the DATA card; the smoke
set's platform-scoped DATA-04 pattern). Case IDs are UUID5 over a fixed namespace.
Nothing in a model-visible path, filename or metadata carries a label. All content is
original synthetic UI; every name, prefix and ID is invented. License Apache-2.0.

Usage: python benchmarks/synthetic_v1/tools/generate_benchmark.py [OUT_DIR]
(defaults to benchmarks/synthetic_v1 next to tools/).
"""

from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import platform
import sys
import uuid
from pathlib import Path
from typing import Any

import PIL
from PIL import Image, ImageDraw, ImageFont
from PIL import features as pil_features

from nitelos.policy import VerificationPolicy, policy_hash
from nitelos.schemas import canonical_json

NAMESPACE_BENCH = uuid.UUID("7e1f2a54-6b0d-4c8e-9a3f-5d21c8b40e97")
GENERATION_ID = "nitelos-synthetic-v1-generation-v1"
AS_OF = "2026-10-20T10:01:00Z"
CHECKPOINT = "cp-final"
W, H = 1200, 800

PALETTES: tuple[tuple[tuple[int, int, int], ...], ...] = (
    ((36, 43, 56), (240, 243, 247), (63, 81, 181), (56, 142, 60), (198, 40, 40)),
    ((40, 44, 52), (245, 242, 236), (0, 105, 92), (67, 160, 71), (198, 40, 40)),
    ((50, 40, 56), (243, 240, 247), (123, 31, 162), (46, 125, 50), (198, 40, 40)),
    ((30, 46, 58), (238, 245, 247), (0, 121, 107), (76, 175, 80), (211, 47, 47)),
    ((56, 42, 36), (247, 244, 238), (230, 81, 0), (104, 159, 56), (211, 47, 47)),
    ((36, 56, 42), (240, 247, 243), (26, 35, 126), (0, 137, 123), (211, 47, 47)),
    ((44, 52, 58), (244, 246, 247), (69, 90, 100), (67, 160, 71), (211, 47, 47)),
    ((58, 36, 52), (247, 240, 244), (173, 20, 87), (56, 142, 60), (211, 47, 47)),
)
FIRST_NAMES = (
    "Aro",
    "Bex",
    "Cai",
    "Dov",
    "Eli",
    "Fen",
    "Gia",
    "Hux",
    "Iri",
    "Jor",
    "Kel",
    "Lum",
    "Mira",
    "Nox",
    "Ovi",
)
LAST_NAMES = (
    "Adder",
    "Brook",
    "Cinder",
    "Delta",
    "Ember",
    "Field",
    "Gale",
    "Hollow",
    "Iron",
    "Junction",
    "Kestrel",
    "Larch",
    "Mill",
    "Nether",
    "Orchard",
    "Pine",
    "Quarry",
    "Reed",
    "Stone",
    "Thorn",
    "Umber",
    "Vale",
    "Wold",
    "Yard",
)
PREFIX_LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
JOB_KINDS = ("export", "report", "sync", "archive", "backup", "upload", "render", "index")
ERROR_CODES_DEV = ("E201", "E202", "E203", "E204")
ERROR_CODES_TEST = ("E210", "E211", "E212", "E213")
EMPTY_FIELDS = ("email", "display name", "workspace tag", "region")
EMPTY_FIELD_KEYS = ("email", "display_name", "workspace_tag", "region")
LIST_ROWS = ("Weekly summary", "Monthly rollup", "Quarterly digest")

SUBJECT_KEYS = {
    "S01": "job",
    "S02": "submission",
    "S03": "form",
    "S04": "payment",
    "S05": "deployment",
    "S06": "sync",
    "S07": "order",
    "S08": "record",
    "S09": "syncjob",
    "S10": "upload",
    "S11": "transfer",
    "S12": "build",
    "S13": "task",
    "S14": "report",
    "S15": "import",
}
FAMILY_TITLES = {
    "S01": JOB_KINDS,
    "S02": JOB_KINDS,
    "S03": ("profile", "account", "signup", "workspace", "member", "tenant", "signup", "workspace"),
    "S04": ("payment", "transfer", "payout", "invoice", "settle", "remit", "charge", "billing"),
    "S05": ("deploy", "release", "rollout", "canary", "push", "ship", "promote", "restart"),
    "S06": ("folder", "repo", "drive", "bucket", "share", "vault", "stash", "mirror"),
    "S07": ("order", "record", "invoice", "ticket", "booking", "claim", "parcel", "case"),
    "S08": ("record", "entry", "item", "asset", "note", "file", "row", "card"),
    "S09": ("folder", "repo", "drive", "bucket", "share", "vault", "stash", "mirror"),
    "S10": ("file", "asset", "bundle", "patch", "image", "dump", "packet", "blob"),
    "S11": ("transfer", "payout", "remittance", "settle", "wire", "clear", "rebate", "refund"),
    "S12": ("build", "pipeline", "check", "run", "compile", "verify", "bundle", "test"),
    "S13": ("task", "job", "chore", "errand", "quest", "shift", "stint", "gig"),
    "S14": ("report", "digest", "summary", "brief", "ledger", "digest", "recap", "folio"),
    "S15": ("import", "ingest", "load", "batch", "feed", "sync", "migrate", "intake"),
}


def _font(size: int) -> Any:
    return ImageFont.load_default(size=size)


def group_index(family_number: int, group_number: int) -> int:
    """Global lineage-group index in (family, group) order: 15 families x 8 groups."""
    return (family_number - 1) * 8 + (group_number - 1)


def group_prefix(family_number: int, group_number: int) -> str:
    index = group_index(family_number, group_number)
    return PREFIX_LETTERS[index // 26] + PREFIX_LETTERS[index % 26]


def group_names(family_number: int, group_number: int) -> tuple[str, str, str]:
    base = group_index(family_number, group_number) * 3
    return tuple(  # type: ignore[return-value]
        f"{FIRST_NAMES[(base + k) // len(LAST_NAMES) % len(FIRST_NAMES)]} "
        f"{LAST_NAMES[(base + k) % len(LAST_NAMES)]}"
        for k in range(3)
    )


def case_id(family: str, group_number: int, slot: str = "") -> str:
    return str(uuid.uuid5(NAMESPACE_BENCH, f"{family}:{'L' + str(group_number)}:{slot}"))


def file_stem(case: str) -> str:
    return case.replace("-", "")[:12]


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def payload_digest(payload: Any) -> str:
    return _digest(canonical_json(payload).encode("utf-8"))


# ---------------------------------------------------------------------------
# scene rendering (original synthetic chrome, distinct from the smoke set)
# ---------------------------------------------------------------------------


def _frame(draw: ImageDraw.ImageDraw, title: str, group_number: int) -> None:
    ink, _paper, accent, _, _ = PALETTES[(group_number - 1) % 8]
    tint = 232 + (group_number % 5) * 4  # per-group paper tint
    header_h = 72 + (group_number % 4) * 24
    draw.rectangle((0, 0, W, H), fill=(tint, tint + 2, tint + 5))
    draw.rectangle((0, 0, W, header_h), fill=ink)
    draw.rectangle((24, 18, 56, 50), fill=accent)
    draw.text((72, 26), title, font=_font(26), fill=(245, 247, 250))
    if group_number % 2 == 1:  # layout variant: left rail vs top tabs
        draw.rectangle((0, header_h, 200, H), fill=ink)
        for i in range(6):
            draw.rectangle(
                (18, 104 + i * 44, 182, 136 + i * 44),
                fill=(tint, tint + 2, tint + 5),
                outline=accent,
                width=1,
            )
    else:
        for i in range(4):
            draw.rectangle(
                (24 + i * 190, header_h + 16, 194 + i * 190, header_h + 56), fill=ink, outline=accent, width=1
            )
    # per-group section band behind the content area
    band_y = 340 + (group_number % 4) * 92
    band_h = 26 + group_number * 5
    draw.rectangle((0, band_y, W, band_y + band_h), fill=accent)
    # per-group corner inlay: a fixed-size hollow square placed from a fixed
    # shuffle table - separates aHash without encoding the group number in any
    # human-legible or binary form
    inlay_positions = (
        (1120, 120),
        (1120, 260),
        (1120, 640),
        (300, 120),
        (620, 120),
        (920, 640),
        (300, 640),
        (620, 640),
    )
    ix, iy = inlay_positions[(group_number - 1) % 8]
    draw.rectangle((ix, iy, ix + 56, iy + 56), outline=ink, width=10)
    draw.rectangle((ix + 18, iy + 18, ix + 38, iy + 38), fill=accent)
    draw.text((24, H - 44), f"{title} - synthetic fixture", font=_font(14), fill=(120, 128, 140))


def _banner(
    draw: ImageDraw.ImageDraw, text: str, tone: int, group_number: int, box: tuple[int, int, int, int]
) -> None:
    _, _, _, good, bad = PALETTES[(group_number - 1) % 8]
    fill = (232, 245, 233) if tone == 1 else (253, 232, 232) if tone == -1 else (236, 239, 241)
    edge = good if tone == 1 else bad if tone == -1 else (144, 156, 168)
    draw.rounded_rectangle(box, radius=16, fill=fill, outline=edge, width=4)
    x0, y0, x1, y1 = box
    draw.text(((x0 + x1) // 2, (y0 + y1) // 2), text, font=_font(44), fill=edge, anchor="mm")


def _status_row(draw: ImageDraw.ImageDraw, x: int, y: int, label: str, value: str, *, size: int = 28) -> None:
    draw.text((x, y), label, font=_font(size), fill=(120, 128, 140))
    draw.text((x + 360, y), value, font=_font(size), fill=(35, 39, 47))


def _form_row(  # noqa: PLR0917 - generator-internal fixture builder
    draw: ImageDraw.ImageDraw, x: int, y: int, w: int, label: str, value: str, *, error: str | None = None
) -> None:
    edge = (211, 47, 47) if error else (180, 188, 198)
    draw.text((x, y), label, font=_font(20), fill=(120, 128, 140))
    draw.rounded_rectangle((x, y + 28, x + w, y + 78), radius=8, fill=(250, 251, 253), outline=edge, width=2)
    if value:
        draw.text((x + 14, y + 42), value, font=_font(24), fill=(35, 39, 47))
    if error:
        draw.text((x, y + 86), error, font=_font(18), fill=(183, 28, 28))


def _list_row(
    draw: ImageDraw.ImageDraw, y: int, left: str, right: str, *, right_fill: tuple[int, int, int]
) -> None:
    draw.line((240, y - 12, 1160, y - 12), fill=(216, 222, 230), width=1)
    draw.text((240, y), left, font=_font(24), fill=(35, 39, 47))
    draw.text((1160, y), right, font=_font(24), fill=right_fill, anchor="ra")


def _spinner(draw: ImageDraw.ImageDraw, cx: int, cy: int, r: int, color: tuple[int, int, int]) -> None:
    draw.arc((cx - r, cy - r, cx + r, cy + r), start=30, end=300, fill=color, width=14)
    draw.ellipse((cx - 10, cy - 10, cx + 10, cy + 10), fill=color)


def render_scene(spec: dict[str, Any]) -> bytes:
    """Render one scene to PNG bytes from a pure widget spec (no RNG)."""
    image = Image.new("RGB", (W, H), (255, 255, 255))
    draw = ImageDraw.Draw(image)
    group = spec["group_number"]
    _, _, accent, _, _ = PALETTES[(group - 1) % 8]
    _frame(draw, spec["title"], group)
    for widget in spec["widgets"]:
        kind = widget[0]
        if kind == "banner":
            _, text, tone, box = widget
            _banner(draw, text, tone, group, box)
        elif kind == "status":
            _, x, y, label, value, size = widget
            _status_row(draw, x, y, label, value, size=size)
        elif kind == "form":
            _, x, y, w, label, value, error = widget
            _form_row(draw, x, y, w, label, value, error=error)
        elif kind == "row":
            _, y, left, right, tone = widget
            fill = (27, 94, 32) if tone == 1 else (183, 28, 28) if tone == -1 else (120, 128, 140)
            _list_row(draw, y, left, right, right_fill=fill)
        elif kind == "spinner":
            _, cx, cy, r = widget
            _spinner(draw, cx, cy, r, accent)
        elif kind == "bar":
            _, x, y, w, h, frac = widget
            draw.rounded_rectangle((x, y, x + w, y + h), radius=8, outline=(180, 188, 198), width=2)
            draw.rounded_rectangle((x, y, x + int(w * frac), y + h), radius=8, fill=accent)
        elif kind == "note":
            _, x, y, text, size = widget
            draw.text((x, y), text, font=_font(size), fill=(120, 128, 140))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


# ---------------------------------------------------------------------------
# case construction: state, evidence, criteria, scenes, oracle shells
# ---------------------------------------------------------------------------


def _base_identity(family_number: int, group_number: int) -> dict[str, Any]:
    prefix = group_prefix(family_number, group_number)
    names = group_names(family_number, group_number)
    return {"prefix": prefix, "names": names, "entity": f"{prefix}-0101"}


def _subject_key(family: str) -> str:
    return SUBJECT_KEYS[family]


def build_case(family: str, group_number: int, slot: int) -> dict[str, Any]:
    """Build one case: identity, state, evidence specs, criteria specs, scene specs."""
    family_number = int(family[1:])
    identity = _base_identity(family_number, group_number)
    prefix = identity["prefix"]
    entity = f"{prefix}-{100 + group_number * 10 + slot:04d}"
    skey = _subject_key(family)
    subject = {skey: entity}
    title_word = FAMILY_TITLES[family][(group_number - 1) % len(FAMILY_TITLES[family])]
    app = f"{title_word.capitalize()} Console {prefix}"
    split = "dev" if group_number <= 4 else "test"
    case = {
        "family": family,
        "family_number": family_number,
        "group": group_number,
        "group_id": f"{family.lower()}:L{group_number}",
        "slot": slot,
        "split": split,
        "case_id": case_id(family, group_number, f"slot{slot}"),
        "identity": identity,
        "entity": entity,
        "subject": subject,
        "app": app,
        "title_word": title_word,
        "job_kind": JOB_KINDS[(group_number - 1) % 8],
        "person": identity["names"][slot % 3],
    }
    _FAMILY_BUILDERS[family](case)
    _uniquify_ids(case)
    return case


def _uniquify_ids(case: dict[str, Any]) -> None:
    """Prefix evidence and artifact IDs with the neutral case stem.

    Family builders use short local IDs (ext-1, shot-a...); every ID becomes
    <stem>-<local> so evidence IDs and fixture-collector entries are unique across
    the whole benchmark and bindings never collide. The stems are neutral hex.
    """
    stem = file_stem(case["case_id"])
    ev_map = {item["id"]: f"{stem}-{item['id']}" for item in case["evidence"]}
    art_map = {aid: f"{stem}-{aid}" for aid in case["artifacts"]}
    for item in case["evidence"]:
        item["id"] = ev_map[item["id"]]
        if item["kind"] == "screenshot":
            item["artifact_id"] = art_map[item["artifact_id"]]
    case["artifacts"] = {art_map[aid]: png for aid, png in case["artifacts"].items()}
    for criterion in case["criteria"]:
        criterion["evidence_ids"] = [ev_map[e] for e in criterion["evidence_ids"]]
    for key, (evidence_ids, description) in case.get("visual_replace", {}).items():
        case["visual_replace"][key] = ([ev_map[e] for e in evidence_ids], description)
    if case.get("visual_extra") is not None:
        evidence_ids, description = case["visual_extra"]
        case["visual_extra"] = ([ev_map[e] for e in evidence_ids], description)
    case["visual_drop_evidence"] = [ev_map[e] for e in case.get("visual_drop_evidence", [])]


def _obs_item(case: dict[str, Any], eid: str, seq: int, data: dict[str, Any], **over: Any) -> dict[str, Any]:
    item = {
        "id": eid,
        "kind": "observation",
        "sequence": seq,
        "captured_at": _captured(seq),
        "checkpoint_id": CHECKPOINT,
        "source_id": "fixture-ui",
        "subject": dict(case["subject"]),
        "phase": "final",
        "sha256": payload_digest(data),
        "channel": "dom",
        "data": data,
    }
    item.update(over)
    return item


def _ext_item(
    case: dict[str, Any], eid: str, seq: int, data: dict[str, Any], channel: str = "external_api"
) -> dict[str, Any]:
    return _obs_item(case, eid, seq, data, channel=channel, source_id="fixture-collector-v1")


def _action_item(case: dict[str, Any], eid: str, seq: int, name: str, **over: Any) -> dict[str, Any]:
    arguments = over.pop("arguments", {"target": case["entity"]})
    reported = over.pop("reported_status", "completed")
    tool_result_id = over.pop("tool_result_id", None)
    view = {
        "name": name,
        "arguments": arguments,
        "reported_status": reported,
        "tool_result_id": tool_result_id,
    }
    item = {
        "id": eid,
        "kind": "action",
        "sequence": seq,
        "captured_at": _captured(seq),
        "checkpoint_id": CHECKPOINT,
        "source_id": "agent-runner",
        "subject": dict(case["subject"]),
        "phase": "final",
        "sha256": payload_digest(view),
        "name": name,
        "arguments": arguments,
        "reported_status": reported,
        "tool_result_id": tool_result_id,
    }
    item.update(over)
    return item


def _shot_item(case: dict[str, Any], eid: str, seq: int, artifact_id: str, png: bytes) -> dict[str, Any]:
    width, height = Image.open(io.BytesIO(png)).size
    return {
        "id": eid,
        "kind": "screenshot",
        "sequence": seq,
        "captured_at": _captured(seq),
        "checkpoint_id": CHECKPOINT,
        "source_id": "fixture-ui",
        "subject": dict(case["subject"]),
        "phase": "final",
        "sha256": _digest(png),
        "artifact_id": artifact_id,
        "media_type": "image/png",
        "width": width,
        "height": height,
    }


def _captured(seq: int) -> str:
    minute, second = divmod(seq, 60)
    return f"2026-10-20T10:{minute:02d}:{second:02d}Z"


def _crit(  # noqa: PLR0917 - generator-internal fixture builder; bundling would hurt clarity
    cid: str,
    scope: str,
    pointer: str,
    operator: str,
    expected: Any,
    evidence_ids: list[str],
    subject: dict[str, str],
    description: str,
) -> dict[str, Any]:
    return {
        "id": cid,
        "description": description,
        "kind": "assertion",
        "scope": scope,
        "evidence_ids": evidence_ids,
        "subject": dict(subject),
        "pointer": pointer,
        "operator": operator,
        **({"expected": expected} if operator != "exists" else {}),
    }


def _visual_crit(
    cid: str, evidence_ids: list[str], subject: dict[str, str], description: str
) -> dict[str, Any]:
    return {
        "id": cid,
        "description": description,
        "kind": "visual",
        "scope": "visual",
        "evidence_ids": list(evidence_ids),
        "subject": dict(subject),
    }


# ---- family builders: state + evidence + criteria + scenes ------------------

BANNER_BOX = (240, 150, 1160, 330)


def _s01(case: dict[str, Any]) -> None:
    kind = case["job_kind"]
    items_done = (2, 4, 7, 12, 3, 5, 9, 14)[case["group"] - 1]
    data = {"job_status": "completed", "items": items_done}
    ext_data = {"status": "completed", "record_count": items_done}
    png = render_scene(
        {
            "title": case["app"],
            "group_number": case["group"],
            "widgets": [
                ("banner", f"{kind.capitalize()} complete", 1, BANNER_BOX),
                ("status", 260, 380, "Job", case["entity"], 28),
                ("status", 260, 430, "Items written", str(items_done), 28),
                ("status", 260, 480, "Operator", case["person"], 28),
            ],
        }
    )
    case["state"] = {"final_status": "completed", "items": items_done}
    case["evidence"] = [
        _shot_item(case, "shot-1", 0, "art-1", png),
        _obs_item(case, "dom-1", 1, data),
        _ext_item(case, "ext-1", 2, ext_data),
    ]
    case["artifacts"] = {"art-1": png}
    desc = f"The {case['app']} window shows a banner stating the {kind} completed"
    case["criteria"] = [
        _crit(
            "c-ext",
            "external",
            "/status",
            "equals",
            "completed",
            ["ext-1"],
            case["subject"],
            f"Backend record for {case['entity']} reports status completed",
        ),
        _crit(
            "c-obs",
            "observed_state",
            "/job_status",
            "equals",
            "completed",
            ["dom-1"],
            case["subject"],
            f"Interface state for {case['entity']} reports the {kind} completed",
        ),
    ]
    case["visual_replace"] = {"c-obs": (["shot-1"], desc)}
    case["visual_drop_evidence"] = []
    case["scope"] = ["external", "observed_state", "visual"]


def _s02(case: dict[str, Any]) -> None:
    code = (ERROR_CODES_DEV + ERROR_CODES_TEST)[case["group"] - 1]
    data = {"job_status": "failed", "error": code}
    png = render_scene(
        {
            "title": case["app"],
            "group_number": case["group"],
            "widgets": [
                ("banner", "Submission rejected", -1, BANNER_BOX),
                ("status", 260, 380, "Submission", case["entity"], 28),
                ("status", 260, 430, "Error", code, 28),
            ],
        }
    )
    case["state"] = {"final_status": "failed", "error": code}
    case["evidence"] = [
        _shot_item(case, "shot-1", 0, "art-1", png),
        _obs_item(case, "dom-1", 1, data),
        _ext_item(case, "ext-1", 2, {"status": "failed", "error": code}),
    ]
    case["artifacts"] = {"art-1": png}
    desc = f"The {case['app']} window shows a banner stating the submission was accepted"
    case["criteria"] = [
        _crit(
            "c-ext",
            "external",
            "/status",
            "equals",
            "completed",
            ["ext-1"],
            case["subject"],
            f"Backend record for {case['entity']} reports status completed",
        ),
        _crit(
            "c-obs",
            "observed_state",
            "/job_status",
            "equals",
            "completed",
            ["dom-1"],
            case["subject"],
            f"Interface state for {case['entity']} reports the submission completed",
        ),
    ]
    case["visual_replace"] = {"c-obs": (["shot-1"], desc)}
    case["visual_drop_evidence"] = []
    case["scope"] = ["external", "observed_state", "visual"]


def _s03(case: dict[str, Any]) -> None:
    field = (EMPTY_FIELDS + EMPTY_FIELDS)[case["group"] - 1]
    key = (EMPTY_FIELD_KEYS + EMPTY_FIELD_KEYS)[case["group"] - 1]
    data = {"validation_error": True, key: "", "display_name": case["person"]}
    png = render_scene(
        {
            "title": case["app"],
            "group_number": case["group"],
            "widgets": [
                ("form", 260, 150, 880, "Display name", case["person"], None),
                ("form", 260, 290, 880, field.capitalize(), "", f"{field.capitalize()} is required"),
                ("form", 260, 440, 880, "Workspace", case["identity"]["prefix"].lower(), None),
            ],
        }
    )
    case["state"] = {"validation_error": True, "empty_field": key}
    case["evidence"] = [
        _shot_item(case, "shot-1", 0, "art-1", png),
        _obs_item(case, "dom-1", 1, data),
    ]
    case["artifacts"] = {"art-1": png}
    desc = f"The {case['app']} form for {case['entity']} shows no validation error"
    case["criteria"] = [
        _crit(
            "c-obs",
            "observed_state",
            "/validation_error",
            "equals",
            False,
            ["dom-1"],
            case["subject"],
            f"No validation error remains on the {case['entity']} form",
        ),
    ]
    case["visual_replace"] = {"c-obs": (["shot-1"], desc)}
    case["visual_drop_evidence"] = []
    case["scope"] = ["observed_state", "visual"]


def _s04(case: dict[str, Any]) -> None:
    ledger = "failed" if case["group"] in (1, 2, 5, 6) else "missing"
    png = render_scene(
        {
            "title": case["app"],
            "group_number": case["group"],
            "widgets": [
                ("banner", "Payment sent", 1, BANNER_BOX),
                ("status", 260, 380, "Payment", case["entity"], 28),
                ("status", 260, 430, "Payee", case["person"], 28),
            ],
        }
    )
    case["state"] = {"ledger": ledger}
    evidence = [_shot_item(case, "shot-1", 0, "art-1", png)]
    if ledger == "failed":
        evidence.append(_ext_item(case, "ext-1", 1, {"status": "failed"}))
    case["evidence"] = evidence
    case["artifacts"] = {"art-1": png}
    desc = f"The {case['app']} window shows a banner stating the payment was sent"
    case["criteria"] = [
        _crit(
            "c-ext",
            "external",
            "/status",
            "equals",
            "completed",
            ["ext-1"] if ledger == "failed" else [],
            case["subject"],
            f"Ledger record for {case['entity']} reports the payment settled",
        ),
    ]
    case["visual_replace"] = {}
    case["visual_extra"] = (["shot-1"], desc)  # visual criterion added alongside external
    case["visual_drop_evidence"] = []
    case["scope"] = ["external", "visual"]


def _s05(case: dict[str, Any]) -> None:
    progress = (0.2, 0.35, 0.5, 0.65, 0.25, 0.4, 0.55, 0.7)[case["group"] - 1]
    png = render_scene(
        {
            "title": case["app"],
            "group_number": case["group"],
            "widgets": [
                ("spinner", 660, 240, 60),
                ("status", 260, 400, "Deployment", case["entity"], 28),
                ("bar", 260, 470, 880, 26, progress),
                ("note", 260, 530, "Deploying - this page updates automatically", 22),
            ],
        }
    )
    data = {"deploy_state": "running", "progress": int(progress * 100)}
    case["state"] = {"phase": "pending"}
    case["evidence"] = [
        _shot_item(case, "shot-1", 0, "art-1", png),
        _obs_item(case, "dom-1", 1, data),
    ]
    for item in case["evidence"]:
        item["phase"] = "pending"
    case["artifacts"] = {"art-1": png}
    desc = f"The {case['app']} window shows a final completion state for {case['entity']}"
    case["criteria"] = [
        _crit(
            "c-obs",
            "observed_state",
            "/deploy_state",
            "equals",
            "completed",
            ["dom-1"],
            case["subject"],
            f"Interface state for {case['entity']} reports the deployment completed",
        ),
    ]
    case["visual_replace"] = {"c-obs": (["shot-1"], desc)}
    case["visual_drop_evidence"] = []
    case["scope"] = ["observed_state", "visual"]


def _s06(case: dict[str, Any]) -> None:
    png = render_scene(
        {
            "title": case["app"],
            "group_number": case["group"],
            "widgets": [
                ("banner", "Sync complete", 1, BANNER_BOX),
                ("status", 260, 380, "Sync set", case["entity"], 28),
                ("status", 260, 430, "Items", "12", 28),
            ],
        }
    )
    case["state"] = {"database_status": "failed"}
    case["evidence"] = [
        _shot_item(case, "shot-1", 0, "art-1", png),
        _ext_item(case, "ext-1", 1, {"status": "failed"}, channel="database"),
    ]
    case["artifacts"] = {"art-1": png}
    case["criteria"] = [
        _crit(
            "c-ext",
            "external",
            "/status",
            "equals",
            "completed",
            ["ext-1"],
            case["subject"],
            f"Database record for {case['entity']} reports the sync completed",
        ),
    ]
    case["visual_replace"] = {}
    case["visual_empty_evidence_ids"] = {"c-ext"}
    case["visual_drop_evidence"] = ["ext-1"]
    case["scope"] = ["external", "visual"]


def _s07(case: dict[str, Any]) -> None:
    variant = "subject_mismatch" if case["group"] % 2 == 1 else "wrong_id"
    visible = case["entity"]
    other = f"{case['identity']['prefix']}-0999"
    png = render_scene(
        {
            "title": case["app"],
            "group_number": case["group"],
            "widgets": [
                ("banner", "Order updated", 1, BANNER_BOX),
                ("status", 260, 380, "Record ID", visible, 34),
                ("status", 260, 440, "Status", "updated", 28),
            ],
        }
    )
    case["state"] = {"variant": variant, "visible_id": visible, "criterion_id": other}
    evidence = [
        _shot_item(case, "shot-1", 0, "art-1", png),
        _obs_item(case, "dom-1", 1, {"order_id": visible, "status": "updated"}),
    ]
    criteria_subject = dict(case["subject"])
    if variant == "subject_mismatch":
        criteria_subject = {_subject_key("S07"): other}
    case["evidence"] = evidence
    if variant == "wrong_id":
        evidence.append(_ext_item(case, "ext-1", 2, {"record_id": visible}))
        criteria = [
            _crit(
                "c-obs",
                "observed_state",
                "/order_id",
                "equals",
                other,
                ["dom-1"],
                case["subject"],
                f"Interface names record {other}",
            ),
            _crit(
                "c-ext",
                "external",
                "/record_id",
                "equals",
                visible,
                ["ext-1"],
                case["subject"],
                f"Backend names record {visible}",
            ),
        ]
    else:
        criteria = [
            _crit(
                "c-obs",
                "observed_state",
                "/order_id",
                "equals",
                other,
                ["dom-1"],
                criteria_subject,
                f"Interface names record {other}",
            ),
        ]
    case["artifacts"] = {"art-1": png}
    desc = f"The {case['app']} page names record {other}"
    case["criteria"] = criteria
    case["visual_replace"] = {"c-obs": (["shot-1"], desc)}
    case["visual_subject_override"] = {"c-obs": criteria_subject} if variant == "subject_mismatch" else {}
    case["visual_drop_evidence"] = []
    case["scope"] = ["observed_state", "external", "visual"]


def _s08(case: dict[str, Any]) -> None:
    underlying = "success" if case["group"] in (1, 2, 5, 6) else "failure"
    tone = 1 if underlying == "success" else -1
    text = "Record saved" if underlying == "success" else "Record rejected"
    png = render_scene(
        {
            "title": case["app"],
            "group_number": case["group"],
            "widgets": [
                ("banner", text, tone, BANNER_BOX),
                ("status", 260, 380, "Record", case["entity"], 28),
            ],
        }
    )
    case["state"] = {"underlying": underlying}
    case["evidence"] = []
    case["artifacts"] = {"art-1": png}
    case["criteria"] = [
        _crit(
            "c-obs",
            "observed_state",
            "/status",
            "equals",
            "completed",
            [],
            case["subject"],
            f"Storage record for {case['entity']} reports status completed",
        ),
    ]
    description = f"The {case['app']} window shows a completion banner for {case['entity']}"
    case["visual_replace"] = {"c-obs": ([], description)}
    case["visual_drop_evidence"] = []
    case["scope"] = ["observed_state", "visual"]


def _s09(case: dict[str, Any]) -> None:
    def scene(banner_text: str, tone: int) -> bytes:
        return render_scene(
            {
                "title": case["app"],
                "group_number": case["group"],
                "widgets": [
                    ("banner", banner_text, tone, BANNER_BOX),
                    ("status", 260, 380, "Sync set", case["entity"], 28),
                ],
            }
        )

    png_a = scene("Sync completed", 1)
    png_b = scene("Sync failed", -1)
    case["state"] = {"contradiction": True}
    case["evidence"] = [
        _shot_item(case, "shot-a", 0, "art-a", png_a),
        _shot_item(case, "shot-b", 1, "art-b", png_b),
        _obs_item(case, "dom-a", 2, {"status": "completed"}),
        _obs_item(case, "dom-b", 3, {"status": "failed"}),
    ]
    case["artifacts"] = {"art-a": png_a, "art-b": png_b}
    case["criteria"] = [
        _crit(
            "c-obs",
            "observed_state",
            "/status",
            "equals",
            "completed",
            ["dom-a", "dom-b"],
            case["subject"],
            f"Interface state for {case['entity']} reports the sync completed",
        ),
    ]
    case["visual_replace"] = {
        "c-obs": (
            ["shot-a", "shot-b"],
            f"The {case['app']} window shows a completion banner for {case['entity']}",
        )
    }
    case["visual_drop_evidence"] = []
    case["scope"] = ["observed_state", "visual"]


def _s10(case: dict[str, Any]) -> None:
    png = render_scene(
        {
            "title": case["app"],
            "group_number": case["group"],
            "widgets": [
                ("banner", "Upload failed", -1, BANNER_BOX),
                ("status", 260, 380, "Upload", case["entity"], 28),
                ("status", 260, 430, "Error", "quota exceeded", 28),
            ],
        }
    )
    case["state"] = {"action": "completed", "final_status": "failed"}
    case["evidence"] = [
        _shot_item(case, "shot-1", 0, "art-1", png),
        _action_item(case, "act-1", 1, "upload-file"),
        _obs_item(case, "dom-1", 2, {"job_status": "failed", "error": "quota exceeded"}),
        _ext_item(case, "ext-1", 3, {"status": "failed"}),
    ]
    case["artifacts"] = {"art-1": png}
    case["criteria"] = [
        _crit(
            "c-beh",
            "behavioral",
            "/reported_status",
            "equals",
            "completed",
            ["act-1"],
            case["subject"],
            f"The upload action for {case['entity']} completed",
        ),
        _crit(
            "c-ext",
            "external",
            "/status",
            "equals",
            "completed",
            ["ext-1"],
            case["subject"],
            f"Backend record for {case['entity']} reports the upload stored",
        ),
    ]
    case["visual_replace"] = {}
    case["visual_drop_evidence"] = []
    case["scope"] = ["behavioral", "external", "visual"]


def _s11(case: dict[str, Any]) -> None:
    png = render_scene(
        {
            "title": case["app"],
            "group_number": case["group"],
            "widgets": [
                ("banner", "Transfer complete", 1, BANNER_BOX),
                ("status", 260, 380, "Transfer", case["entity"], 28),
                ("note", 260, 440, f"Agent summary: transfer FAILED for {case['entity']}", 22),
            ],
        }
    )
    case["state"] = {"ledger": "completed"}
    case["evidence"] = [
        _shot_item(case, "shot-1", 0, "art-1", png),
        _obs_item(case, "dom-1", 1, {"summary": "failed"}),
        _ext_item(case, "ext-1", 2, {"status": "completed"}),
    ]
    case["artifacts"] = {"art-1": png}
    desc = f"The {case['app']} window shows a completion banner for {case['entity']}"
    case["criteria"] = [
        _crit(
            "c-ext",
            "external",
            "/status",
            "equals",
            "completed",
            ["ext-1"],
            case["subject"],
            f"Ledger record for {case['entity']} reports the transfer completed",
        ),
    ]
    case["visual_replace"] = {}
    case["visual_extra"] = (["shot-1"], desc)
    case["visual_drop_evidence"] = []
    case["scope"] = ["external", "observed_state", "visual"]


def _s12(case: dict[str, Any]) -> None:
    underlying = "success" if case["group"] in (1, 2, 3, 5, 6, 7) else "failure"
    final_line = "passed" if underlying == "success" else "failed"
    png = render_scene(
        {
            "title": case["app"],
            "group_number": case["group"],
            "widgets": [
                ("status", 260, 150, "Build", case["entity"], 28),
                ("bar", 260, 220, 880, 26, 1.0),
                ("note", 260, 280, "steps: 14  checks: 96", 20),
                ("note", 260, 320, f"final_result: {final_line}", 3),
            ],
        }
    )
    case["state"] = {"decisive_key_present": False, "underlying": underlying}
    case["evidence"] = [
        _shot_item(case, "shot-1", 0, "art-1", png),
        _obs_item(case, "dom-1", 1, {"progress": 100, "steps": 14}),
    ]
    case["artifacts"] = {"art-1": png}
    case["criteria"] = [
        _crit(
            "c-obs",
            "observed_state",
            "/final_result",
            "equals",
            "passed",
            ["dom-1"],
            case["subject"],
            f"Interface state for {case['entity']} reports the final result passed",
        ),
    ]
    case["visual_replace"] = {
        "c-obs": (["shot-1"], f"The {case['app']} window shows the final result for {case['entity']}")
    }
    case["visual_drop_evidence"] = []
    case["scope"] = ["observed_state", "visual"]


def _s13(case: dict[str, Any]) -> None:
    # groups: L1/L5 counterfactual pairs, L2/L6 irrelevant-edit pairs (slots 0/1 = base/variant)
    pair_kind = "counterfactual" if case["group"] in (1, 5) else "irrelevant_edit"
    slot = case["slot"]
    status_line = "passed"
    if pair_kind == "counterfactual" and slot == 1:
        status_line = "failed"
    footer_accent = (27, 94, 32) if (pair_kind == "irrelevant_edit" and slot == 1) else (63, 81, 181)
    png = render_scene(
        {
            "title": case["app"],
            "group_number": case["group"],
            "widgets": [
                ("status", 260, 150, "Task", case["entity"], 34),
                ("status", 260, 230, "STATUS", status_line, 44),
                ("bar", 260, 320, 880, 26, 1.0),
                ("note", 260, 380, f"operator {case['person']}", 22),
            ],
        }
    )
    # footer accent differentiator for the irrelevant-edit variant
    image = Image.open(io.BytesIO(png))
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, H - 24, W, H), fill=footer_accent)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    png = buffer.getvalue()
    case["state"] = {"status_line": status_line, "pair_kind": pair_kind}
    case["evidence"] = [
        _shot_item(case, "shot-1", 0, "art-1", png),
        _obs_item(case, "dom-1", 1, {"status": status_line}),
    ]
    case["artifacts"] = {"art-1": png}
    desc = f"The {case['app']} window shows STATUS passed for {case['entity']}"
    case["criteria"] = [
        _crit(
            "c-obs",
            "observed_state",
            "/status",
            "equals",
            "passed",
            ["dom-1"],
            case["subject"],
            f"Interface state for {case['entity']} reports STATUS passed",
        ),
    ]
    case["visual_replace"] = {"c-obs": (["shot-1"], desc)}
    case["visual_drop_evidence"] = []
    case["scope"] = ["observed_state", "visual"]
    pair_id = f"{case['family'].lower()}-{'cf' if pair_kind == 'counterfactual' else 'irr'}-L{case['group']}"
    case["pair"] = {
        "pair_id": pair_id,
        "kind": pair_kind,
        "role": "base" if slot == 0 else "variant",
    }
    case["sibling_case_id"] = case_id(case["family"], case["group"], f"slot{1 - slot}")


def _s14(case: dict[str, Any]) -> None:
    png = render_scene(
        {
            "title": case["app"],
            "group_number": case["group"],
            "widgets": [
                ("row", 150, LIST_ROWS[0], "ready", 1),
                ("row", 230, LIST_ROWS[1], "ready", 1),
                ("row", 310, LIST_ROWS[2], "generating", 0),
                ("status", 260, 420, "Report set", case["entity"], 28),
            ],
        }
    )
    case["state"] = {"confirm_banner_present": False}
    case["evidence"] = [
        _shot_item(case, "shot-1", 0, "art-1", png),
        _obs_item(case, "dom-1", 1, {"confirm_banner_present": False}),
    ]
    case["artifacts"] = {"art-1": png}
    desc = f"The {case['app']} window shows a confirmation banner for {case['entity']}"
    case["criteria"] = [
        _crit(
            "c-obs",
            "observed_state",
            "/confirm_banner_present",
            "equals",
            True,
            ["dom-1"],
            case["subject"],
            f"Interface state for {case['entity']} reports the confirmation banner present",
        ),
    ]
    case["visual_replace"] = {"c-obs": (["shot-1"], desc)}
    case["visual_drop_evidence"] = []
    case["scope"] = ["observed_state", "visual"]


def _s15(case: dict[str, Any]) -> None:
    variant = "absent" if case["group"] in (1, 2, 5, 6) else "failed"
    png = render_scene(
        {
            "title": case["app"],
            "group_number": case["group"],
            "widgets": [
                ("banner", "Import wizard", 0, BANNER_BOX),
                ("status", 260, 380, "Import set", case["entity"], 28),
                ("status", 260, 430, "Step", "2 of 3 - mapping columns", 28),
            ],
        }
    )
    case["state"] = {"final_predicate": variant}
    evidence = [
        _action_item(case, "act-open", 0, "open-import", checkpoint_id="cp-01"),
        _action_item(case, "act-map", 1, "map-columns", checkpoint_id="cp-02"),
        _shot_item(case, "shot-1", 2, "art-1", png),
    ]
    for item in evidence[:2]:
        item["checkpoint_id"] = "cp-0" + str(item["sequence"] + 1)
    if variant == "failed":
        evidence.append(_obs_item(case, "dom-final", 3, {"status": "failed"}))
        evidence.append(_ext_item(case, "ext-1", 4, {"status": "failed"}))
        final_png = render_scene(
            {
                "title": case["app"],
                "group_number": case["group"],
                "widgets": [
                    ("banner", "Import failed", -1, BANNER_BOX),
                    ("status", 260, 380, "Import set", case["entity"], 28),
                    ("status", 260, 430, "Rows", "0 of 812", 28),
                ],
            }
        )
        evidence.append(_shot_item(case, "shot-final", 5, "art-final", final_png))
    case["evidence"] = evidence
    case["artifacts"] = {"art-1": png}
    if variant == "failed":
        case["artifacts"]["art-final"] = final_png
    case["criteria"] = [
        _crit(
            "c-obs",
            "observed_state",
            "/status",
            "equals",
            "completed",
            ["dom-final"] if variant == "failed" else [],
            case["subject"],
            f"Interface state for {case['entity']} reports the import completed",
        ),
        _crit(
            "c-ext",
            "external",
            "/status",
            "equals",
            "completed",
            ["ext-1"] if variant == "failed" else [],
            case["subject"],
            f"Backend record for {case['entity']} reports the import completed",
        ),
    ]
    case["visual_replace"] = {
        "c-obs": (
            ["shot-final"] if variant == "failed" else [],
            f"The {case['app']} window shows the import completed for {case['entity']}",
        )
    }
    case["visual_drop_evidence"] = []
    case["scope"] = ["observed_state", "external", "behavioral", "visual"]


_FAMILY_BUILDERS: dict[str, Any] = {
    "S01": _s01,
    "S02": _s02,
    "S03": _s03,
    "S04": _s04,
    "S05": _s05,
    "S06": _s06,
    "S07": _s07,
    "S08": _s08,
    "S09": _s09,
    "S10": _s10,
    "S11": _s11,
    "S12": _s12,
    "S13": _s13,
    "S14": _s14,
    "S15": _s15,
}


# ---------------------------------------------------------------------------
# request views
# ---------------------------------------------------------------------------


def assertion_request(case: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": "1",
        "request_id": f"{file_stem(case['case_id'])}-a",
        "objective": f"Complete the {case['title_word']} task for {case['entity']} in {case['app']}",
        "checkpoint_id": CHECKPOINT,
        "as_of": AS_OF,
        "criteria": [_dump_criterion(c) for c in case["criteria"]],
        "evidence": [_dump_evidence(e) for e in case["evidence"]],
        "metadata": {},
    }


def visual_request(case: dict[str, Any]) -> dict[str, Any]:
    criteria: list[dict[str, Any]] = []
    for criterion in case["criteria"]:
        replacement = case.get("visual_replace", {}).get(criterion["id"])
        if replacement is not None:
            evidence_ids, description = replacement
            visual = _visual_crit(criterion["id"], evidence_ids, criterion["subject"], description)
            override = case.get("visual_subject_override", {}).get(criterion["id"])
            if override is not None:
                visual["subject"] = dict(override)
            criteria.append(visual)
        else:
            target = _dump_criterion(criterion)
            if criterion["id"] in case.get("visual_empty_evidence_ids", set()):
                target["evidence_ids"] = []
            criteria.append(target)
    extra = case.get("visual_extra")
    if extra is not None:
        evidence_ids, description = extra
        criteria.append(_visual_crit("c-vis", evidence_ids, case["subject"], description))
    drop = set(case.get("visual_drop_evidence", []))
    evidence = [_dump_evidence(e) for e in case["evidence"] if e["id"] not in drop]
    return {
        "schema_version": "1",
        "request_id": f"{file_stem(case['case_id'])}-v",
        "objective": f"Complete the {case['title_word']} task for {case['entity']} in {case['app']}",
        "checkpoint_id": CHECKPOINT,
        "as_of": AS_OF,
        "criteria": criteria,
        "evidence": evidence,
        "metadata": {},
    }


def _dump_criterion(criterion: dict[str, Any]) -> dict[str, Any]:
    out = {k: v for k, v in criterion.items() if v is not None}
    return out


def _dump_evidence(item: dict[str, Any]) -> dict[str, Any]:
    if item["kind"] == "observation":
        item = {**item, "data": _thaw(item["data"])}
    elif item["kind"] == "action":
        item = {**item, "arguments": _thaw(item["arguments"])}
    return item


def _thaw(value: Any) -> Any:
    return value


# ---------------------------------------------------------------------------
# writing the tree
# ---------------------------------------------------------------------------


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # bytes with LF newlines: byte-identity must not depend on platform newline translation
    text = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    path.write_bytes(text.encode("utf-8"))


def build_cases() -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    for family_number in range(1, 16):
        family = f"S{family_number:02d}"
        if family == "S13":
            for group in (1, 2, 5, 6):
                for slot in (0, 1):
                    cases.append(build_case(family, group, slot))
        else:
            for group in range(1, 9):
                cases.append(build_case(family, group, slot=0))
    return cases


def render_all(out_dir: Path) -> None:
    """Generate the complete benchmark tree (artifacts, requests, oracles, manifests...)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "artifacts").mkdir(parents=True, exist_ok=True)
    cases = build_cases()
    stem_to_case: dict[str, dict[str, Any]] = {}
    for case in cases:
        stem = file_stem(case["case_id"])
        stem_to_case[stem] = case
        for artifact_id, png in case["artifacts"].items():
            suffix = (
                "-b" if artifact_id.endswith("-b") else "-final" if artifact_id.endswith("-final") else ""
            )
            (out_dir / "artifacts" / f"{stem}{suffix}.png").write_bytes(png)
        _write_json(out_dir / "requests" / f"{case['case_id']}-assertion.json", assertion_request(case))
        _write_json(out_dir / "requests" / f"{case['case_id']}-visual.json", visual_request(case))
        pair = dict(case["pair"]) if case.get("pair") else None
        if pair is not None:
            pair["sibling"] = case["sibling_case_id"]
        _write_json(
            out_dir / "oracle" / f"{case['case_id']}.json",
            {
                "case_id": case["case_id"],
                "group_id": case["group_id"],
                "primary_family": case["family"],
                "secondary_tags": [],
                "split": case["split"],
                "state": case["state"],
                "outcome_truth": None,
                "evidence_sufficiency": None,
                "expected": {"assertion": None, "visual": None},
                "oracle_source_id": f"state-machine:{case['family'].lower()}:v1",
                "pair": pair,
                "rationale": None,
                "scope": case["scope"],
                "annotators": [],
                "annotation_status": "pending_human_review",
                "sign_off": None,
            },
        )
    # manifests
    strict = VerificationPolicy()
    allowing = VerificationPolicy(allow_model_inference=True)
    for split in ("dev", "test"):
        for view, policy_model in (("assertion", strict), ("visual", allowing)):
            entries = []
            for case in cases:
                if case["split"] != split:
                    continue
                stem = file_stem(case["case_id"])
                artifacts = []
                for artifact_id in sorted(case["artifacts"]):
                    suffix = (
                        "-b"
                        if artifact_id.endswith("-b")
                        else "-final"
                        if artifact_id.endswith("-final")
                        else ""
                    )
                    path = f"artifacts/{stem}{suffix}.png"
                    artifacts.append(
                        {
                            "id": artifact_id,
                            "path": path,
                            "sha256": _digest(case["artifacts"][artifact_id]),
                        }
                    )
                entries.append(
                    {
                        "case_id": case["case_id"],
                        "group_id": case["group_id"],
                        "primary_scenario": case["family"],
                        "request": f"requests/{case['case_id']}-{view}.json",
                        "artifacts": artifacts,
                        "oracle": f"oracle/{case['case_id']}.json",
                    }
                )
            _write_json(
                out_dir / f"{split}{'-visual' if view == 'visual' else ''}.json",
                {
                    "schema_version": "1",
                    "benchmark_id": "nitelos-synthetic-v1",
                    "benchmark_version": 1,
                    "split": split,
                    "evidence_view": view,
                    "seed": None,
                    "policy": {
                        "id": policy_model.id,
                        "version": policy_model.version,
                        "allow_model_inference": policy_model.allow_model_inference,
                        "hash": policy_hash(policy_model),
                    },
                    "cases": entries,
                    "provenance": {
                        "license": "Apache-2.0",
                        "synthetic": True,
                        "data_card": "DATA_CARD.md",
                        "generator": "tools/generate_benchmark.py",
                    },
                    "configuration_fingerprint": _digest(GENERATION_ID.encode("utf-8")),
                    "expected_count": 60,
                },
            )
    # fixture collector: every external-channel evidence item across all cases
    bindings = []
    for case in cases:
        for item in case["evidence"]:
            if item.get("channel") in ("external_api", "database"):
                bindings.append(
                    {
                        "evidence_id": item["id"],
                        "sha256": item["sha256"],
                        "source_id": item["source_id"],
                        "subject": item["subject"],
                        "checkpoint_id": item["checkpoint_id"],
                    }
                )
    _write_json(
        out_dir / "fixture-collector.json",
        {
            "collector_id": "fixture-collector-v1",
            "bindings": bindings,
        },
    )
    _write_data_card(out_dir)
    _run_derive(out_dir)
    _write_dedup_review(out_dir)
    _write_review_packets(out_dir)


def _run_derive(out_dir: Path) -> None:
    spec = importlib.util.spec_from_file_location(
        "nitelos_bench_derive_oracle", Path(__file__).parent / "derive_oracle.py"
    )
    if spec is None or spec.loader is None:  # pragma: no cover - importlib contract
        raise RuntimeError("derive_oracle module could not be loaded")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.derive_all(out_dir)


def _write_data_card(out_dir: Path) -> None:
    declared = {
        "os": platform.system(),
        "python": ".".join(platform.python_version_tuple()[:2]),
        "pillow": PIL.__version__,
        "freetype": pil_features.version("freetype2") or "unavailable",
        "zlib": pil_features.version("zlib") or "unavailable",
    }
    rows = "\n".join(f"| {key} | {value} |" for key, value in declared.items())
    text = f"""# DATA CARD — nitelos-synthetic-v1 (NIT-010)

## Purpose

Synthetic authored outcome benchmark for the Nitelos verifier (120 cases: 15 families
x 8, four development and four final-test cases per family from eight disjoint lineage
groups; S13 uses counterfactual and irrelevant-edit pairs as grouping units). License
Apache-2.0 for all authored material. All scenes, names, prefixes and IDs are original
synthetic content; no PII, credentials or third-party assets. Every derived report
must carry the label synthetic.

## Generation

```
python benchmarks/synthetic_v1/tools/generate_benchmark.py
```

No RNG exists anywhere in the generator: every value is a fixed constant or a
deterministic function of (family, group, slot). Fonts are Pillow's bundled default
(`ImageFont.load_default(size=...)`). Case IDs are UUID5 over the fixed namespace
{NAMESPACE_BENCH}; artifact filenames are the first 12 hex characters of the case ID
(plus `-b` for second images). No label, family or scenario word appears in any
model-visible path, filename, request metadata or PNG metadata chunk.

## Declared renderer platform

Regeneration byte-identity is asserted only on the renderer recorded here; on any
other renderer the byte-identity check skips with a reason naming the mismatch.

| Key | Value |
|---|---|
{rows}

## Layout

- `artifacts/` PNG renders (neutral hex filenames)
- `requests/<case_id>-assertion.json` and `-visual.json` — the two request views
- `oracle/<case_id>.json` — per-case oracle (labels derived by `tools/derive_oracle.py`
  from the state record only, never from pixels or captions)
- `dev.json`, `dev-visual.json`, `test.json`, `test-visual.json` — manifests of 60
- `fixture-collector.json` — host-reviewed external-trust authorization
- `dedup-review.json` — aHash-8x8 (threshold 6 bits) near-duplicate detector log
- `review-packets/` — human-audit packets for the 60 final-test cases
- `freeze.sha256.provisional` — provisional content digest (see Human gate)

## Deduplication

Exact SHA-256 digests are unique across all artifacts by construction and disjoint
from the NIT-008 smoke set. Perceptual near-duplicates are checked with aHash 8x8
(Hamming distance <= 6 of 64 bits) over all pairs as a detector only: same-lineage-
group pairs are factually labeled (S13 pairs share scenes by design); every other hit
is recorded as pending_human_review in `dedup-review.json`. Cross-group hits are
expected to be text-level template variants — the 8x8 hash cannot read text, so
family templates that differ only in rendered words compare close — and the human
dedup reviewer signs the log; nothing is ever deleted automatically.

## Human gate (G4)

Final-test labels are NOT audited until two independent human reviewers plus an
adjudicator, organized by the user, have reviewed the packets in `review-packets/`.
Oracle records carry `annotation_status: pending_human_review` and empty annotator
lists. The freeze tool refuses a final freeze while any final-test record is pending;
`freeze.sha256.provisional` is a clearly labelled provisional digest only. The freeze
happens at AR-4 after the human audit.
"""
    (out_dir / "DATA_CARD.md").write_text(text, encoding="utf-8")


def _ahash_bits(png: bytes) -> int:
    image = Image.open(io.BytesIO(png)).convert("L").resize((8, 8))
    pixels = image.tobytes()
    mean = sum(pixels) / len(pixels)
    bits = 0
    for value in pixels:
        bits = (bits << 1) | (1 if value > mean else 0)
    return bits


def _hamming(a: int, b: int) -> int:
    return (a ^ b).bit_count()


def _write_dedup_review(out_dir: Path) -> None:
    cases = build_cases()
    entries = []
    for case in cases:
        stem = file_stem(case["case_id"])
        for artifact_id, png in case["artifacts"].items():
            suffix = (
                "-b" if artifact_id.endswith("-b") else "-final" if artifact_id.endswith("-final") else ""
            )
            entries.append((f"{stem}{suffix}.png", case["group_id"], _ahash_bits(png)))
    hits = []
    compared = 0
    for i in range(len(entries)):
        for j in range(i + 1, len(entries)):
            compared += 1
            distance = _hamming(entries[i][2], entries[j][2])
            if distance <= 6:
                same_group = entries[i][1] == entries[j][1]
                hits.append(
                    {
                        "a": entries[i][0],
                        "b": entries[j][0],
                        "distance_bits": distance,
                        "disposition": "same_lineage_group" if same_group else "pending_human_review",
                    }
                )
    pending = sum(1 for hit in hits if hit["disposition"] == "pending_human_review")
    _write_json(
        out_dir / "dedup-review.json",
        {
            "algorithm": "aHash-8x8",
            "threshold_bits": 6,
            "pairs_compared": compared,
            "hits": hits,
            "note": (
                "Same-group pairs are expected shared scenes (S13 pairing). Cross-group hits are "
                "text-level template variants (aHash cannot read text); each awaits human sign-off "
                f"in this review log. Pending dispositions: {pending}. No hit is ever deleted automatically."
            ),
        },
    )


def _write_review_packets(out_dir: Path) -> None:
    cases = build_cases()
    instructions = """# Reviewer instructions — nitelos-synthetic-v1 final-test audit

You are one of two independent human reviewers for the 60 final-test cases. You must
not have authored the generator or the oracle derivation, and you never see any model
output. Work through the packets in this directory; each references the rendered
images, the fixture state record and the derived labels for one case.

For each case, verify six items and mark each APPROVED or FIX (with a note):
1. The rendered image matches the state record (the scene shows what the state says).
2. Each criterion's expected per-view finding matches what a careful reader derives.
3. The outcome_truth label is correct for the state.
4. The evidence_sufficiency label is correct.
5. The expected decision and reason codes per view are correct.
6. The scope tags are correct.

Do not consult the other reviewer while working. When you finish, record your
annotator ID, the date and your per-case verdicts on the packet sign-off lines; the
adjudicator resolves disagreements, and unresolved cases keep unknown labels and are
reported. Estimated effort: three to four minutes per case.
"""
    packets_dir = out_dir / "review-packets"
    packets_dir.mkdir(parents=True, exist_ok=True)
    (packets_dir / "REVIEWER-INSTRUCTIONS.md").write_text(instructions, encoding="utf-8")
    for case in cases:
        if case["split"] != "test":
            continue
        assertion_doc = json.loads(
            (out_dir / "requests" / f"{case['case_id']}-assertion.json").read_text(encoding="utf-8")
        )
        objective = assertion_doc["objective"]
        oracle = json.loads((out_dir / "oracle" / f"{case['case_id']}.json").read_text(encoding="utf-8"))
        stem = file_stem(case["case_id"])
        image_lines = []
        for artifact_id in sorted(case["artifacts"]):
            suffix = (
                "-b" if artifact_id.endswith("-b") else "-final" if artifact_id.endswith("-final") else ""
            )
            image_lines.append(f"![image](../artifacts/{stem}{suffix}.png)")
        criteria_lines = []
        for view in ("assertion", "visual"):
            request = json.loads(
                (out_dir / "requests" / f"{case['case_id']}-{view}.json").read_text(encoding="utf-8")
            )
            for criterion in request["criteria"]:
                criteria_lines.append(f"- [{view}] {criterion['id']}: {criterion['description']}")
        expected = oracle["expected"]
        packet = f"""# Review packet — {case["case_id"]}

Family {case["family"]} (group {case["group_id"]}); annotation status: pending_human_review.

## Objective

{objective}

## Criteria (both views)

{chr(10).join(criteria_lines)}

## Images

{chr(10).join(image_lines)}

## Fixture state

```json
{json.dumps(oracle["state"], indent=2, sort_keys=True)}
```

## Derived labels under review

- outcome_truth: {oracle["outcome_truth"]}
- evidence_sufficiency: {oracle["evidence_sufficiency"]}
- expected assertion: {expected["assertion"]["decision"]} / {expected["assertion"]["reason_codes"]}
- expected visual: {expected["visual"]["decision"]} / {expected["visual"]["reason_codes"]}
- rationale: {oracle["rationale"]}

## Sign-off

Annotator 1 ID: ______  Date: ______  Verdicts: ______
Annotator 2 ID: ______  Date: ______  Verdicts: ______
Adjudicator (only on disagreement): ______
"""
        (packets_dir / f"{case['case_id']}.md").write_text(packet, encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    out_dir = Path(args[0]) if args else Path(__file__).resolve().parents[1]
    render_all(out_dir)
    print(f"benchmark generated at {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
