# Execution Kernel

[Up: Improvement Runtime](../README.md)

| File | Responsibility |
|---|---|
| `scheduler.py` | Bounded worker queue shared by single-task and batch trials |
| `handles.py` | Owned cancellable tasks and truthful completion-only adaptation |
| `events.py`, `control.py` | Immutable attributed events and scoped control |
| `facts.py` | Validate/store terminal diagnostics without inferring unknown results |
| `batches.py` | Execute frozen batches through injected runners and aggregation |
| `segments.py` | Segment identity and state evidence |

Executors receive frozen material and a harness, return exact receipts, and clean
up cancellation. Failed or interrupted work is not a completed measurement.
Facts distinguish incomplete diagnostics, collection failures and confirmed
absence. `diagnosable` permits useful failed-task evidence to reach editing; it
never makes a failed execution selectable or verified.

Concrete file/SSH/container capabilities belong to their registered backend.
See [Lab execution](../../lab/improvement/execution/README.md) and optional
[Eval](../../../eval/improvement/README.md). Offline checks:
`tests.lab.test_improvement_reliability`, `tests.lab.test_task_set_lifecycle`,
`tests.eval.test_execution_facts`.
