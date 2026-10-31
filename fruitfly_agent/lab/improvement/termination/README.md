# Termination

[Up: Improvement](../README.md)

Pure conditions shared by task control, candidate search and cross-generation RSI.
Stopping never grants quality assurance and cannot override phase time/cancellation.

| Policy | Trigger |
|---|---|
| `IterationLimit` | Completed iteration count |
| `NoImprovement` | Consecutive unchanged selected/adopted versions |
| `FailureLimit` | Consecutive recorded failures |
| `ResourceLimit` | Measured calls, executions or elapsed time |
| `ScoreAtLeast` | Incumbent score and required assurance |
| `MetricThreshold` | Latest final assessment for the declared scope |
| `AnyOf`, `AllOf` | Ordered, deterministic condition composition |

`StopDecision` retains reason and evidence IDs. Missing/provisional measurements
do not satisfy final goals. Search and generation states have separate phases.
`StopExecutionPolicy` requests a scoped runner stop; it does not cancel RSI.
Custom policies implement `decide(state)`. `StopRegistry` discovers factories
without execution. Durable custom policies declare a configuration identity;
changed strategy rejects resume.

Ordinary search supplies consecutive non-completed execution counts and final
completed-process assessments at round boundaries, including an empty proposal
round. Zero official reward is not an execution failure. `MetricThreshold` needs
an exact assessor ID, metric and scope; unknown/provisional values cannot trigger
it. Online metrics are a separate path and are not implicitly copied into search
stopping. Persistent RSI rejection is not a counted failure and its standard
generation state does not supply these completed-process assessments.

`BoundedStopPolicy` is provided by this module; stopping contracts belong to
`improvement.contracts.stopping`. Defaults still bound rounds and retain original results. Finite
patience is a stopping rule, not proof of convergence or a calibrated confidence
claim. Provider request and monetary enforcement remain separate accounting.

```bash
.venv/bin/python -m unittest tests.lab.test_evolution_policies tests.lab.test_online_improvement tests.rsi.test_callbacks
```

Frozen host previews retain policy parameters through `policy_spec`, not only
class names. Changing a patience or threshold invalidates the old preview. Pure
custom policies expose immutable configuration; hidden mutable policy state is
not restored automatically.
