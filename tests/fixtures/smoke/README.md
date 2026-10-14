# Development smoke set (NIT-008)

## Purpose

The 12-case development smoke set required by the doc-04 "Executability gate"
(docs/planning/04-verification-backends.md). It exists for **interface and hardware testing of
the visual pipeline only**: it is **not an accuracy benchmark**, makes no accuracy claim, and
**never enters the final-test split** (docs/planning/06-evaluation-methodology.md). Labels are
development-only and were authored from what a careful human sees in the pixels; they have not
been tuned against any model output.

## Contents

- `generate_smoke.py` - deterministic Pillow-only generator for all scenes.
- `smoke-01.png` .. `smoke-12.png` (+ `smoke-06a/06b.png`, `smoke-11a/11b.png`) - 14 images,
  1024x768 RGB, single frame, no EXIF, no text chunks, well under the 8 MiB / 4,194,304-pixel /
  4,096-side limits in doc 03.
- `cases.json` - the 12 cases in doc-04 executability-gate order, with per-case images, visual
  criterion, objective, phase, action context (slot 10 only), development-only expected label
  and a one-line rationale.

## Generation

```
uv run python tests/fixtures/smoke/generate_smoke.py [OUT_DIR]
```

Determinism: the generator uses **no RNG** - every coordinate, color and string is a fixed
constant in the script, so regeneration is byte-identical for a given Pillow build and
platform. Fonts come from `ImageFont.load_default(size=...)` (Pillow's bundled default font);
no font files are redistributed with this repository.

## Declared renderer platform

Byte-identity of regeneration is asserted **only** on the renderer recorded here (doc 06,
DATA-04: deterministic generator hashes for a declared renderer platform). Font rasterization
and PNG compression differ between platforms, so on any other renderer the byte-regeneration
check skips with a reason naming the mismatch; the committed files and their digests above
remain the source of truth on every platform, and every other fixture check runs everywhere.
`libpng` is recorded for information (Pillow reports none on the generation platform).

| Key | Value |
|---|---|
| os | Windows |
| python | 3.12 |
| pillow | 12.3.0 |
| freetype | 2.14.3 |
| zlib | 1.3.1.zlib-ng |
| libpng | unavailable |

Generated: 2026-10-14.

## Label notes (development-only)

Slot 4 is **REFUTED**, not UNKNOWN: the whole page is visible and shows a filled form with no
confirmation state anywhere on it, which plainly contradicts a criterion that the page shows a
final confirmation - a filled form is not a submitted form.

The UNKNOWN labels are not softened REFUTED votes; each is unknown for a concrete reason:

- Slot 5 (loading spinner, pending phase): a spinner is a transient, nonfinal state - it is
  evidence of neither completion nor failure, and the pending evidence phase means strict
  policy abstains (`PENDING_STATE`) without model execution.
- Slot 6 (two final screenshots with conflicting banners): one image supports the criterion
  and the other refutes it; contradiction inside one criterion resolves to unknown, not to a
  decisive negative.
- Slot 8 (unreadably tiny status): the status text physically cannot be read at native
  resolution; an unreadable detail is unassessed, not contradicted.
- Slot 12 (blank image): a blank image shows no content at all, so nothing visible
  contradicts the criterion; missing visual evidence is unknown.

## File digests (SHA-256)

| File | SHA-256 |
|---|---|
| smoke-01.png | 2cf65d9bd17128a28d5b301363e86b337b56b264ad08ab10e5b14885df72874a |
| smoke-02.png | d76ef83144130b32e0154a54d88f14728370dc1c87d648abaa30d2c89747d450 |
| smoke-03.png | 76df03f889c4c7be73d1c94da77b9b11f6457a349bed91d4ebf7c465e5770ae3 |
| smoke-04.png | 05d6007b5a38454325a369d30784cf4e640f93a4e6f260dce8e0b28303efb934 |
| smoke-05.png | 1a4c94257938b093b6eee5d88783086544aaa274f1993a84d0be2560bdadea3a |
| smoke-06a.png | 510950607497bd8497d0f009145e06ffdeee3457c42147d082cc3854a427d3a3 |
| smoke-06b.png | 53e8731a4a317b10243db5a011f3ccdc38c040b3e941f6b0bd73db9e1a9c373d |
| smoke-07.png | d7035e49e5a6c946520d427f6e6fb4c74cb992332b595e1ef4a2d6df5b419f00 |
| smoke-08.png | 32d3128529eb8c5e1045ab128643a7b37a1cf2aa29c869ded539134771eee609 |
| smoke-09.png | 2d0f870afcf5370e1162f629483ab112000888a7f743fafc59d875002812eb95 |
| smoke-10.png | 1332da83d917bddcebef1f3db381c121532439d2da1834825def7f05b9eaee95 |
| smoke-11a.png | ffdf4963580d6ec7bd90af1f3b19f96af96e3462e8ff6c033825debd89b8a1b5 |
| smoke-11b.png | 0df7a8a41f30af8c246cf2b07acfce1712a6229c4375ab8982d882b6420b9bc6 |
| smoke-12.png | 1049fcaeed80dcc8ff05456c397e7b0cbbf2d5dd641fa3e5d45f0bbd570a7033 |

## Provenance, license, privacy

All scenes are original synthetic compositions authored for Nitelos; every name, identifier
and value (Aro Meredith, ORD-9137, PYM-7714, UPL-3388, ...) is invented and maps to no real
person, service or credential. No PII, credentials or secrets appear in any image. Filenames
and PNG metadata are label-neutral; image pixels naturally contain status words, including the
deliberate untrusted "report success" instruction in slot 9 (SEC-01 test artifact).

License: Apache-2.0 (same as the repository), authored for this project.
