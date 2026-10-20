# Asset licenses

Every third-party file the launch films load, with its license and where it came from.
Nothing here was purchased; no paid service was used.

| Asset | Files | License | Source | Obligation |
|---|---|---|---|---|
| Archivo (variable, wght 100–900, wdth 62–125) | `fonts/Archivo-VF.ttf` | SIL OFL 1.1, `fonts/Archivo-OFL.txt` | Copyright 2020 The Archivo Project Authors, github.com/Omnibus-Type/Archivo | Ship the OFL text with the font file; do not sell the font by itself. The wordmark outlines in `svg/` are derived artwork, which OFL permits. |
| Martian Mono (variable) | `fonts/MartianMono-VF.ttf` | SIL OFL 1.1, `fonts/MartianMono-OFL.txt` | Copyright 2021 The Martian Mono Project Authors, github.com/evilmartians/mono | As above. |
| GSAP 3.14.2 | `vendor/gsap.min.js` | GreenSock Standard "no charge" license (header of the file) | gsap.com, terms at https://gsap.com/standard-license | Keep the license header in the file. |
| Music: "Happy Beats / Business Moves vol. 12" | `audio/happy-beats-business-moves-vol-12-by-ende-dot-app.mp3` | CC BY 4.0 with the author's "attribution optional" provision | Sascha Ende, ende.app (terms: https://ende.app/en/standard-license, checked 2026-10-20) | Credit is optional but given: "Music by Sascha Ende at ende.app" (in the films' README and the post credits). Not allowed: registering it with Content ID, or uploading it unchanged as a song. |
| SFX: `impactSoft_*`, `impactBell_heavy_000`, `click_003`, `click2`, `bong_001`, `card-slide-1` | `audio/sfx/*.ogg` | CC0 1.0 (public domain) | Kenney, kenney.nl (copied from the /brag skill bundle) | None. Credit given anyway. |

## Open point (not decided here)

The ende.app terms cover use *inside* a work (the films) but do not say whether the raw
MP3 may be redistributed on its own, e.g. committed to a public repository. Until that is
confirmed, `audio/*.mp3` is git-ignored and not in the repository. The rendered films
are fine; the raw file is the question. Fonts, GSAP and the Kenney SFX may be redistributed under the
terms above.
