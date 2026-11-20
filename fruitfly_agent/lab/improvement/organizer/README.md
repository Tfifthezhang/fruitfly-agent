# Organize Evidence for Reading

[Up: Improvement](../README.md)

The organizer is a peer of the editor and assessor. It structures granted records
into compact navigation and attributable investigation findings. Each finding
separates facts, causal hypotheses, counterevidence and unknowns. Hypotheses are
unverified leads; proposing candidate changes belongs to the editor. The organizer has no candidate writes, task executor or activation.

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
`instructions.organize` and `instructions.extract`. Schemas, grants, source bookkeeping and execution remain
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


The model submits the current guide format with `schema_version: 2`, `sections`
and `findings`. Each fact contains `text` and its own nonempty `sources` array.
A finding contains `issue_id`, `signal`, `facts`, `hypotheses`, `counterevidence`,
`unknowns`, `run_ids`, `control_ids` and `status`. At most 16 findings are accepted.
Empty findings remain valid with a sourced explanation in sections.

| Field | Meaning |
|---|---|
| `run_ids`, `control_ids` | Distinct affected and contrasting executions from supplied records |
| `status` | `ready_for_proposal`, `needs_evidence` or `not_supported`; a research judgment, not verification |
| `unknowns` | Objects with `question`, relative `materials` and `availability` (`not_read`, `not_granted`, `unavailable`, `unknown`) |
| `hypotheses`, `counterevidence` | Concise strings; neither collection completeness nor causal proof is implied |

[publication.py](publication.py) publishes `organization/index.json`, individual
`findings/<issue-id>.json`, `coverage.json` and `gaps.json` alongside the readable
guide, batch, parts and sources. Index entries include an immutable qualified
`issue_ref`. Editors can read issue details instead of paging the whole guide.
Historical unversioned guides remain readable as attributed input; they do not
acquire per-fact citations or coverage retroactively.

Coverage derives from actual returned ranges and child lifecycle snapshots. It
separates selected cases, direct read ranges, search excerpts and delegated
citations. Failed child investigations remain visible even when a parent publishes
useful partial findings. No byte count establishes comprehension. Each fact's
citation is checked for supply and scope, not semantic entailment.

Use the deterministic batch statistics before investigation. Preserve unknown
counters and account for exceptions. Observing expensive behavior in a successful
case does not establish efficiency or exclude improvement. Detailed grants come
from the independent [selector](../evidence_selection/README.md). Selection and
catalog navigation never establish full original reading.

Prepared hosts preserve configured context mechanisms and scoped archive
readback. When [work products](../../agents/work_products/README.md) are enabled,
roles checkpoint progress and can submit an exact saved JSON revision through
the same final validator. Rejected fields can be patched without retransmitting
the complete document. Direct Lab embeddings without a prepared host retain
minimal execution and record `role-runtime-mode`; they do not inherit ambient
configuration or claim an installed context policy.

## Check and hand off a large investigation

`check_organization` validates a draft without publishing or ending the role.
Use bounded case groups and separate recurring Agent behavior from collection
quality findings. The published `provenance.json` maps returned text citations
to immutable bytes and character intervals. Failed workers remain explicit;
validated incremental findings survive parent failure.

Organization draft checks collect independent section/finding errors before
returning; final submission still validates the complete guide and unique issue
identities through the same owner.

## Inspect task-local organization

A grouped batch schedules task-local units from granted event indexes. Each
unit lists its events and the preceding event for continuity. Extraction reads
the task instruction, event metadata and authorized event bodies or exact
source intervals. The unit exposes event-specific paths for source reads.
An interval shared across units remains available to group synthesis and is
marked unavailable to the local unit. Extraction returns short event-attributed
observations. The synthesis Agent can consult the unit index and retrieve
granted source spans. Deferred, missing and unavailable units remain visible.
The backend-neutral reflection packet records task and execution identities,
exact references, source-declared observations and the synthesized findings.

Set `parameters.settings.extraction_model_requests` to bound all local extraction
requests for one grouped invocation, including retries and follow-up reads.
A value of zero defers model extraction while preserving the unit queue.
Extraction leaves the shared completion reserve available for synthesis.
The packet reports consumed extraction requests, unit reads, and direct unit
citations in synthesis. Citation coverage records links in the guide.
