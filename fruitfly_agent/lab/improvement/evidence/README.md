# Navigate Execution Evidence

[Up: Improvement](../README.md)

Existing Agent and execution hosts retain raw records. This module organizes
those records without another recorder or model request. Editors and evaluators
share the same granted evidence service.

| Layer | Content |
|---|---|
| Overview | Task, output excerpt/reference, deliverables, termination and usage |
| Event directory | Source spans, event kinds, timestamps and reported durations/status |
| Originals | Complete messages, commands, outputs, files and execution facts |

`organize_evidence` derives immutable `evidence/overview.json` and
`evidence/events.json` resources after collection. They are rebuildable views;
originals remain authoritative. Incomplete or unindexed sources are explicit.
A successful tool status does not establish success of every command it contains.

| Operation | Behavior |
|---|---|
| `catalog` | Page granted paths or filter/sort an event directory |
| `search` | Literal search over one or more granted sources, with continuation |
| `read` | Original text pages or supported images |

Results carry original identities and character intervals. A text citation ID
identifies the actual returned source span, not the whole file. Catalog entries
are navigation, not proof that their source contents were read. Empty matches,
unsupported binary data and collection failures remain distinct. Page sizes bound
individual responses, not cumulative reading. Private verification inputs remain
outside development grants.

| File | Responsibility |
|---|---|
| `configuration.py` | Strict read/catalog/search limits shared by editor and evaluator |
| `rounds.py` | Cross-round references to hypotheses, receipts, assessments and selections |
| `indexing.py` | Deterministic overview and event extraction |
| `catalog.py`, `query.py` | Paged navigation and literal retrieval |
| `resources.py`, `access.py` | Immutable access and supply receipts |
| `tools.py`, `session.py` | Agent-facing access and role invocation composition |
| `__init__.py`, `task_sets.py` | Detached single-task and task-set workspaces |

The public `EvidenceReader` contract is in
[Improvement contracts](../../../improvement/contracts/evidence.py). Retrieval can
be replaced through `reader_factory(workspace, settings=EvidenceSettings(...))` on
`AgentEditor` or `ModelEvaluator`, without changing evaluator policy. The reader
must preserve grant checks, exact source spans and supply receipts. The bundled
reader loads source files in host memory; a disk index is not implemented. The bundled implementation uses
no vector database, generated summary or extra retrieval Agent.

Offline checks: `tests.lab.test_evidence_index`, `tests.lab.test_search_reporting`,
`tests.lab.test_improvement_configuration`.

Cross-round navigation contains relationships and references, not a second ledger
of copied observations. Existing candidate manifests retain `expected_effect`;
assessment and selection artifacts retain their own judgments and assurance.

## Inspect coverage and source relationships

The organizer also produces `evidence/coverage.json` and `evidence/sources.json`.
Coverage separates collection, parsing, indexing, outputs, usage and identity.
Each dimension is complete, partial, unknown or not applicable. Summary `complete`
means scoped evidence completeness; `execution_diagnostics_complete` preserves
the separate execution fact. A missing capture receipt, unindexed required source
or unknown usage cannot become complete merely because terminal diagnostics exist.

JSONL splits only at physical LF boundaries, preserving CRLF and Unicode character
coordinates. A malformed record remains an explicit gap; valid records are still
indexed. Formatted ATIF steps, JSON arrays and request-receipt arrays retain original
source ranges. Tool calls/results join by source and call ID, including unmatched
results. Request, operation, phase and status fields survive where recorded.
ATIF is marked as a derived view; navigation entries must not be counted as extra
executions. Existing execution facts remain the authority for aggregate counters. Consecutive streaming deltas share one navigation range with a record count; their full original text remains pageable.

The overview includes actual output, final-answer state, deliverables and gaps.
Reorganization derives views from current original identities and invalidates stale
overviews. Original bytes remain unchanged. `catalog` can additionally filter an
event directory by tool name/call ID, request ID, operation ID, phase or status;
cataloging still grants no source-content citation.

| File | Additional responsibility |
|---|---|
| `decoding.py` | Format recognition and original character ranges |
| `events.py` | Event normalization and source-local relationships |
| `coverage.py` | Separate evidence dimensions and explicit gaps |

[Eval](../../../../fruitfly_eval/README.md#organize-retained-evidence) can materialize
these views offline after a benchmark. This module has no Harbor dependency and
performs no collection, model request or container operation.

Evidence completeness applies to registered records and selected captured file
versions. It does not prove that every task-specific output requirement is known
or met; file scope and exclusions remain visible in the capture manifest.

## Keep batch entry points compact

The task-set `INDEX.json` lists the task directory, evaluation metadata, edit
grants and organized-view references. It records reference/task counts rather
than repeating every archived file path. Use `catalog` with a task prefix to
load further paths. All original resources remain granted through the existing
reader; compact navigation does not truncate the evidence collection.

Single-task root indexes likewise keep source paths behind paged catalog access
and describe component identities without embedding complete component text.
See the [development guide](../DEVELOPER_GUIDE.md) for portable stage bundles.
