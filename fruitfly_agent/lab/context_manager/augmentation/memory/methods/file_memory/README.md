# File Memory

[Up: Memory](../../README.md)

Use attributed user notes across sessions and workspaces. H `file-memory` controls when to
read, extract and consolidate them. S `memory-library` contains the adopted notes.
Normal maintenance changes S through the host; it uses no Improvement editor or
evaluator. I contains only those improvement strategies themselves.

## Enable and read

Memory and automatic upkeep are enabled by default. The configuration menu
shows Memory with File memory as its implementation. It exposes automatic
automatic upkeep and the two thresholds. Advanced instructions and budgets use the
ordinary H component document. Disabling Memory removes its reading and upkeep;
disabling Memory removes reading and manual upkeep. Disabling automatic upkeep
preserves reading and `/memory run`. Neither action deletes saved notes.

Each request receives descriptions and resource locations. Bodies are read only
when the model calls `read`. The bounded directory includes an `INDEX.md` resource
for complete discovery. Resources are immutable within a runtime and remain on the
host when file/shell execution uses a remote environment. They cannot be written
through file tools. Assembly and directory loading make no model requests.

## Maintain notes

| Trigger | Default | Meaning |
|---|---|---|
| Extraction | 8000 | New original user-input characters since the processed cursor |
| Consolidation | 50 | Completed user turns since the last consolidation |

Counters and evidence identities accumulate in the shared memory store at
`.fruitfly/memory/state.json`. Run hosts can inject `user_root` to share one memory store across workspaces.
The default stores memory in the current workspace. Assistant output and tool
results are not extraction evidence. Scheduling
occurs while idle; `/memory run` manually requests the same owner-validated
pipeline below thresholds. Both paths use the same batch journal, validation,
atomic publication and visible model activity. Pending proposals suppress
duplicate work. A lazy
`models.roles.memory_maintenance` binding inherits executor unless explicitly
assigned another catalog alias. Empty consolidation and unchanged content already consolidated with the same
instructions make no model request.
Invocation input/output and timeout bounds are declared in [defaults.yaml](defaults.yaml).
Failed or cancelled work does not advance successful cursors. Explicit retry
remains available; no periodic model polling is used.

Validated maintenance results and successful cursors publish atomically. A library committed by another session is
refreshed through checked runtime preparation before the next foreground task.
Refresh preserves the current conversation path and uses the ordinary assembler.
Preparation failures let the task continue with the previous runtime and expose a
refresh error through `/memory`. The saved library remains published. `/memory`
shows the location, automatic trigger status and next command; `/memory details`
lists notes, counters and pending updates. `/memory run`, `/memory read ID`,
`/memory commit UPDATE`, `/memory reject UPDATE` and `/memory retry OPERATION`
use the host's retained-state capability. Commit prepares
and starts a replacement runtime before activation. Failed preparation leaves the
active runtime, canonical history and pending status intact. Sources are never
rewritten. One-shot tasks disable user and workspace maintenance services and use frozen
initial content from their selected configuration.

## Recover maintenance

The host journals immutable evidence, the base library revision, algorithm input
identity, observation time and each model response. Completed batches are reused
when a later batch is interrupted. A call recorded as started without a durable
response requires `/memory retry OPERATION`, which permits another potentially
paid call. New input cannot authorize that replay. Invalid responses retain the
input cursor; explicit retry regenerates the failed batch while keeping earlier
responses. Recovery requires the captured algorithm configuration. Restore that
configuration before resuming an interrupted batch. `/memory discard OPERATION`
releases a known failed batch while retaining its responses and unprocessed
evidence. Use it after a base revision conflict before generating against the new
revision. Unknown calls still require retry authorization.

Use `/memory import WORKSPACE` once for legacy project checkpoints. Import verifies
source artifacts, merges identities, keeps project applicability and unknown
operations, and publishes one checkpoint. Repeating an unchanged import is safe.
Resolve conflicting identities or pending batches explicitly. Source checkpoints
remain available. Import does not call a model; retry is a separate action.

New notes use `user` scope and retain applicability for project-specific facts.
Historical `project` notes retain their scope. Store publication and the revision
loaded by each session are displayed separately. Bodies stay on-demand.

## Structure retained entries

[models.py](models.py) and [validation.py](validation.py) own the strict schema.
Kinds are `profile`, `preference`, `feedback`, `project` and `reference`. They
distinguish user/role facts, preferences, corrections, project knowledge and
external references. Each note has a stable identity, subject, concise reading
trigger, body, applicability, status, supersession and attributed provenance.
Session/message evidence and observation time identify the source. Scope,
identity and provenance are protected during optimization. Candidate text cannot
fabricate new sources. Withdrawn or superseded notes stay out of the visible directory.

## Improve H and S independently

| Surface | Editable content | Protected content |
|---|---|---|
| H `file-memory` | Reading, extraction, consolidation, thresholds and invocation bounds | Workspace namespace and model bindings |
| S `memory-library` | Existing note descriptions, bodies and applicability | IDs, sources, scope and lifecycle metadata |

The H target requires `memory-learning`. This registered execution freezes
disjoint development and verification packages. Training inputs alone reach the
maintenance worker; expected evaluation answers remain private. Each paired
trial clones the same initial memory, applies validated updates locally and
executes downstream validation/holdout tasks. Production retained state is never
written by the trial. Ordinary task runners cannot claim to evaluate learning
instructions without this capability. Independent verification is required for
persistent improvement publication; normal owner-validated memory upkeep is a different
operation. The generic experiment source can select `execution: memory-learning`.

## Files and checks

| File | Owns |
|---|---|
| [registration.py](registration.py), [state.yaml](state.yaml) | H definition, S surface and installer |
| [algorithm.py](algorithm.py), [index.py](index.py), [resources.py](resources.py) | Directory projection and immutable body reads |
| [config.py](config.py), [maintenance.py](maintenance.py) | Two thresholds and bounded generation |
| [trials.py](trials.py) | H learning executor through shared paired-episode contracts |

Run `tests.run.test_memory_lifecycle`, `tests.lab.test_memory_comparison` and
`tests.workflows.test_memory_skills` offline. Model usefulness, long-term conflict
resolution and external services require separately authorized quality studies.
