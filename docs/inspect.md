# Inspect AI scorer (extra `inspect`)

[nitelos.integrations.inspect_scorer](https://github.com/Gjusev/nitelos/blob/main/src/nitelos/integrations/inspect_scorer.py)
turns one nitelos verification into an Inspect AI
[Score](https://inspect.aisi.org.uk/scorers.html). The truth comes from
evidence the task's solver and tools captured, never from the target string.

## Install

```text
pip install 'nitelos[inspect]'
```

## Minimal runnable example

See [examples/inspect_verify_task.py](../examples/inspect_verify_task.py): a
task whose solver reports a deployment and whose state store carries the
evidence; the scorer then decides from the evidence alone. Offline, runnable
without a model.

```python
from nitelos.integrations.inspect_scorer import nitelos_scorer

scorer = nitelos_scorer()  # attach to a Task via scorers=[...]
```

The scorer contract: sample metadata carries `nitelos_criteria` (a list of
v0.1 criterion documents) and `nitelos_checkpoint_id`; the final state store
carries the evidence list under `nitelos_evidence` (written by your solver
or a collector-backed tool). Missing `nitelos_criteria` raises `KeyError` at
scoring time: a task misconfiguration should be loud, not a silent score.

## Score mapping

| nitelos result | Inspect value |
|---|---|
| decision `success` | `C` |
| decision `failure` | `I` |
| abstained, input_error, backend_error | `A` (with the code in metadata) |

Score metadata carries `nitelos.decision`, `nitelos.execution_status`,
`nitelos.reason_codes`, `nitelos.limitation_codes` and
`nitelos.evidence_fingerprints` (payload digests). The explanation is built
from safe codes only; raw evidence values never enter the Score.

## Abstention and accuracy

The scorer attaches `nitelos_accuracy` by default; there is nothing to pass:

```python
from nitelos.integrations.inspect_scorer import nitelos_scorer

scorer = nitelos_scorer()  # nitelos_accuracy is already attached
```

`nitelos_accuracy` computes C/(C+I) over the decisive scores only and
returns 0.0 when there are none. Inspect's stock `accuracy()` maps every
unknown value, including our `A`, to 0.0 and keeps it in the denominator,
which would punish abstention like failure; that is why the custom metric
exists. Attach the stock metric yourself if you want abstention counted as
wrong.

## Limitations

- Evidence supplied through the scorer is agent evidence: it is verified
  unbound, so external-scope criteria abstain with `UNTRUSTED_EXTERNAL`.
  Only the host can create trust bindings, outside Inspect.
- A criterion citing an evidence id the store does not carry is rewritten
  to an empty citation and abstains with `MISSING_EVIDENCE` (never a loud
  crash); malformed stored evidence also scores `A` with `INVALID_SCHEMA`.
  Eval-author mistakes in the criteria themselves stay loud.
- Requires inspect-ai 0.3.x; importing the module without the extra raises
  `ImportError` naming the install command.
