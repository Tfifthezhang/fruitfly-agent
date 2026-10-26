# Evidence and Receipts

[Up: Improvement](../README.md)

[__init__.py](__init__.py) builds detached editor workspaces containing original
task inputs, execution trajectories and deliverables, candidate changes and
attributed experience. Evidence paths are read-only; only registered candidate
paths are writable. Read/write events retain content identities. `MemoryArtifacts`
is an embedding/test capability; Run supplies durable byte storage.

Hosted execution resources include `execution-facts.json` and optional
`process-assessments.json`. They use ordinary read-only evidence paths and content
identities. Facts retain source references; the editor can inspect the original
trajectory through the same workspace. No auxiliary extraction or summary stage
is required. See [execution facts](../execution/README.md#record-execution-facts).

[receipts.py](receipts.py) defines `TaskReference`, `TaskRunEvidence` and
`EvidenceArtifact` for optional official executors. Runtime, conditions,
environment, task material and invocation counts must match the authorized trial.
Official reward fields remain private in behavior-based editing. Custom executors
can consume these public values without defining the runtime workflow.

[reporting.py](reporting.py) reads historical reports and validates their journal
and task-snapshot references. Missing scores and usage stay unknown. Historical
report readers do not restore the removed search engines or grant adoption.

A tool workspace is a capability boundary, not an OS sandbox for trusted Python
extensions. Entire evidence workspaces are bounded; text is paginated instead of
silently truncated. Offline checks: `tests.lab.test_improvement_pipeline`,
`tests.lab.test_search_reporting`, `tests.workflows.test_improvement_pipeline`.

`session.py` supplies a shared bounded workspace-model transport. Editing and
read-only inspection provide their own policy and tools. Unknown external model
usage remains separate from conservative quota charges in reports.

`task_sets.py` projects authorized development entries and joint evaluation rows;
selection/confirmation content is rejected. `resources.py` supplies read-only
artifact references so original logs need not all be copied into the editable
workspace. Existing text pagination and image handling still apply. This is not
an extraction or summarization stage. Candidate write permissions are unchanged.

## Inspect what the editor received

The selected I feedback component owns `evidence.projection` and default
`evidence.page_characters`. `projections.py` registers pure text views; the bundled
`granted-full` view returns exact pages from already granted originals. It cannot
add private files or change immutable execution facts. Custom embedding sessions
may inject an `EvidenceProjectionRegistry`; the standard config accepts the
bundled registry's IDs.

Each successful read journals `editor-evidence-page` with the original artifact
hash and path. Text receipts include offset/limit, returned interval, total source
characters, truncation, projection implementation and returned page hash. Image
and unavailable binary reads retain their status and size. Full originals remain
in the ordinary artifact store. `context/edit-grants.json` gives the editor the
same owner-normalized field permissions enforced during candidate validation.
