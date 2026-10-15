# What verified success means

`decision: success` says exactly this and nothing more: **every declared criterion
was supported by admissible evidence at the request's checkpoint**, under the
policy you configured.

- Scope-relative: the criteria define what "success" means. Nitelos never
  infers conditions from objective prose.
- Time-scoped: evidence is checked against `as_of`, the request checkpoint,
  freshness windows and phase. A result describes that moment, not the future.
- Evidence-relative: an outcome can be false while your evidence cannot
  establish it — that is `abstained`, never a guessed failure or success.
- Basis-labeled: every criterion result carries its basis — `deterministic`,
  `model_inferred` (experimental visual only), or `none`.

The aggregation is an all-required conjunction: all supported → success; any
refuted → failure; otherwise abstained. A same-criterion contradiction becomes
unknown. "The tool completed" and "the summary says done" are context, never
proof — see [errors-and-abstention.md](errors-and-abstention.md).
