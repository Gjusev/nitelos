# Documentation audit (launch pass, 2026-10-20)

Scope: `README.md`, `CONTRIBUTING.md` and `docs/` at commit `6b3d108` (nitelos 0.1.0 on
PyPI). Each finding names the evidence that showed it was wrong and the fix made.
How the fixes were checked: [documentation-validation.md](documentation-validation.md).

## Findings and fixes

| # | File | Issue | Evidence | Fix |
|---|---|---|---|---|
| 1 | `README.md` | Opening did not show the problem or a real result | Read-through; no output anywhere above the fold | Rewritten in English: wordmark, tagline, PyPI badges, "The problem" with the literal stdout of `examples/demo_incomplete_form.py`, a "How it works" diagram, install, a verified quickstart, "Reading a result", "Evaluation status" |
| 2 | `README.md` (draft row) | Said checks can run in parallel | One in-flight call per `Verifier` instance; a concurrent call returns `BUSY` | Row rewritten to the actual concurrency rule |
| 3 | `README.md`, diagram | "evidence references that decided each criterion" over-claims | Abstained criteria carry no deciding evidence | Now "behind every decided criterion" (README and `how-it-works-*.svg`) |
| 4 | `README.md` | Documentation table pointed the lifecycle row at the wrong topic | `docs/lifecycle.md` content | Row corrected |
| 5 | `docs/quickstart.md` | Snippet was not a complete runnable script and showed no output | The old block parsed an undefined `request_json_text`, so it could not run as written | Complete script with the literal output; "Change one value" section, verified by running it (see validation) |
| 6 | `docs/installation.md` | Did not say the package is on PyPI; the core-only checkout command installed dev tools | `uv sync` installs the dev group by default (`uv sync --dry-run`) | PyPI note added; "From a checkout" uses `uv sync --frozen --no-dev` for core only |
| 7 | `docs/evaluation.md` | Stale "No benchmark run…" bullet | `reports/v0.1/SUMMARY.md` exists | Replaced by a link to SUMMARY with its ADR-013 label; no figures copied into docs |
| 8 | `docs/backends.md` | "pending NIT-013" | NIT-013 closed, results in SUMMARY | Link to SUMMARY |
| 9 | `docs/errors-and-abstention.md` | `UNSUPPORTED_CAPABILITY` row read as general | Only raised for visual criteria without a capable backend | Row scoped to visual criteria |
| 10 | `docs/traces.md` | Trace example could be read as a stable format | Example is illustrative | Sketch note added |
| 11 | `CONTRIBUTING.md` | DCO sign-off and cryptographic commit signing were conflated | Text | The two are now described separately |
| 12 | `docs/planning/README.md` | Planning status read as current | v0.1 is released | Historical-baseline banner above the original status line |
| 13 | `docs/` | No entry point by task | Reader had to scan file names | New `docs/README.md` task index |

## Visual assets added for the docs

- `docs/assets/brand/`: wordmark, mark and tile, dark and light.
- `docs/assets/nitelos-film-preview.gif`: the current README hero, a silent preview of the
  28 s explainer (`videos/nitelos-launch/explainer.html`, 0 to 21 s, 800 px, 10 fps, 96
  colours, 3.5 MB) linking to the full film with sound, hosted on Hugging Face
  (`datasets/Gjusev/nitelos-launch`). GitHub strips `<video>` tags pointing at repository
  or external files, so an inline player would need a web-uploaded attachment.
- Earlier hero, removed: `docs/assets/nitelos-workflow.gif`, the five-step workflow film
  (`videos/nitelos-launch/workflow.html`) up to the settled diagram, at 960 px, 12 fps,
  96 colours (680 KB). It is a GIF because GitHub does not play repository MP4s inline.
  A first README pass used the 6 s loop instead; feedback was that it did not explain
  what the project does, so the workflow film replaced it.
- `docs/assets/how-it-works-{dark,light}.svg` (real text, accessible title and
  description) with PNG fallbacks, and `docs/assets/nitelos-film-poster.jpg` (verdict
  frame, 107 KB). Neither is used by the README any more, since the GIF and the
  numbered steps cover them; they are kept for slides and posts.
- Generators: `videos/nitelos-launch/tools/brand.py` and `tools/diagram.py`.

## Left as is, on purpose

- No benchmark numbers in README or docs: they live in `reports/v0.1/SUMMARY.md` with
  their ADR-013 label, and are linked, not restated.
- Python blocks in `docs/custom-adapters.md`, `docs/lifecycle.md`, `docs/traces.md`,
  `docs/recipes/caller-collection.md` and `docs/implementation/nit-008-adapter-design.md`
  are fragments, not scripts; they were read, not executed (see validation).
- GitHub URLs: only the CI badge, added when the repository was made public
  (2026-10-20). The films and storyboard still carry none; they were made while it was
  private and point to PyPI.
