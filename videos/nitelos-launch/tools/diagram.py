"""Generate the README 'how it works' diagram (dark and light) as accessible SVG.

    uv run python tools/diagram.py   (also writes stills/cards/nitelos-state-*.svg)

Real <text> (not outlines) so it stays searchable and screen-reader friendly; system
font stacks because GitHub renders README SVGs as images without web fonts. Colors
and the evidence-square motif come from DESIGN.md.
"""

from __future__ import annotations

from pathlib import Path

DOCS = Path(__file__).resolve().parents[3] / "docs" / "assets"

THEMES = {
    "dark": {
        "ground": "#101318",
        "panel": "#171B22",
        "ink": "#F4F1E9",
        "muted": "#8A93A3",
        "line": "#59616F",
        "evidence": "#79BFFF",
        "success": "#95D8AC",
        "refuted": "#FF877A",
        "abstained": "#F0C878",
    },
    "light": {
        "ground": "#FFFFFF",
        "panel": "#F3F4F6",
        "ink": "#101318",
        "muted": "#5A6271",
        "line": "#C9CED6",
        "evidence": "#1F6FD1",
        "success": "#1E7A47",
        "refuted": "#C2412F",
        "abstained": "#8A5A00",
    },
}
SANS = "ui-sans-serif, -apple-system, 'Segoe UI', Helvetica, Arial, sans-serif"
MONO = "ui-monospace, SFMono-Regular, Menlo, Consolas, 'Liberation Mono', monospace"


def svg(c: dict[str, str]) -> str:
    def t(x, y, s, size=20, fill=c["ink"], family=SANS, weight=400, anchor="start"):  # noqa: PLR0917 - SVG text helper, positional reads like markup
        return (
            f'<text x="{x}" y="{y}" font-family="{family}" font-size="{size}" font-weight="{weight}" '
            f'fill="{fill}" text-anchor="{anchor}">{s}</text>'
        )

    def box(x, y, w, h):
        return (
            f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="6" '
            f'fill="{c["panel"]}" stroke="{c["line"]}" stroke-width="2"/>'
        )

    def sq(x, y, s=14, fill=c["evidence"]):
        return f'<rect x="{x}" y="{y}" width="{s}" height="{s}" fill="{fill}"/>'

    def flow(x1, x2, y):
        # a trace that stops at the next box: line plus an end stop (the brand's motion verb)
        return (
            f'<path d="M{x1} {y} H{x2}" stroke="{c["evidence"]}" stroke-width="3" fill="none"/>'
            f'<path d="M{x2} {y - 11} V{y + 11}" stroke="{c["evidence"]}" stroke-width="4"/>'
        )

    parts = []  # transparent ground: the README page colour shows through in both GitHub themes

    # 1. your host
    parts += [
        box(40, 70, 470, 420),
        t(70, 116, "your host", 28, weight=650),
        t(70, 148, "agent runner, test harness, CI job", 18, c["muted"]),
        t(70, 200, "collects and normalizes the evidence:", 19, c["ink"]),
    ]
    for i, (k, v) in enumerate(
        [
            ("observation", "DOM / API state"),
            ("screenshot", "image + digest"),
            ("action", "what the tool reported"),
            ("external read", "+ TrustBinding"),
        ]
    ):
        y = 244 + i * 44
        parts += [sq(72, y - 13), t(98, y, k, 19, c["ink"], MONO), t(290, y, v, 18, c["muted"])]
    parts += [
        t(70, 446, "and writes the criteria:", 19, c["ink"]),
        t(70, 476, "/validation_error equals false", 18, c["evidence"], MONO),
    ]

    # 2. nitelos
    parts += [
        flow(510, 590, 280),
        box(590, 150, 420, 260),
        t(800, 214, "nitelos", 40, weight=700, anchor="middle"),
        t(800, 262, "Verifier().verify(request)", 19, c["ink"], MONO, anchor="middle"),
        t(800, 316, "checks every criterion against", 18, c["muted"], anchor="middle"),
        t(800, 342, "the evidence it was given", 18, c["muted"], anchor="middle"),
        t(800, 384, "no clicks, no fetches, no retries", 17, c["muted"], anchor="middle"),
    ]

    # 3. result
    parts += [
        flow(1010, 1090, 280),
        box(1090, 70, 470, 420),
        t(1120, 116, "result", 28, weight=650),
        t(1120, 160, "execution_status", 18, c["muted"], MONO),
        t(1340, 160, "ok", 18, c["ink"], MONO),
        t(1120, 206, "decision", 18, c["muted"], MONO),
    ]
    rows = [
        ("success", c["success"], "every criterion supported"),
        ("failure", c["refuted"], "a criterion refuted"),
        ("abstained", c["abstained"], "not enough evidence"),
    ]
    for i, (word, col, meaning) in enumerate(rows):
        y = 256 + i * 54
        if word == "abstained":
            mark = (
                f'<rect x="1122" y="{y - 19}" width="20" height="20" '
                f'fill="none" stroke="{col}" stroke-width="4"/>'
            )
        elif word == "failure":
            mark = (
                f'<rect x="1120" y="{y - 21}" width="24" height="24" fill="{col}"/>'
                f'<path d="M1120 {y + 3} L1144 {y - 21}" stroke="{c["panel"]}" stroke-width="4"/>'
            )
        else:
            mark = f'<rect x="1120" y="{y - 21}" width="24" height="24" fill="{col}"/>'
        parts += [mark, t(1160, y, word, 24, col, weight=650), t(1300, y, meaning, 18, c["muted"])]
    parts += [
        t(1120, 446, "plus the evidence references", 18, c["muted"]),
        t(1120, 474, "behind every decided criterion", 18, c["muted"]),
    ]

    body = "".join(parts)
    title = "How nitelos works"
    desc = (
        "Your host collects and normalizes evidence and writes the criteria. nitelos checks every criterion "
        "against that evidence, without clicking, fetching or retrying, and returns an execution status, "
        "a decision of success, failure or abstained, and the evidence references "
        "behind every decided criterion."
    )
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1600 560" role="img" '
        f'aria-labelledby="dt dd"><title id="dt">{title}</title><desc id="dd">{desc}</desc>{body}</svg>\n'
    )


LAUNCH = Path(__file__).resolve().parents[1]
CARDS = {  # real outputs from the three examples (evidence/*.stdout.txt)
    "success": (
        "Every criterion is supported by the evidence.",
        "['ALL_CRITERIA_SUPPORTED']",
        "quickstart.py",
    ),
    "failure": (
        "At least one criterion is refuted by the evidence.",
        "['CRITERION_REFUTED']",
        "demo_incomplete_form.py",
    ),
    "abstained": (
        "The evidence cannot decide a criterion, and none is refuted.",
        "['INSUFFICIENT_EVIDENCE', 'MISSING_EVIDENCE']",
        "demo_external_pending.py",
    ),
}


def card(state: str) -> str:
    """A 1200x630 decision-state card (dark), same layout as the kit-card.html PNG."""
    c = THEMES["dark"]
    col = c["refuted"] if state == "failure" else c[state]
    meaning, codes, example = CARDS[state]
    mark = (LAUNCH / "assets" / "svg" / "nitelos-wordmark-dark.svg").read_text(encoding="utf-8")
    mark = mark.replace("<svg ", '<svg x="80" y="72" width="180" height="37" ', 1)
    if state == "success":
        shape = f'<rect x="80" y="214" width="150" height="150" fill="{col}"/>'
    elif state == "failure":
        shape = (
            f'<rect x="80" y="214" width="150" height="150" fill="{col}"/>'
            f'<path d="M80 364 L230 214" stroke="{c["ground"]}" stroke-width="19"/>'
        )
    else:
        shape = (
            f'<rect x="91" y="225" width="128" height="128" fill="none" stroke="{col}" stroke-width="22"/>'
        )
    body = (
        f'<rect width="1200" height="630" fill="{c["ground"]}"/>{mark}{shape}'
        f'<text x="270" y="224" font-family="{MONO}" font-size="22" fill="{c["muted"]}">decision</text>'
        f'<text x="266" y="352" font-family="{SANS}" font-size="132" font-weight="700" '
        f'fill="{col}">{state}</text>'
        f'<text x="80" y="448" font-family="{SANS}" font-size="34" fill="{c["ink"]}">{meaning}</text>'
        f'<text x="80" y="506" font-family="{MONO}" font-size="22" fill="{c["muted"]}">'
        f"reason_codes: {codes}</text>"
        f'<text x="80" y="572" font-family="{MONO}" font-size="18" fill="{c["muted"]}">'
        f"real output · examples/{example}</text>"
    )
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1200 630" role="img" aria-labelledby="ct">'
        f'<title id="ct">nitelos decision: {state}. {meaning}</title>{body}</svg>\n'
    )


if __name__ == "__main__":
    DOCS.mkdir(parents=True, exist_ok=True)
    for theme, colors in THEMES.items():
        out = DOCS / f"how-it-works-{theme}.svg"
        out.write_text(svg(colors), encoding="utf-8")
        print(out.name, out.stat().st_size, "bytes")
    for state in CARDS:
        out = LAUNCH / "stills" / "cards" / f"nitelos-state-{state}.svg"
        out.write_text(card(state), encoding="utf-8")
        print(out.name, out.stat().st_size, "bytes")
