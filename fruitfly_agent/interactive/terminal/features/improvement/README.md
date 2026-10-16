# Improvement Feature

[Up: Terminal Features](../README.md)

Use `/improvement [DIRECTION]` to choose an H/S/I target, improve against declared tasks, or review a proposed change. `TerminalImprovementFrontend` is the menu entry; `improvement_handler` borrows and restores the terminal's input/display scope. The menu retains navigation notices and returns outcome text; the handler publishes it through `CommandResult` after restoring chat, so the alternate screen cannot erase the reason for returning.

| File | Responsibility |
|---|---|
| [menu.py](menu.py) | Task source selection, one cost confirmation, progress, candidate review/activation, and role/target selection |
| [command.py](command.py) | Dispatch through an injected view factory and menu scope |
| [events.py](events.py) | Original-task event display |
| [formatting.py](formatting.py) | Generic improvement activity text |

## Navigate the menu

Back and Esc return one level through task sources, benchmarks, task sets, saved packages, H/S/I target selections, and candidate review. Each parent retains its selected row; candidate lists retain pagination while viewing details. Cancelling a confirmation returns to its selection page. `q` exits the whole menu from any selection page; the home page also offers **Back**. Navigation and cancelled confirmations never start jobs. Every execution confirmation starts with Cancel selected, including after revisiting it.

Unavailable configuration or task environments leave a notice on the parent/selection page instead of closing the menu. Notices also remain available in the restored chat transcript when the menu exits.

## Start with a task source

| Source | Behavior |
|---|---|
| Saved task packages | Choose authored tasks or daily cases with executable acceptance criteria; inspect target, scorer, models and budget |
| Benchmark tasks | Choose a bounded official task set; download/freeze it and run baseline, failure processing, iterative search and independent confirmation in one Application job |
| Review candidates | Inspect evidence and changes; explicitly save or adopt in a fresh session |

`ImprovementClients` injects search, candidates, task materials, activation, progress, target declarations and method discovery independently. The home page selects H (Harness), S (State), I (Improver), or Jobs and history. A role opens its registered targets, then search and candidate actions. Starting a search selects among compatible installed methods before selecting tasks. One method is selected automatically. Several methods open a selector with unavailable reasons; Back restores the method selector. Preview must also match the chosen method. Temporary selection does not change configuration. Candidates are filtered by role and target; history can show all roles. Missing executable targets show an explicit reason. Previews must match the selected role and target. Optional `BenchmarkImprovementController` supplies benchmark task sources and one-use preview execution. The feature imports no Eval or Lab implementation. Hosts without Eval can use saved task packages and review candidates normally.

Benchmark preparation belongs to the same Application improvement lifecycle as model work. Selection/preview starts no task downloads or model calls. **Start improvement** authorizes the displayed bounded job, including downloads, containers and model calls. Cancel is selected by default. Main and auxiliary model calls share the root budget. A dedicated renderer preserves full original-task tool output and logs while the benchmark job is awaited; cooperative cancellation restores chat.

Benchmark improvement binds search, failed-task replay and independent confirmation on demand. If execution capabilities are unavailable, the menu displays the reason on its parent page without loading the task catalog or starting work. Empty catalogs, missing task sets, failed preflight, preview/execution errors, completion and cancellation also leave a visible message in the restored chat transcript. See [Original task experiments](../../../../lab/improvement/experiments/README.md#run-a-benchmark-improvement-job) for configuration and execution requirements.

A saved daily case is usable only with declared acceptance and required data splits. Daily observation recording is separately configured through [Learning](../../../../lab/learning/README.md). This menu does not create or correct learning material. Pending observations are not scored task packages. Existing material services own validation; selecting a package does not modify its acceptance criteria.

A confirmed candidate waits for human adoption. This feature does not establish model quality, grant activation to an algorithm, or improve arbitrary code/workflow/state. See [Automatic search](../../../../lab/improvement/automatic/README.md), [Original task experiments](../../../../lab/improvement/experiments/README.md), and [Task packages](../../../../lab/improvement/tasks/README.md).

The built-in terminal registers one improvement command. Programmatic search remains available through its independent interaction contract. Standalone benchmark evaluation belongs to the optional Eval CLI.

```bash
.venv/bin/python -m unittest tests.interactive.test_improvement tests.interactive.test_improvement_back tests.interactive.test_benchmark_events tests.interactive.test_confirm_navigation tests.workflows.test_benchmark_improvement -v
```

Offline checks use fake Providers, controllers and original-task executors. Input and display come from [I/O](../../io/README.md) and [Rendering](../../rendering/README.md). No new environment variables.

Registered I policy targets use the same search and candidate menus. DreamRSI's preview declares its trigger, material requirements, feedback, generation, acceptance and activation. Task packs describe the underlying H tasks; the method projects them to the I comparison. Missing histories or independent tasks reject the preview. Manual initiation remains separate from configuration; no background scheduler is installed.
