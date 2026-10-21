# DeepEval metric (extra `deepeval`)

[nitelos.integrations.deepeval_metric](https://github.com/Gjusev/nitelos/blob/main/src/nitelos/integrations/deepeval_metric.py)
wraps one nitelos verification as a deterministic DeepEval metric:
`NitelosOutcomeMetric`. The outcome comes from a provider closure you
supply (typically: run collectors, build the request, verify); the DeepEval
test case is accepted and ignored.

## Install

```text
pip install 'nitelos[deepeval]'
```

## Minimal runnable example

See [examples/deepeval_metric_demo.py](../examples/deepeval_metric_demo.py),
which runs offline with a fixed verification result.

```python
from nitelos import Verifier
from nitelos.integrations.deepeval_metric import NitelosOutcomeMetric

metric = NitelosOutcomeMetric(lambda: Verifier().verify(request))
metric.measure(None)
metric.score  # 1.0 or 0.0
metric.reason  # safe codes only
metric.is_successful()
```

## Score mapping

| nitelos result | score | is_successful | reason |
|---|---|---|---|
| decision `success` | 1.0 | True | "decision success: ..." |
| decision `failure` | 0.0 | False | "decision failure: criteria refuted" |
| abstained | 0.0 | False | "abstained: <reason codes>" |
| execution error | 0.0 | False | "execution <status> (<code>); decision is null" |

The score is exactly 1.0 or 0.0: no thresholds, no fractions. Abstention is
never scored as a pass and its reason is distinct from the execution-error
reason. A provider that returns a non-VerificationResult scores 0.0 with
its own reason instead of raising.

## Limitations

- Reasons carry criterion ids and reason codes only, never evidence values.
- The metric is a thin mapper: it never weakens a request and never adds
  trust; the provider closure decides everything the verifier sees.
- Pinned against deepeval 2.9.3 API realities: `BaseMetric.__name__` is a
  read-only property (the metric overrides it) and `is_successful` is a
  method, not a property. Importing the module without the extra raises
  `ImportError` naming `pip install "nitelos[deepeval]"`.
