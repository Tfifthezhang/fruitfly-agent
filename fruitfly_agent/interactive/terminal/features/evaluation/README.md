# Evaluation Feature

[Up: Terminal Features](../README.md)

Use `TerminalEvaluationFrontend` as the menu entry and `evaluation_handler` to bind the command flow. Public entries are exported by this feature package. Consume [interaction contracts](../../../contracts/README.md) through explicit capabilities.

| File | Responsibility |
|---|---|
| [menu.py](menu.py) | Benchmark/variant selection, cost confirmation, events, and diagnostics |
| [command.py](command.py) | Busy feedback, menu lending, launch coordination, and report paths |

EvaluationController describes and launches an optional external evaluation. This feature does not import Eval or benchmark implementations. The controller owns subprocesses, artifacts, and external effects. Existing explicit confirmation precedes launch.

The command awaits evaluation completion and returns to chat. Cancellation/error paths restore terminal display. Real launches can incur model, container, and network costs; offline checks use fake or blocked controllers.

Input and terminal control come from [I/O](../../io/README.md); display comes from [Rendering](../../rendering/README.md). This feature cannot import other features or Application/Session implementations. No new environment variables.

```bash
.venv/bin/python -m unittest tests.interactive.test_evaluation tests.workflows.test_optional_eval -v
```
