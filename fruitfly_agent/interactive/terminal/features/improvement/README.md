# Improvement Feature

[Up: Terminal Features](../README.md)

Use `/improvement [DIRECTION]` to configure and explicitly submit a component
workflow. The terminal consumes renderer-neutral contracts and imports no Lab,
Run or Eval implementation.

| File | Responsibility |
|---|---|
| [workflow_panel.py](workflow_panel.py) | Task/input selection, component toggles, generator, exploration, budgets, feedback and scope |
| [menu.py](menu.py) | Confirmation, progress, history, results and candidate review |
| [command.py](command.py) | Borrow and restore terminal input/display scope |
| [formatting.py](formatting.py) | Generic activity and usage |

Task sources include explicit current instructions and input files or saved
packages. Invalid or cancelled field input preserves the prior value. Components
and generators show capability availability. The panel has no benchmark-specific
source, runner or configuration.

Start creates a fresh frozen preview and one confirmation with Cancel selected by
default. Confirmation binds materials, component scope, generator, guidance and
allocations. Navigation and previews start no model work.

Application owns the running job. Polling terminal input offers Return to chat and
Cancel improvement; returning leaves the job running. Non-polling input waits for
completion. Results retain stop reason, selected output, assurance and available
usage. Choosing Return to chat exits the workflow panel too.

History includes empty, failed and cancelled submissions. Unfinished records after
restart are interrupted, never replayed. Logs are read through the host's hash
checks. Candidate review retains pagination and explicit confirmation for future
default changes or fresh-session activation. These operations recheck scope,
parent, configuration, binding and artifacts.

`ImprovementClients` injects workflow, execution, candidate, activation, history and
cancellation capabilities independently. A host without the component workflow
reports unavailable; it does not fall back to an obsolete search engine. Daily
observation collection belongs to [Learning](../../../../lab/learning/README.md).
See [Improvement](../../../../lab/improvement/README.md) and
[Task packages](../../../../lab/improvement/tasks/README.md).

```bash
.venv/bin/python -m unittest tests.interactive.test_improvement tests.interactive.test_improvement_back tests.interactive.test_confirm_navigation tests.workflows.test_improvement_history
```

These checks are offline and establish interaction/lifecycle behavior, not model
quality or real container integration. Model execution may incur charges.

## Choose registered execution and review lessons

**Execution strategy** changes compatible component availability and material
choices from host metadata. **Execution parameters** edits declared string/integer/
number fields. Switching strategies clears incompatible material/component choices
and applies its declared defaults. The terminal contains no concrete execution or
scoring implementation. Start always creates a fresh preview after edits.

For **Editor self-improvement**, follow the [experiment guide](../../../../lab/improvement/improver/README.md).
Progress counts all nested model calls and leaf executions. Results retain stopping
reason separately from assurance. Original references remain candidates for output
selection; no task execution mutates its active components.

Results and history includes **Pending experience** when an independent review
client exists. Inspect lessons and the initial S snapshot, then explicitly confirm
Commit or Reject. Application must be idle; stale commits fail. No lesson is
silently committed when returning to chat or selecting a candidate.
