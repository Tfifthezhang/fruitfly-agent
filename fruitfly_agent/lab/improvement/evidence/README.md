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

Results carry the returned resource identity and character intervals. Projections
separately retain original source locators; reading a projection does not prove
that its original bytes were supplied. A text citation ID
identifies the actual returned source span, not the whole file. Catalog entries
are navigation, not proof that their source contents were read. Empty matches,
unsupported binary data and collection failures remain distinct. Page sizes bound
individual responses; cumulative supply is bounded separately. Private verification inputs remain
outside development grants.

| File | Responsibility |
|---|---|
| `configuration.py` | Strict read/catalog/search limits shared by editor and evaluator |
| `rounds.py` | Cross-round references to hypotheses, receipts, assessments and selections |
| `batch.py` | Compact execution table, observation supply and deterministic batch coverage |
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

The overview includes actual output, final-answer state, file counts and gaps.
Source lists remain behind `sources_path`; file catalogs are paged separately.
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
load further paths. All registered resources remain granted through the existing reader. External
source locators require explicit supplementation before their bytes are granted.

Single-task root indexes likewise keep source paths behind paged catalog access
and describe component identities without embedding complete component text.
See the [development guide](../DEVELOPER_GUIDE.md) for portable stage bundles.

## Bound an investigation

`defaults.yaml` owns all read, catalog, search and supply numeric defaults.
Typed settings derive their defaults from this package resource; Python retains
validation and hard response-size limits. Stage allowances override cumulative
supply for an invocation.

`evidence.supply.max_characters` defaults to 256000 and `max_pages` to 64.
The bundled reader shares those cumulative limits across read/search, including
repeated pages. A search response counts once regardless of its number of matched
source spans; every returned character and exact citation still counts. The tool facade additionally bounds catalog/read/search calls.
Exhausted reads return `budget_exhausted`, no source citation, and a request to
submit using existing evidence with uncovered scope declared. Invocation request
count is bounded by max_pages plus supply.completion_requests (default eight) opportunities to finish. A request
measurement checks input, uncertainty margin and output reserve before Provider
execution; estimates retain their declared quality. Context exhaustion stops with
`evidence_context_budget_exhausted` instead of sending another oversized request.

Search defaults exclude harness content and explicitly supplemented `originals/`.
Specify granted paths to search those originals. Host reads emit
`evidence-host-read`; `evidence-page` and supply receipts identify content actually
returned to the role. Neither event proves semantic understanding or citation.

Eval supplies one compact reading trajectory, task and final-answer material,
execution facts and an external source catalog. Text/argument excerpts declare
original lengths and truncation; each step locates its original source span.
The catalog is metadata, not an original-byte grant. Deep reads require an explicit
hash-checked supplement through the [Eval adapter](../../../../fruitfly_eval/improvement/README.md).
Unpacked external bytes remain unavailable after source removal. Existing retained
batches remain immutable; rebuilding never reconstructs unknown historical state.

Organizer and historical Editor workspaces share `context/overview.json`,
`context/executions.json` and `context/coverage.json`. Execution resources use
`context/executions/<run-id>/` in both roles, so newly organized references are
readable by the Editor without changing their source identity. Batch counts cover
all supplied records; they do not imply all trajectories were read. Per-record
observations stay distinct from status and missing diagnostics remain unknown.

## Delegate assigned evidence

`delegation.py` builds immutable child views from exact parent-granted paths. It
uses the existing Subagent service and exposes only its configured read-only tool
subset plus validated findings submission. Parent and child workspaces keep
separate direct-reading/citation receipts while sharing supply and request
counters. Accepted findings record delegated citations separately; copying a
citation into prose or reading a directory does not authorize it.

Run supplies explicit persistent role/child Sessions and Provider lifecycles.
Enable the stage control through the [developer guide](../DEVELOPER_GUIDE.md#delegate-read-only-evidence-investigation).
Offline execution checks are in `tests.run.test_research_delegation`; CLI wiring
and guide publication are covered by `tests.experiments.test_stage_cli`.

`defaults.yaml` also owns session entry/repair guidance and evidence/findings tool
descriptions. `instructions.repair` substitutes the literal `{error}` marker; it
does not evaluate templates. Typed settings validate bounded nonempty text.

## Retain incremental organization

`parts.py` supplies `catalog_parts` and `read_part` only when the host provides a
durable part store and retention is enabled. Owner defaults declare retention and
tool instructions. Validated child findings are saved before parent integration.
Current grants, exact source hashes, worker/model settings and mission/implementation
conditions determine eligibility. Historical source citations remain delegated
provenance; reading a derived part never becomes a direct original-reading receipt.
See [reuse operations](../DEVELOPER_GUIDE.md#reuse-completed-organization-parts).

