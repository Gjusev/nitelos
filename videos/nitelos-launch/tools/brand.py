"""Generate the nitelos logo set from the Archivo variable font (wdth 125, wght 700).

Run from this directory's parent:
    uv run --with fonttools --with uharfbuzz --with skia-pathops python tools/brand.py

Outputs SVG outlines (no font dependency) into assets/svg/ and the light-weight
README copies into ../../docs/assets/brand/.

Geometry rules (see BRAND.md):
- Every outline comes from Archivo, so mark and wordmark share one stem width (S).
- The evidence square is S x S. It replaces the foot of the n's right leg,
  separated from the cut leg by a gap G. The mark is that n alone; the
  wordmark is the same n followed by Archivo's own 'itelos'. One accent per logo.
"""

from __future__ import annotations

import io
import json
from pathlib import Path

import pathops
import uharfbuzz as hb
from fontTools.pens.recordingPen import RecordingPen
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont
from fontTools.varLib import instancer

HERE = Path(__file__).resolve().parents[1]
FONT = HERE / "assets" / "fonts" / "Archivo-VF.ttf"
OUT = HERE / "assets" / "svg"
DOCS = HERE.parents[1] / "docs" / "assets" / "brand"

PALETTES = {
    "dark": {"ink": "#F4F1E9", "accent": "#79BFFF"},
    "light": {"ink": "#101318", "accent": "#1F6FD1"},
}

font = instancer.instantiateVariableFont(TTFont(FONT), {"wdth": 125, "wght": 700})
glyphs = font.getGlyphSet()
cmap = font.getBestCmap()
ASCENDER = 724.2174072265625  # top of l, measured
STEM_LEFT, STEM_RIGHT = 68.6085205078125, 225.3055419921875
S = STEM_RIGHT - STEM_LEFT  # one stem: the evidence square side
G = 40.0  # gap between a cut stroke and its evidence square


def glyph_path(name: str) -> pathops.Path:
    rec = RecordingPen()
    glyphs[name].draw(rec)
    path = pathops.Path()
    pen = path.getPen()
    rec.replay(pen)
    return path


def rect(x0: float, y0: float, x1: float, y1: float) -> pathops.Path:
    p = pathops.Path()
    p.moveTo(x0, y0)
    p.lineTo(x1, y0)
    p.lineTo(x1, y1)
    p.lineTo(x0, y1)
    p.close()
    return p


def svg_d(path: pathops.Path, dx: float, baseline: float) -> str:
    pen = SVGPathPen(None)
    tpen = TransformPen(pen, (1, 0, 0, -1, dx, baseline))
    path.draw(tpen)
    return pen.getCommands()


def shaped(text: str) -> list[tuple[str, float]]:
    buf = io.BytesIO()
    font.save(buf)
    face = hb.Face(buf.getvalue())
    hfont = hb.Font(face)
    hbuf = hb.Buffer()
    hbuf.add_str(text)
    hbuf.guess_segment_properties()
    hb.shape(hfont, hbuf, {"kern": True, "liga": False})
    order = font.getGlyphOrder()
    x = 0.0
    out = []
    for info, pos in zip(hbuf.glyph_infos, hbuf.glyph_positions, strict=True):
        out.append((order[info.codepoint], x + pos.x_offset))
        x += pos.x_advance
    return out, x


def mark_paths() -> tuple[pathops.Path, pathops.Path]:
    """The n whose right leg stops short; the evidence square completes it."""
    n = glyph_path(cmap[ord("n")])
    right_outer = 666.392578125
    leg_left = right_outer - S
    cut_y = S + G
    body = pathops.op(n, rect(leg_left - 1, -50, right_outer + 50, cut_y), pathops.PathOp.DIFFERENCE)
    square = rect(leg_left, 0, right_outer, S)
    return body, square


def wordmark_paths() -> tuple[list[tuple[pathops.Path, float]], pathops.Path, float]:
    """nitelos whose n is the mark: its right leg stops short, the evidence square completes it."""
    run, advance = shaped("nitelos")
    m_body, m_square = mark_paths()
    ink = []
    square = None
    for name, x in run:
        if name == cmap[ord("n")] and square is None:
            ink.append((m_body, x))
            square = (x, m_square)
        else:
            ink.append((glyph_path(name), x))
    return ink, square, advance


def write(path: Path, body: str, w: float, h: float, title: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w:.0f} {h:.0f}" '
        f'role="img" aria-labelledby="t"><title id="t">{title}</title>{body}</svg>\n',
        encoding="utf-8",
    )


def build() -> None:
    pad = 60
    baseline = ASCENDER + pad
    height = ASCENDER + 2 * pad
    m_body, m_square = mark_paths()
    ink, (sq_x, sq_path), advance = wordmark_paths()
    n_left, n_right, n_top = 68.6085205078125, 666.392578125, 539.2174072265625

    for theme, pal in PALETTES.items():
        # mark: the n alone, tight square frame (side = glyph width + 2 * 0.12 S)
        mpad = 0.12 * S
        side = (n_right - n_left) + 2 * mpad
        mx = mpad - n_left
        mb = side - (side - n_top) / 2  # vertically centre the x-height
        mark = (
            f'<path fill="{pal["ink"]}" d="{svg_d(m_body, mx, mb)}"/>'
            f'<path fill="{pal["accent"]}" d="{svg_d(m_square, mx, mb)}"/>'
        )
        write(OUT / f"nitelos-mark-{theme}.svg", mark, side, side, "nitelos")

        # app tile: the mark on a ground-colour tile, for favicons and avatars
        tile = 1024
        scale = 0.62 * tile / (n_right - n_left)
        tx = (tile - (n_right - n_left) * scale) / 2 - n_left * scale
        ty = tile - (tile - n_top * scale) / 2
        ground = "#101318" if theme == "dark" else "#FFFFFF"
        body = (
            f'<rect width="{tile}" height="{tile}" rx="{0.18 * tile:.0f}" fill="{ground}"/>'
            # svg_d already flips y (font units grow upward), so the group scale stays positive
            f'<g transform="translate({tx:.2f} {ty:.2f}) scale({scale:.5f})">'
            f'<path fill="{pal["ink"]}" d="{svg_d(m_body, 0, 0)}"/>'
            f'<path fill="{pal["accent"]}" d="{svg_d(m_square, 0, 0)}"/></g>'
        )
        write(OUT / f"nitelos-tile-{theme}.svg", body, tile, tile, "nitelos")

        # wordmark (the primary logo)
        word = "".join(f'<path fill="{pal["ink"]}" d="{svg_d(p, pad + x, baseline)}"/>' for p, x in ink)
        square = f'<path fill="{pal["accent"]}" d="{svg_d(sq_path, pad + sq_x, baseline)}"/>'
        write(OUT / f"nitelos-wordmark-{theme}.svg", word + square, advance + 2 * pad, height, "nitelos")
        # animation part: the wordmark without its square; the films dock the square in separately
        write(OUT / f"nitelos-wordmark-{theme}-open.svg", word, advance + 2 * pad, height, "nitelos")

    # square geometry in wordmark viewBox units, for docking the square in motion pieces
    leg_left = 666.392578125 - S
    geometry = {
        "viewBox": [0, 0, round(advance + 2 * pad, 3), round(height, 3)],
        "square": {
            "x": round(pad + sq_x + leg_left, 3),
            "y": round(baseline - S, 3),
            "size": round(S, 3),
        },
    }
    (OUT / "nitelos-wordmark-geometry.json").write_text(
        json.dumps(geometry, indent=2) + "\n", encoding="utf-8"
    )

    for old in OUT.glob("nitelos-lockup-*.svg"):
        old.unlink()
    DOCS.mkdir(parents=True, exist_ok=True)
    for name in ("wordmark", "mark", "tile"):
        for theme in PALETTES:
            src = OUT / f"nitelos-{name}-{theme}.svg"
            (DOCS / src.name).write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    print(f"stem S={S:.1f} gap G={G:.0f} word advance={advance:.0f}")


if __name__ == "__main__":
    build()
