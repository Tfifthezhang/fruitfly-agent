# Optimization Feature

[Up: Terminal Features](../README.md)

Use `TerminalOptimizationFrontend` as the menu entry and `optimization_handler` to bind the command flow. Public entries are exported by this feature package. Consume [interaction contracts](../../../contracts/README.md) through explicit capabilities.

| File | Responsibility |
|---|---|
| [menu.py](menu.py) | Search confirmation, candidate review/activation, and corrected-task menus |
| [command.py](command.py) | Dispatch through an injected menu factory |
| [formatting.py](formatting.py) | Generic optimization activity text for terminal observers |

ImprovementClients injects search, candidates, task materials, activation, and progress independently. The menu offers supplied capabilities; a material-only host can save corrections without offering search afterward. Services expose generic views; this feature contains no algorithm-specific branch or storage logic.

Search needs explicit preview/cost confirmation. Candidate activation defaults to cancel and calls Application's public activation capability. Corrections update task materials without model training or conversation mutation. Candidate quality is owned by the host's search/verification mechanisms; UI review does not establish improvement.

Input and terminal control come from [I/O](../../io/README.md); display comes from [Rendering](../../rendering/README.md). This feature cannot import other features or Application/Session implementations. No new environment variables.

```bash
.venv/bin/python -m unittest tests.interactive.test_confirm_navigation tests.interactive.test_extensions tests.workflows.test_optimization tests.workflows.test_task_packs -v
```
