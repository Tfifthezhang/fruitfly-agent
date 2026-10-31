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
| `indexing.py` | Deterministic overview and event extraction |
| `catalog.py`, `query.py` | Paged navigation and literal retrieval |
| `resources.py`, `access.py` | Immutable access and supply receipts |
| `tools.py`, `session.py` | Agent-facing access and role invocation composition |
| `__init__.py`, `task_sets.py` | Detached single-task and task-set workspaces |

The public `EvidenceReader` contract is in
[Improvement contracts](../../../improvement/contracts/evidence.py). Retrieval can
be replaced through `reader_factory(workspace, page_characters=...)` on
`AgentEditor` or `ModelEvaluator`, without changing evaluator policy. The reader
must preserve grant checks, exact source spans and supply receipts. The bundled
reader loads source files in host memory; a disk index is not implemented. The bundled implementation uses
no vector database, generated summary or extra retrieval Agent.

Offline checks: `tests.lab.test_evidence_index`, `tests.lab.test_search_reporting`,
`tests.lab.test_improvement_configuration`.
