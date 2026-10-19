# Improvement Feature

[Up: Terminal Features](../README.md)

Use `/improvement [DIRECTION]` to edit one experiment, run it, and inspect results. `TerminalImprovementFrontend` borrows the terminal input/display scope. Notices and final outcomes are returned through `CommandResult` after chat is restored.

| File | Responsibility |
|---|---|
| [panel.py](panel.py) | Experiment draft, target/task/method selection, algorithm descriptions/paths, optional search guidance and typed material/budget inputs |
| [menu.py](menu.py) | Execution confirmation, running view, experiment history and candidate review |
| [command.py](command.py) | Borrow and restore the terminal scope |
| [events.py](events.py) | Original-task event and runner-log display |
| [formatting.py](formatting.py) | Generic activity and usage text |

## Configure one experiment

The panel has four configuration rows: Target, Task, Budget and Evaluation, followed by start/history/return actions. Enter expands a row on the same page. One main section is expanded at a time; switching sections retains the draft. Back/Esc first collapses open algorithm details, then the section, then returns to chat; `q` exits menu mode. Navigation and previews start no model requests or task downloads. Host previews may freeze local evidence.

| Field | Behavior |
|---|---|
| Target | First choose an object under H/S/I, then a compatible algorithm below it; show its distinguishing description and optional Search guidance; Details expands implementation/guide paths and YAML locations |
| Task | Saved packages, benchmark/task sets and declared material fields; unavailable sources explain why |
| Budget | Typed fields declared by the method, with current values and bounds |
| Evaluation | Read-only scoring, acceptance, requirements, implementation details and full preview; optional long-text viewer |

Targets use object-owned readable labels. New drafts require explicit target and algorithm selection, even for a single algorithm; remembered defaults are suggestions. Hosts without method metadata retain their configured algorithm after target selection. An empty compatible-method catalog blocks preview and execution; it never falls back to a default. Methods with incompatible roles or formats are omitted; compatible methods missing runtime dependencies remain visible with reasons. A sole usable saved package is preselected. Switching targets preserves compatible choices; incompatible algorithms require reselection. Compatible budget overrides survive algorithm changes, while method-specific overrides reset with a notice. Tasks and source support are rechecked. Policy targets can project compatibility to an underlying target. Missing histories/materials/capabilities remain visible; a failed benchmark catalog does not block saved tasks.

Expanded sections scroll to the focus on small ANSI terminals. Focus follows action identity when rows change. Confirmation and optional long details use PageUp/PageDown without changing the selected action. History/candidate lists retain pagination.

Field input retains the panel and selected row while displaying a labeled input area below it. Live text, cursor edits, descriptions, current values and type/range hints remain visible. Enter submits, blank keeps the value and Esc or `/cancel` cancels. `/clear` clears guidance or string fields. Invalid values preserve the previous value. During input, `q`, spaces and digits are text. Fields do not enter chat history. Internal tuning and JSON overrides are absent from the menu. Each algorithm has a Details action for its configuration file, profile and mechanism location; YAML and programmatic previews retain parameter validation. Search guidance appears only when declared by `direction_help`; task defaults may prefill it, and unsupported guidance from another method is not sent. Evaluation and acceptance remain defined when guidance is empty.

**Start improvement** creates a fresh preview and one execution confirmation, initially selecting Cancel. The confirmation binds the target, direction, method, normalized parameters, parent and task materials. Editing a field requires a new preview. Benchmark confirmation authorizes its displayed downloads, containers, baseline, search and independent confirmation. Real model work may incur charges. No algorithm-specific fields or branches belong to this frontend.

## Inspect a running experiment

Saved packages and benchmarks share the running/result flow. POSIX raw menu input supports bounded polling through the existing reader, so progress can update while offering **Return to chat** and **Cancel improvement**. Returning keeps Application-owned work running; use `/status`, `/cancel`, or reopen `/improvement` and select Results and history. The running view measures the current batch, not overall completion. Redirected/non-polling input waits for completion and cannot read cancellation commands during the job. Ctrl+C cancellation remains owned by Application.

Original-task events retain complete tool output and runner logs. A completed, failed or cancelled job opens its result view. Empty outcomes still show a stopping reason, baseline/usage when measured and verified search logs when produced. **Edit and run again** returns to the current draft without starting work. A completed job is not itself evidence of improvement.

## Review results and candidates

**Results and history** lists submitted runs, including runs without candidates, under the current configuration/profile. Unfinished records after a process restart are shown as interrupted and never replayed. Existing candidates remain available through Saved candidates. History and candidate lists paginate; detail views preserve selection while paging sections.

| Action | Effect |
|---|---|
| Review candidate | Inspect assessment, comparison, usage, changes, full texts and evidence |
| Set as next-session default | Confirm a saved profile/configuration change; keep the current session |
| Set default and start a new session | Confirm the default change and activate an empty session through Application |
| Discard candidate | Reject the stored candidate |

Candidates are already stored; there is no extra save/collection action. Without an activation capability, only the future-default action is offered. Review labels distinguish selection gains, ties, regressions, unknown comparisons and independent confirmation. Adoption still validates parent, scope, configuration, binding and artifact. Histories retain referenced candidates; old candidates are usable only while those checks pass.

`ImprovementClients` injects search, materials, candidates, activation, metadata, history/log queries, waiting and cancellation independently. Existing hosts without history or parameter metadata keep their configured search path; unavailable capabilities do not add execution authority. The feature imports no Lab, Run or Eval implementations. Daily observation collection remains separately configured through [Learning](../../../../lab/learning/README.md); observations without acceptance are not scored task packages.

See [Improvement](../../../../lab/improvement/README.md), [Original task experiments](../../../../lab/improvement/experiments/README.md) and [Task packages](../../../../lab/improvement/tasks/README.md). No new environment variables or automatic adoption.

```bash
.venv/bin/python -m unittest tests.interactive.test_improvement tests.interactive.test_improvement_back tests.interactive.test_confirm_navigation tests.workflows.test_improvement_history tests.workflows.test_benchmark_improvement
```

Offline checks use fake Providers/controllers/executors and local PTYs. They establish interaction and lifecycle behavior, not real model improvement or container integration.
