# Use cross-session memory

[Up: Information Spaces](../README.md)

Keep attributed project context across conversations. This memory is independent of
Session compression and working memory. The model sees a bounded directory and
reads relevant bodies through the ordinary read tool. A full directory resource
keeps omitted entries reachable when the context directory is bounded. Recall makes no auxiliary
model request. Canonical conversation messages are not rewritten.

## Configure and read

Enable `memory-library` under S, `information-context` and `memory-files` under H,
and the ordinary read tool. `memory-library` owns strict JSON entries in
`parameters.content.documents`. `memory-files` owns `settings.root`,
`settings.max_chars` (4000) and `instructions.usage`. Its root is a resource
namespace, not an automatically scanned writable Markdown store.

| Kind | Retained content |
|---|---|
| profile | Role, experience and durable goals |
| preference | Persistent choices with explicit applicability |
| feedback | Corrections and their reasons |
| project | Background and decisions not directly derivable from source |
| reference | External information locations and when to consult them |

Each entry has a stable ID, project scope, subject, description, body, applicability,
provenance (one source Session per entry), observation time, status and explicit supersedes references. Invalid,
duplicate and cyclic references fail. A later active replacement hides the replaced
entry. Memory is historical context; current instructions remain authoritative.
Global user sharing and machine synchronization are not implemented.

`/memory` shows retained entries, status and pending batches. `/memory read ID` displays one
entry. `/memory commit UPDATE` or `/memory reject UPDATE` reviews a complete batch
while idle. Commit is an attributed human decision, not a measured quality gain.
The active runtime is rebuilt with the same conversation after a commit.

## Maintain memories

Enable H `memory-maintenance` and I `memory-extractor` / `memory-consolidator`.
This explicitly enables potentially paid auxiliary calls. The declared lazy
`models.roles.memory_maintenance` inherits executor unless configured separately.
Reading or inspecting memory never constructs that auxiliary client.

| Trigger | Default |
|---|---|
| New original user-text characters since successful extraction | 8000 |
| New completed user turns since successful consolidation | 50 |

Counters accumulate across Sessions within the configured workspace/profile scope.
Assistant text, tools, expanded resources and image bytes do not increment user
characters. Processing happens only at the Application's idle boundary. Pending
review blocks another conflicting batch. When both thresholds are due and notes
exist, consolidation runs first to avoid starvation from large user inputs. A successful no-change result advances
processing; a rejected batch is not silently generated again. No changed content
means consolidation can skip the model. Source evidence has separate identity from
adopted memory. Secret values and benchmark answers are not valid memory content.

Malformed output fails the complete proposal. Omitted notes stay intact; removal
requires an explicit validated withdrawal. Unknown request outcomes block further generation, including after new input.
Inspect the operation ID in `/memory`, then use `/memory retry OPERATION` to
explicitly permit another potentially paid call. An interrupted running operation
is also treated as unknown on recovery. Malformed responses are recorded as failed
without advancing progress. The host owns cancellation, atomic commits, recovery and retention.
See the [maintenance method](methods/threshold_maintenance/README.md) and
[Run storage](../../../../../run/storage/README.md).

## Improve and isolate

Descriptions, bodies and applicability are S optimization fields. IDs, source
positions and scope remain protected. Directory guidance and character budgets are
H; extraction and consolidation instructions are I. Candidate configurations use
the ordinary Catalog assembly and retain on-demand loading. New notes are added
through attributed maintenance, not by fabricating sources in an optimization edit.
Use `memory-maintenance-comparison` to study exactly one I operation at a time:
`memory-extractor` or `memory-consolidator`. A multi-operation selection fails
before generation rather than silently leaving one changed prompt untested.

Task runners restore frozen S and required resources into an isolated environment.
They do not obtain a production maintenance writer. Frozen content and learning
control state must be recorded when comparing learning conditions. A compatible
execution backend must explicitly support each selected optimization surface.

## Public entries and checks

| File | Responsibility |
|---|---|
| [source.py](source.py), [__init__.py](__init__.py) | Frozen information source and directory-only retriever |
| [models.py](models.py), [validation.py](validation.py) | Attributed entries and explicit changes |
| [resources.py](resources.py) | Read-only resource mounting |
| [registration.py](registration.py), [improvement.py](improvement.py) | H/S declarations, installation and editable fields |
| [defaults.yaml](defaults.yaml), [memory-state.yaml](memory-state.yaml) | Owner defaults |
| [Methods](methods/README.md) | Concrete directory and maintenance algorithms |

```bash
.venv/bin/python -m unittest tests.lab.test_memory_models tests.lab.test_memory_maintenance tests.run.test_retained_state
```

These offline checks establish control flow and data integrity, not recall quality.
The design uses the file-directory and on-demand ideas documented in
[Claude Code memory](https://code.claude.com/docs/en/memory); it does not reproduce
undocumented extraction internals or claim their quality results.

Collections also respect the editable component file budget: their YAML content
encoding is bounded to 118000 characters, reserving owner metadata within the
120000-character component limit. Oversized collections fail admission; retained
entries are not silently truncated.
