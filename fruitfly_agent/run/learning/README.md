# Learning Host

[Up: Run](../README.md)

Bind configured [Lab learning](../../lab/learning/README.md) to Application task
completion and workspace persistence. [service.py](service.py) exposes
`RunLearningService.observe` and closes pending batches with its runtime.
Catalog supplies the processor; the host does not implement material algorithms.

Records live at `.fruitfly/learning/materials/<source-hash>.json`. Writes are
atomic; repeated identical source records are idempotent, conflicting records
are rejected. Paths must remain in the workspace. Each record includes source
input/output, Session, runtime identity, material status and training-only scope.
There is no automatic task-pack publication, retention sweep, search or adoption.
Errors preserve queued material while the process remains alive. Unknown processor work is not replayed; persistence retries reuse completed material. No new secrets,
environment variables, network requests or model calls are introduced by recording.

```bash
.venv/bin/python -m unittest tests.lab.test_learning tests.workflows.test_task_packs
```
