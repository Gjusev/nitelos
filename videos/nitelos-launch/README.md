# nitelos launch films and brand kit

HTML/GSAP compositions rendered with HyperFrames. Everything on screen is English; every
factual line maps to [claims.md](claims.md); the examples are synthetic and the output
shown is real ([evidence/](evidence/commands.md)).

| File | What |
|---|---|
| [DESIGN.md](DESIGN.md) | Brand system: concept, logo rules, palette, type, motion |
| [storyboard.md](storyboard.md) | Main film, scene by scene |
| [claims.md](claims.md) | Every on-screen claim and its source |
| [manifest.json](manifest.json) | Every deliverable: size, duration, codecs, loudness, render command |
| [proofs/qa.md](proofs/qa.md) | QA gates, seam test, problems found and fixed |
| [assets/licenses.md](assets/licenses.md) | Fonts, GSAP, music, SFX: licenses and obligations |

Compositions: `workflow.html` (how it works in five steps, 24 s; source of the README
GIF), `index.html` (main, 30 s), `demo.html` (60 s), `vertical.html` (30 s),
`teaser.html` (8 s vertical), `loop.html` (6 s, silent), `kit-card.html`, `poster.html`,
`diagram-png.html` (stills).

## Rebuild

Renders are local only (`renders/` is git-ignored). Requirements: Node 20+, ffmpeg,
uv. The music track is not in the repository (see [assets/licenses.md](assets/licenses.md));
download "Happy Beats / Business Moves vol. 12" from ende.app and save it as
`assets/audio/happy-beats-business-moves-vol-12-by-ende-dot-app.mp3`. From this folder:

```bash
tools/stage.sh index.html check                     # lint, layout, contrast
tools/stage.sh index.html snapshot --at 3,14.5,28.5 # PNG frames + contact sheet
tools/stage.sh index.html render --quality delivery --output "$(pwd -W)/renders/nitelos-main-30s.raw.mp4"
tools/master.sh renders/nitelos-main-30s.raw.mp4 renders/nitelos-main-30s.mp4 17.2 stills/nitelos-main-poster.jpg
```

`stage.sh` copies a composition into `.stage/<name>/` with the shared `assets/`, because
the films use root-relative `/assets/...` URLs. `master.sh` measures loudness, applies the
gain plus a limiter to reach about −16 LUFS with true peak below −1 dBTP, and bakes the
poster frame into frame 0. The exact command for every deliverable is in `manifest.json`.

Brand files: `uv run --with fonttools --with uharfbuzz --with skia-pathops python tools/brand.py`
(wordmark, mark, tile, dark and light, into `assets/svg/` and `docs/assets/brand/`).
Diagram and state-card SVGs: `uv run python tools/diagram.py`.

Music by Sascha Ende at ende.app (CC BY 4.0). Sound effects by Kenney (CC0).
