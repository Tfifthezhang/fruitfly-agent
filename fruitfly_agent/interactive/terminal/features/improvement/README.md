# Improvement Feature

[Up: Terminal Features](../README.md)

Use `/improvement [DIRECTION]` to improve against a declared task set, save a daily case, or review a proposed change. `TerminalImprovementFrontend` is the menu entry; `improvement_handler` borrows and restores the terminal's input/display scope. The menu retains navigation notices and returns outcome text; the handler publishes it through `CommandResult` after restoring chat, so the alternate screen cannot erase the reason for returning.

| File | Responsibility |
|---|---|
| [menu.py](menu.py) | Task source selection, one cost confirmation, progress, candidate review/activation, and case corrections |
| [command.py](command.py) | Dispatch through an injected view factory and menu scope |
| [events.py](events.py) | Original-task event display |
| [formatting.py](formatting.py) | Generic improvement activity text |

## Navigate the menu

Back and Esc return one level through task sources, benchmarks, task sets, saved packages, case-saving selections, and candidate review. Each parent retains its selected row; candidate lists retain pagination while viewing details. Cancelling a confirmation returns to its selection page. Case form drafts survive returning from confirmation. `q` exits the whole menu from any selection page; the home page also offers **Return to chat**. Navigation and cancelled confirmations never start jobs. Every execution confirmation starts with Cancel selected, including after revisiting it.

Unavailable configuration or task environments leave a notice on the parent/selection page instead of closing the menu. Notices also remain available in the restored chat transcript when the menu exits.

## Start with a task source

| Source | Behavior |
|---|---|
| Saved task packages | Choose authored tasks or daily cases with executable acceptance criteria; inspect target, scorer, models and budget |
| Benchmark tasks | Choose a bounded official task set; download/freeze it and run baseline, failure processing, iterative search and independent confirmation in one Application job |
| Save a failed task | Supply self-contained input and verified acceptance; confirm training-only persistence without model calls |
| Review candidates | Inspect evidence and changes; explicitly save or adopt in a fresh session |

`ImprovementClients` injects search, candidates, task materials, activation and progress independently. Optional `BenchmarkImprovementController` supplies benchmark task sources and one-use preview execution. The feature imports no Eval or Lab implementation. Hosts without Eval can use saved task packages and review candidates normally.

Benchmark preparation belongs to the same Application optimization lifecycle as model work. Selection/preview starts no task downloads or model calls. **Start improvement** authorizes the displayed bounded job, including downloads, containers and model calls. Cancel is selected by default. Main and auxiliary model calls share the root budget. A dedicated renderer preserves full original-task tool output and logs while the benchmark job is awaited; cooperative cancellation restores chat.

Benchmark improvement requires an enabled optimizer, failure processor and automatic workflow in the active session. If these are unavailable, the menu displays a configuration hint on its parent page without loading the task catalog or starting work. Empty catalogs, missing task sets, failed preflight, preview/execution errors, completion and cancellation also leave a visible message in the restored chat transcript. See [Original task experiments](../../../../lab/optimization/experiments/README.md#run-a-benchmark-improvement-job) for configuration and execution requirements.

A saved daily case is usable only with declared acceptance and required data splits. Raw conversations and weak-feedback tasks are not automatically collected or scored. Existing material services own validation; selecting a package does not modify its acceptance criteria.

A confirmed candidate waits for human adoption. This feature does not establish model quality, grant activation to an algorithm, or optimize arbitrary code/workflow/state. See [Automatic search](../../../../lab/optimization/automatic/README.md), [Original task experiments](../../../../lab/optimization/experiments/README.md), and [Task packages](../../../../lab/optimization/TASK_PACKS.md).

The built-in terminal registers one improvement command. Programmatic search remains available through its independent interaction contract. Standalone benchmark evaluation belongs to the optional Eval CLI.

```bash
.venv/bin/python -m unittest tests.interactive.test_improvement tests.interactive.test_improvement_back tests.interactive.test_benchmark_events tests.interactive.test_confirm_navigation tests.workflows.test_benchmark_improvement -v
```

Offline checks use fake Providers, controllers and original-task executors. Input and display come from [I/O](../../io/README.md) and [Rendering](../../rendering/README.md). No new environment variables.
