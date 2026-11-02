# Reduce Request Context

[Up: Context Manager](../README.md)

Select one method in the Reduction slot. Core validates and durably commits
projections and checkpoints; canonical Session messages remain intact.

| Method | Default | Auxiliary work |
|---|---|---|
| [Layered compaction](methods/layered_compaction/README.md) | Yes, deterministic | Abbreviate old tool results, then archive complete history groups. Optional hybrid mode makes one bounded summary request when needed. |
| [Working memory](methods/working_memory/README.md) | No | Incrementally update bounded task memory from canonical evidence pages. |

Both methods preserve tool pairing and respect signed Provider continuation.
Only smaller fitting projections replace history. Core remeasures the proposed
request before commit. Failed checkpoint persistence stops requests until recovery.
[Measurement](../measurement/README.md) remains a shared service; estimates do not
establish retained-information quality or remote acceptance.

## Retrieve evidence and recover

[History resources](../resources/README.md) expose a deterministic directory,
original public messages and immutable artifacts through ordinary `read`.
Tool arguments/results remain available; private thinking, opaque replay and image
bytes are excluded. Inspect original images when needed. Reading archived evidence
does not repeat an earlier tool operation.

Artifacts live beside Session: layered compaction uses
`SESSION.jsonl.artifacts/reduction/layered_compaction/`; working memory uses
`SESSION.jsonl.artifacts/reduction/`. Recovery validates required hashes and source
identity before continuation. In-memory construction has no cross-process recovery.
Uncommitted artifacts never become active state. The fixed immutable-artifact
allocation is 16 MB per artifact; it is not a selectable optimization mechanism.

## Optimize policy

Both owners expose H parameter targets through the ordinary Catalog path.
Layered compaction grants thresholds, previews, recent-group/tail policy and
readback guidance. Hybrid mode additionally grants summary guidance and request
limits. Mode and model bindings are protected; deterministic mode rejects inactive
summary-field grants. Working memory exposes its update/shrink/readback policy.

A candidate requires `configuration-materialization`, isolated state and actual
execution. Changed policy identity does not inherit auxiliary retry admission.
Source identity, artifact integrity, tool pairing, permissions and outer budgets
are fixed. Retained summaries are execution state, never automatic S updates.

Concrete algorithms, defaults and declarations live under `methods/`.
[inference.py](inference.py) supplies bounded auxiliary calls;
[registration.py](registration.py) and [improvement.py](improvement.py) compose
owner definitions without host dispatch.

Offline checks: `tests.lab.test_layered_compaction`,
`tests.lab.test_layered_compaction_failures`, `tests.lab.test_working_memory`,
`tests.workflows.test_layered_compaction_improvement` and
`tests.workflows.test_working_memory_improvement`.
