# File Memory

[Up: Memory](../../README.md)

Use attributed workspace notes across sessions. H `file-memory` controls when to
read, extract and consolidate them. S `memory-library` contains the adopted notes.
Normal maintenance changes S through the host; it uses no Improvement editor or
evaluator. I contains only those improvement strategies themselves.

## Enable and read

Memory and automatic maintenance are enabled by default. The configuration menu
shows Memory with File memory as its implementation. It exposes automatic
maintenance and the two thresholds. Advanced instructions and budgets use the
ordinary H component document. Disabling Memory removes its reading and upkeep;
disabling only maintenance preserves reading. Neither action deletes saved notes.

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

Counters and evidence identities accumulate across sessions in the same retained
scope. Assistant output and tool results are not extraction evidence. Scheduling
occurs while idle; pending proposals suppress duplicate work. A lazy
`models.roles.memory_maintenance` binding inherits executor unless explicitly
assigned another catalog alias. Empty consolidation and unchanged content already consolidated with the same
instructions make no model request.
Invocation input/output and timeout bounds are declared in [defaults.yaml](defaults.yaml).
Failed or cancelled work does not advance successful cursors. Explicit retry
remains available; no periodic model polling is used.

Generated batches remain pending. `/memory` lists notes, counters and pending
updates. `/memory read ID`, `/memory commit UPDATE`, `/memory reject UPDATE` and
`/memory retry OPERATION` use the host's retained-state capability. Commit prepares
and starts a replacement runtime before activation. Failed preparation leaves the
active runtime, canonical history and pending status intact. Sources are never
rewritten. One-shot tasks disable the workspace maintenance service and use frozen
initial content from their selected configuration.

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
persistent improvement publication; normal reviewed memory upkeep is a different
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
