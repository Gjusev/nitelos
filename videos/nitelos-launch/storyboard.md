# Storyboard: main film, 30 s, 1920x1080, 30 fps

Concept: "From the attempt to the evidence". One continuous stage for the first
example (objects persist and reflow; the camera never cuts), then a wipe to the
second example, the three-answer legend, and the logo close. All on-screen
text is English. Copy is final; every factual line maps to `claims.md`.

Music: `happy-beats-business-moves-vol-12` (ende.app, CC BY 4.0), 109.96 BPM.
Beat-locks: verdict 1 at 14.20 s (beat), verdict 2 at 20.75 s (beat), legend
at 22.93 s (strong cue). Fade out over the last 1.5 s.

Persistent frame (whole film): top-right real request metadata in Martian Mono
(`demo-registration-1 · cp-final`); bottom-left honesty label
`synthetic example · real output`.

| # | Time | On-screen copy | Visual and motion | Source |
|---|---|---|---|---|
| 1 | 0.0 to 3.0 | "Your agent says:" / card: `registration succeeded` | Claim card arrives fast and settles; claim set in condensed Archivo (wdth 62): the tense, unverified voice. Card label: `agent summary · context only, never proof` | fixture `metadata.agent_summary` and its code comment |
| 2 | 3.0 to 6.0 | "Does the evidence agree?" | The card slides up and away to the top-right corner, uncovering the observation panel behind it: `validation_error true`, `email_filled false`. The `validation_error` row is outlined in the accent; the evidence square marks the panel | fixture observation `obs-form` |
| 3 | 6.0 to 9.6 | "Write down what done means." | Observation panel tightens to the left column; criterion panel enters on the right: `no-errors`, "No validation error remains on the form", `/validation_error  equals  false` | fixture criterion |
| 4 | 9.6 to 14.0 | "Check it against the evidence." | Signature transition: the underline under `/validation_error` extends into the pointer trace, runs across to the observed value and stops dead on `true`. Comparison strip: expected `false`, observed `true`, not equal | criterion vs observation |
| 5 | 14.0 to 18.6 | "The check ran fine. The outcome failed." | Verdict lands on the beat: `failure` expands from condensed to wide in coral with the struck square. Beside it, the real stdout in a plain panel labeled with its command | `evidence/demo_incomplete_form.stdout.txt` |
| 6 | 18.6 to 22.8 | "The upload tool says completed." | Horizontal wipe to the second example. Action card `upload-file`, `reported_status completed`; criterion "The exported report is stored in the external system" with `evidence_ids:` empty. Verdict `abstained` in amber with the outlined square, beside the real stdout (`criterion stored: unknown`, `INSUFFICIENT_EVIDENCE`, `MISSING_EVIDENCE`). The planned second caption ("No external record was supplied, so nitelos abstains.") was cut during QA; the empty `evidence_ids` row and the real stdout carry that point | `evidence/demo_external_pending.stdout.txt` |
| 7 | 22.8 to 26.8 | "Judged only on the evidence you supply." + legend | Three rows arrive one by one (each holds): `success` every criterion supported; `failure` a criterion refuted; `abstained` not enough evidence to decide | SDK decision semantics (`docs/success-criteria.md`) |
| 8 | 26.8 to 30.0 | wordmark, "Verify the outcome, not the attempt.", `pip install nitelos` | The wordmark arrives with the n's right leg cut short. The accent square rides a vertical trace down and stops dead in the gap at 27.6 s (bell SFX): the wordmark is complete. The dock was pulled earlier in QA so the cut n is never read as an r for long. Tagline and install line settle. Last frame holds | PyPI `nitelos 0.1.0` (verified 2026-10-16) |

Reading floors: every headline holds at least 1.8 s fully settled; the legend
rows reveal 0.6 s apart and then hold together for 2.2 s.

Not shown on purpose: the success example (it belongs to the 60 s demo), any
benchmark number, any GitHub URL (the repository is private).
