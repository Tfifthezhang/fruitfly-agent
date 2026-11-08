# Independent Stage Bindings

[Up: Improvement](../README.md)

These handlers adapt a single research operation to its owning role or injected
execution backend. They do not invoke one another or schedule another activity.

| File | Responsibility |
|---|---|
| `registry.py` | Narrow injected `StageContext` and default handler mapping |
| `organize.py` | Batch readability request, optional auxiliary context and guide output |
| `assess.py` | Per-record structured feedback, including explicit unavailable results |
| `propose.py` | Direct retained-batch proposal request and owner-validated candidate output |
| `execute.py` | One injected fixed-config execution batch and derived-config attribution |
| `compare.py` | Explicit batch comparison without selecting research continuation |
| `context.py` | Expand explicitly granted feedback resources for role consumption |
| `extensions.py` | Immutable identity of injected extension settings |
| `control.py` | Separate optional online execution control; no research scheduling |

Run supplies artifact callbacks, role instances and stage services. These modules
import neither Run, Experiments nor Eval. External benchmark formats remain in
their adapters. Algorithms remain with Organizer, Editor, Assessment and execution
owners; this directory defines no parallel mechanism configuration registry.

Missing scores never prevent invocation. Feedback unavailability is retained as
data. The Editor receives granted historical records directly, without fabricated
search scores or baseline trials. See the [developer guide](../DEVELOPER_GUIDE.md).

```bash
.venv/bin/python -m unittest tests.improvement.test_research_service tests.experiments.test_stage_cli tests.experiments.test_research_continuation
```
