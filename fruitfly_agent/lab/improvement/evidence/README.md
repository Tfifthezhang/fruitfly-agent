# Evidence and Receipts

[Up: Improvement](../README.md)

[__init__.py](__init__.py) builds detached editor workspaces containing original
task inputs, execution trajectories and deliverables, candidate changes and
attributed experience. Evidence paths are read-only; only registered candidate
paths are writable. Read/write events retain content identities. `MemoryArtifacts`
is an embedding/test capability; Run supplies durable byte storage.

[receipts.py](receipts.py) defines `TaskReference`, `TaskRunEvidence` and
`EvidenceArtifact` for optional official executors. Runtime, conditions,
environment, task material and invocation counts must match the authorized trial.
Official reward fields remain private in behavior-based editing. Eval consumes
these public values without defining the runtime workflow.

[reporting.py](reporting.py) reads historical reports and validates their journal
and task-snapshot references. Missing scores and usage stay unknown. Historical
report readers do not restore the removed search engines or grant adoption.

A tool workspace is a capability boundary, not an OS sandbox for trusted Python
extensions. Entire evidence workspaces are bounded; text is paginated instead of
silently truncated. Offline checks: `tests.lab.test_improvement_pipeline`,
`tests.lab.test_search_reporting`, `tests.workflows.test_benchmark_improvement`.
