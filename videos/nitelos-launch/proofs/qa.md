# QA record

Visual overview of every deliverable: [contact-sheet.png](contact-sheet.png) (frames pulled
from the final mastered files with ffmpeg). Measurements are from the final files, not
the raw renders. Full numbers per file: `../manifest.json`.

## Gates per deliverable

| Deliverable | `hyperframes check` | Contrast (WCAG AA) | Frames / duration | Loudness (target −16 LUFS, TP ≤ −1 dBTP) |
|---|---|---|---|---|
| Main 30 s, 1920×1080 | pass, 0 errors | all text pairs pass | 900 / 30.016 s | −15.95 LUFS, −1.77 dBTP |
| Demo 60 s, 1920×1080 | pass, 0 errors | all pass | 1800 / 60.01 s | −16.06 LUFS, −1.81 dBTP |
| Vertical 30 s, 1080×1920 | pass, 0 errors | all pass | 900 / 30.016 s | −16.07 LUFS, −1.52 dBTP |
| Teaser 8 s, 1080×1920 | pass, 0 errors | 25/25 pass | 240 / 8.0 s | −16.14 LUFS, −1.33 dBTP |
| Workflow 24 s, 1920×1080 (README GIF, LinkedIn) | pass, 0 errors (an overflowing evidence label was shortened) | pass | 708 / 23.616 s | −16.06 LUFS, −1.22 dBTP |
| Loop 6 s, 1600×900, MP4 + WebM | pass, 0 errors, 0 warnings | n/a (no text pairs flagged) | 180 / 6.0 s, no audio | n/a |
| Stills: social card, 3 state cards, poster | pass, 0 errors | pass | PNG at exact size | n/a |

Remaining check output is deliberate: `nested_structure_needs_subcomposition` and
`timeline_track_too_dense` warnings (each film is one self-contained HTML file so it can be
read and diffed in one place), and `text_occluded` infos where a cover or strike-through
crosses text on purpose (marked with `data-layout-allow-occlusion` where the linter honors it).

## Loop seam

Frame 179 against frame 0 of `nitelos-loop-6s.mp4`: PSNR 48.98 dB (identical within
encoder noise). Both are the settled failure state; every tween settles by 5.2 s.
Three repetitions concatenated: `renders/nitelos-loop-6s.x3.mp4`, 18.0 s. Consecutive-frame
PSNR across both seams (frames 179→180 and 359→360) is 48.98 dB, against 58 to 81 dB between
held frames inside a cycle; the small drop is the keyframe at the start of each copy, not
a content change.

## Problems found during QA, and what was done

| Where | Problem | Fix |
|---|---|---|
| Main, scene 4 | The trace landed on `false` (row 2) instead of the observed `true` | Re-routed from the right at row-1 height |
| Main, close | The cut n read as "ritelos" for too long before the square docked | Dock moved earlier (27.6 s); the square rides the trace opaque |
| Main, close | Two GSAP tweens fought over `#dock-square` y | Split into separate opacity and y tweens |
| Main, audio | First master measured −21 LUFS | Mix rebalanced (music up, SFX down), then measured gain + limiter: −15.95 |
| Demo | Code highlight marks clipped neighbouring rows; Verifier text and verdict overflowed | 33 px row grid at 25 px code; sizes reduced |
| Vertical | Bottom label hidden by the output panel | Label moved and shortened |
| Loop | Crossfades overlapped two words for a few frames ("refuteded") | Outgoing text clears before incoming text arrives |
| Loop | `fromTo` without baseline could leave a wrong state at seek 0 | Explicit `tl.set` baselines at 0, equal to the 6 s frame |
| Kit | Loop data: `email_filled` differs from the failure example | Verified: the loop uses the quickstart observation with one value flipped (`evidence/quickstart_flipped.stdout.txt`) |

## Not checked

- Playback on real social platforms (nothing was uploaded; no publishing was authorized).
- WebM playback in Safari (VP9 support varies; the MP4 is the fallback).
- A listening test on phone speakers; loudness is measured, not auditioned there.
