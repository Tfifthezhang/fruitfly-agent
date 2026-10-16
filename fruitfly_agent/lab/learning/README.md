# Learning Material Production

[Up: Lab](../README.md)

Collect completed task observations independently of [improvement](../improvement/README.md).
Configuration enables collection; it does not start search or adopt a candidate.

## Enable recording

Enable **Configure → mechanisms · learning → Learning materials → task-material-recording**,
save, and start a new session. Recording is disabled by default. Detailed policy
parameters belong in `.fruitfly/config.yaml`:

```yaml
mechanisms:
  - id: task-material-recording
    enabled: true
    parameters:
      trigger: task
      batch_size: 4
      max_records: 100
      max_chars: 16000
```

This is a mechanism-list fragment, not a complete profile. No model calls occur.
Task input and output are stored locally; do not enable collection for material
that should not be retained.

| Parameter | Behavior |
|---|---|
| `trigger: task` | Process after a submitted task finishes |
| `trigger: batch` | Process at `batch_size`; close drains the remainder |
| `trigger: session` | Process when the runtime closes or is replaced |
| `max_records` | Maximum distinct task observations in one runtime |
| `max_chars` | Skip oversized observations without truncation; reject oversized processed material |

## Keep evidence separate from observations

`RecordingProcessor` emits **pending** material. An Agent stop reason or answer
is not a correctness label. `LearningMaterial` distinguishes pending, verified
and rejected material; verified material requires acceptance and evidence.
Processor implementations are trusted injected capabilities, not proof that
their claimed evidence is correct.

Run stores attributed schema-1 records under `.fruitfly/learning/materials/`.
Records retain input, output, outcome, source Session and runtime identity. They
are training material, never automatically assigned to selection or holdout.
Pending records are not task packs and cannot be selected as scored tasks.
No built-in method turns weak feedback into trusted answers or scores.

## Extend processing

`LearningEngine` accepts an asynchronous processor and persistence callback.
Catalog exposes `build_learning`, `LEARNING_POLICY_COMPONENT`, and
`LEARNING_PROCESSOR_COMPONENT` for explicit host assembly. A custom definition
can provide policy and a processor independently of an enabled improver. It must
declare its effects, budgets, model roles and acceptance validation. Core owns
neither task completion policy nor material processing.

Application awaits task-triggered work under its submission lifecycle, preserves
a successful Agent result on an ordinary collection error, and exposes the error
through `last_error`. Cancellation propagates. Processor failure or cancellation retains an interrupted observation in memory
and never automatically replays unknown work. A persistence retry reuses the
already processed material. Process crashes do not recover observations that
were only queued in memory. No scheduler or detached
background worker is installed. In-process limits do not sandbox custom Python.

| File | Responsibility |
|---|---|
| [engine.py](engine.py) | Bounded queue, material contract, default recording method |
| [registration.py](registration.py) | Disabled-by-default policy and configuration grouping |
| [Run learning](../../run/learning/README.md) | Lifecycle binding and persistence |

No module-specific environment variables.

```bash
.venv/bin/python -m unittest tests.lab.test_learning tests.workflows.test_task_packs
```
