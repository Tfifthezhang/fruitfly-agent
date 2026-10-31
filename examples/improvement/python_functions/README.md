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
| 1 | Prepare the independent default Agent/model files and credentials. |
| 2 | Select `source: files` and the pack in the task document referenced by experiment `tasks`. |
| 3 | For persistent verification, set `scope: persistent` in the referenced comparison document and choose suitable independent phase times. |
| 4 | Run `fruitfly-agent-lab improvement check`, then explicitly `improvement run`; model calls may incur charges. |
| 5 | Inspect the linked candidate and evidence. `rsi run` performs verified adoption into its experiment copy. |

The active target supplies the baseline; selecting the pack does not load `baseline.txt`. The experiment CLI records progress and supports `stop`. Latest candidates do not guarantee better results. The run retains its separate configuration and evidence for review.

## Test independently

For each of the 6 holdout cases, send only its input in a new empty session with the same model. Save every response and failure. These responses are real model requests and may incur charges. Score saved output offline:

```bash
.venv/bin/python -m fruitfly_agent.lab.improvement.tasks.verification score examples/improvement/python_functions/pack.json --case holdout-001 --answer-file /tmp/function-answer.py
```

Compare baseline and candidate under the same model, materials and policy. Selection scores are not independent holdout evidence. The [verification policy](../../../fruitfly_agent/lab/improvement/verification/README.md) runs independent comparison before persistent publication. Task-local selection does not adopt; explicit RSI uses the independent verification policy.

| Boundary | Scope |
|---|---|
| Function runner | POSIX restricted Python subset; no imports, files/network/processes, classes, or third-party dependencies |
| Limits | Per-case time/CPU limits; Linux memory limit; kill/reap on cancellation |
| Correction | The public task-material API can update training acceptance without a model request. |
| Evidence | Export explicitly; [retention](../../../fruitfly_agent/lab/improvement/README.md#results-and-retention) protects referenced contents but is not permanent research storage. |

Do not save holdout cases into train. A restricted function runner is not a general code sandbox. Full contracts belong to [Task packs](../../../fruitfly_agent/lab/improvement/tasks/README.md).
