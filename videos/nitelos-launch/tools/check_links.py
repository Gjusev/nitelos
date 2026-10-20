"""Check that every relative link, image and anchor in the public docs resolves.

    uv run python videos/nitelos-launch/tools/check_links.py   (from the repo root)

Covers Markdown links/images and HTML src/srcset/href attributes. External URLs are
listed, not fetched (no network). Exit code 1 on any broken target.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
FILES = [
    ROOT / "README.md",
    ROOT / "CONTRIBUTING.md",
    ROOT / "SECURITY.md",
    *sorted((ROOT / "docs").glob("*.md")),
    *sorted((ROOT / "docs" / "recipes").glob("*.md")),
    ROOT / "docs" / "planning" / "README.md",
    *sorted((ROOT / "videos" / "nitelos-launch").glob("*.md")),
    ROOT / "reports" / "v0.1" / "SUMMARY.md",
]
MD_LINK = re.compile(r"!?\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
HTML_ATTR = re.compile(r"(?:src|srcset|href)=\"([^\"]+)\"")
FENCE = re.compile(r"```.*?```", re.S)


def slug(heading: str) -> str:
    text = re.sub(r"[`*_]", "", heading.strip().lower())
    text = re.sub(r"[^\w\- ]", "", text)
    return text.replace(" ", "-")


def anchors(md: Path) -> set[str]:
    body = FENCE.sub("", md.read_text(encoding="utf-8"))
    return {slug(m.group(1)) for m in re.finditer(r"^#{1,6}\s+(.+)$", body, re.M)}


def main() -> int:
    broken, external, checked = [], set(), 0
    for md in FILES:
        if not md.exists():
            continue
        text = FENCE.sub("", md.read_text(encoding="utf-8"))
        targets = MD_LINK.findall(text) + HTML_ATTR.findall(text)
        for target in targets:
            if target.startswith(("http://", "https://", "mailto:")):
                external.add(target)
                continue
            checked += 1
            path_part, _, anchor = target.partition("#")
            dest = md if not path_part else (md.parent / path_part).resolve()
            if not dest.exists():
                broken.append(f"{md.relative_to(ROOT)} -> {target} (missing file)")
            elif anchor and dest.suffix == ".md" and anchor not in anchors(dest):
                broken.append(f"{md.relative_to(ROOT)} -> {target} (missing anchor)")
    print(f"checked {checked} relative targets in {sum(f.exists() for f in FILES)} files")
    print(f"external (listed, not fetched): {len(external)}")
    for url in sorted(external):
        print(f"  {url}")
    for line in broken:
        print(f"BROKEN {line}")
    return 1 if broken else 0


if __name__ == "__main__":
    sys.exit(main())
