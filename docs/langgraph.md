# LangGraph node (extra `langgraph`)

[nitelos.integrations.langgraph_node](https://github.com/Gjusev/nitelos/blob/main/src/nitelos/integrations/langgraph_node.py)
provides `verify_outcome_node`, a node factory that verifies an outcome and
writes a `NitelosVerification` into graph state under the `nitelos` key.
Criteria are host-authored v0.1 documents; the evidence provider callable
returns the evidence the host captured (typically by running collectors).

## Install

```text
pip install 'nitelos[langgraph]'
```

## Minimal runnable example

See [examples/langgraph_verify_node.py](../examples/langgraph_verify_node.py):
a graph whose node verifies and routes on the decision, offline.

```python
from nitelos.integrations.langgraph_node import route_on_decision, verify_outcome_node

node = verify_outcome_node(criteria=CRITERIA, evidence_provider=collect)
update = node(state)  # {"nitelos": NitelosVerification}
route_on_decision(update["nitelos"].decision)  # "continue"|"interrupt"|"abstain"
```

## Routing and state

`NitelosVerification` carries `decision`, `execution_status`,
`reason_codes`, `evidence_ids` and `criterion_states` (tuples of
`(criterion_id, state)`). The node returns a state update; LangGraph merges
it and the incoming state is otherwise untouched. `route_on_decision`
gives the default mapping for conditional edges: success continues,
failure goes to `interrupt()` (re-exported from the module), everything
else abstains and follows a configurable route. The node never raises: a
failing provider becomes `backend_error` in state, an unparseable request
becomes `input_error`, and the graph stays debuggable.

The request is verified with `as_of` set to the node execution moment, so
criteria freshness governs evidence exactly as everywhere else. A criterion
citing evidence the provider did not return is rewritten to an empty
citation and abstains with `MISSING_EVIDENCE`.

## Limitations

- Graph state schemas MUST be module-level TypedDicts. langgraph serializes
  node and router function source for checkpointing, and a function-local
  class raises `NameError` at invoke time (verified against langgraph
  1.2.16).
- Evidence is unbound unless the host passes a verifier with trust
  bindings it created itself; external-scope criteria then abstain with
  `UNTRUSTED_EXTERNAL`.
- The node runs the verification synchronously (deterministic,
  milliseconds); any async collection happens in your provider.
- Importing the module without the extra raises `ImportError` naming
  `pip install "nitelos[langgraph]"`.
