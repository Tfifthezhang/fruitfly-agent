# Independent Stages

[Up: Improvement](../README.md)

The controller invokes one injected activity and retains its intent and result.
It never schedules another activity, selects a candidate or runs a search loop.

| File | Responsibility |
|---|---|
| `controller.py` | Reuse, explicit attempts, invocation and durable activity receipts |
| `services.py` | Cancellation, resources, observations and restricted generation services |
| `operations.py` | Invocation failure and result-validation boundary |
| `timing.py` | Independent invocation clocks |
| `recovery.py` | Validate and reconstruct research journal state |

Inputs and implementations are injected. The controller depends on Core and
Improvement contracts, without Lab, Run, Providers or Eval imports. Scores are
observations and do not control whether an activity may run.

```bash
.venv/bin/python -m unittest tests.improvement.test_research_recovery tests.improvement.test_stage_contracts
```
