# Python Function Improvement

[Up: Improvement Examples](../README.md)

Improve active prompt or Skill guidance using short Python function tasks. The candidate is text; generated Python is a scored task output, not deployed code. No live-model improvement has been measured for this example.

## Files

| File | Purpose |
|---|---|
| [pack.json](pack.json) | Schema 2 manifest, direction, compatible targets, and scoring policy |
| [cases.json](cases.json) | 8 training and 4 selection cases |
| [holdout.json](holdout.json) | 6 independent cases, excluded from search |
| [baseline.txt](baseline.txt) | Optional reference prompt, not automatically activated |
| [references.json](references.json) | Reference implementations for offline material checks |
| [results-template.md](results-template.md) | Record actual outputs, failures, and identities |

Each score is the fraction of function checks passed; aggregate scores weight cases equally. Checks distinguish `False` from `0`, evaluate declared exceptions, and optionally reject argument mutation. Different correct implementations can pass.

## Install and check

Run from the project root; the destination must not exist:

```bash
mkdir -p .fruitfly/improvement/task-packs
cp -R examples/improvement/python_functions .fruitfly/improvement/task-packs/python-functions
.venv/bin/python -m fruitfly_agent.lab.improvement.tasks.verification check .fruitfly/improvement/task-packs/python-functions/pack.json
.venv/bin/python -m fruitfly_agent.lab.improvement.tasks.verification self-check .fruitfly/improvement/task-packs/python-functions/pack.json
```

These checks make no model requests. See [Task packs](../../../fruitfly_agent/lab/improvement/tasks/README.md#python-function-cases) for acceptance syntax and execution limits.

## Search and review

| Step | Action |
|---|---|
| 1 | Start the terminal with a configured model; no improvement switch is required. |
| 2 | Record the active prompt hash from `/status`. |
| 3 | Open `/improvement`; expand **Target**, select the object and algorithm, then set **Task** to the installed Python pack. |
| 4 | Accept or edit direction; verify 8 train / 4 selection, model, budgets, and restricted execution policy. |
| 5 | Explicitly confirm search. **Model requests may incur charges.** |
| 6 | Review evaluation, usage, differences, text, and scope. |
| 7 | Confirm **Set as next-session default** or **Set default and start a new session**. |

The active target supplies the baseline; selecting the pack does not load `baseline.txt`. `/status` observes progress and `/cancel` stops search. Latest candidates do not guarantee better results. Use **Configure → prompt** to preview and select task results for future sessions.

## Test independently

For each of the 6 holdout cases, send only its input in a new empty session with the same model. Save every response and failure. These responses are real model requests and may incur charges. Score saved output offline:

```bash
.venv/bin/python -m fruitfly_agent.lab.improvement.tasks.verification score examples/improvement/python_functions/pack.json --case holdout-001 --answer-file /tmp/function-answer.py
```

Compare baseline and candidate under the same model, materials and policy. Selection scores are not independent holdout evidence. The [verification policy](../../../fruitfly_agent/lab/improvement/verification/README.md) runs independent comparison before persistent publication. Adoption remains an explicit human decision.

| Boundary | Scope |
|---|---|
| Function runner | POSIX restricted Python subset; no imports, files/network/processes, classes, or third-party dependencies |
| Limits | Per-case time/CPU limits; Linux memory limit; kill/reap on cancellation |
| Correction | The public task-material API can update training acceptance without a model request. Daily recording is configured separately. |
| Evidence | Export explicitly; [retention](../../../fruitfly_agent/lab/improvement/README.md#results-and-retention) protects referenced contents but is not permanent research storage. |

Do not save holdout cases into train. A restricted function runner is not a general code sandbox. Full contracts belong to [Task packs](../../../fruitfly_agent/lab/improvement/tasks/README.md).
