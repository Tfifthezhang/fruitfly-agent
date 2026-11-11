# Organize Evidence for Reading

[Up: Improvement](../README.md)

The organizer is a peer of the editor and assessor. It structures granted records
into batch directories, task entries, timelines and attributable summaries. Finding
optimization signals, interpreting causes and proposing candidate changes belong
to the editor. The organizer has no candidate writes, task executor or activation.

`LayeredOrganizer.organize(OrganizationRequest, StageServices)` returns an
immutable `EvidenceView`. It uses the existing Core Agent runner, shared evidence
reader and strict submission. Each summary cites a returned source span. Original
bytes stay unchanged. Missing instructions, outputs and collection coverage remain
visible. A source citation is not a certificate that a downstream editor read it.

| File | Responsibility |
|---|---|
| `instructions.py`, `registration.py` | Owner-validated I instructions and Catalog configuration |
| `improvement.py` | Construct isolated authorized organizer candidates |
| `workspace.py` | Batch/task navigation over immutable references |
| [Layered method](methods/layered/README.md) | Concrete model role and default instructions |

System `models.roles.organizer` selects the model or inherits executor. The
`improvement-organizer` I component exposes `instructions.system` and
`instructions.organize`. Schemas, grants, source bookkeeping and execution remain
protected. `candidate_organizer` validates an I document and applies its instructions
to real role execution. Fixed-I studies that select this component install the candidate into the inner
reading role before editing. An isolated trial is not proof for persistent adoption;
that still requires an independent comparison through the owning host.

Model organization is optional. Assessors and editors can consume imported
batches directly. Explicit organization exposes a reading guide in editor context. Embeddings can inject `StageBindings.organizer`. Standalone
research activities can organize retained batches without preparing containers.

An explicit `OrganizationRequest.instruction` is included in the role mission
as invocation requirements. Its copy in `context/batch.json` remains provenance;
reading that file is not required to receive the invocation requirements.

Offline checks: `tests.lab.test_organizer`, `tests.improvement.test_research_recovery`.
Fake outputs prove candidate application and attribution, not model summary quality.

## Keep partial work

With stage `incremental.enabled`, completed research child findings survive a
later parent failure. The parent decides useful partitions, optionally reads
applicable retained parts, and submits one integrated guide. Published
`organization/parts.json` records new and reused references separately from final
sections. It does not assert complete evidence coverage. See the
[developer recipe](../DEVELOPER_GUIDE.md#reuse-completed-organization-parts).

