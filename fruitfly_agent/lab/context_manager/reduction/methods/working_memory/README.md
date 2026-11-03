# Maintain working memory

[Up: Reduction](../../README.md)

`WorkingMemoryReducer` implements `ContextReducer`. Select
`working-memory-reduction` in the reduction slot. `WorkingMemoryConfig` declares
strict defaults; `registration.py` registers the method and H candidate fields.

`models.roles.working_memory` defaults to `{inherit: executor}`. Set a catalog
alias there for an independent memory model. Inheritance follows changes to the
executor while explicit overrides remain fixed. The resolved model identity
participates in checkpoint policy identity.

Periodic maintenance begins only at `maintenance_ratio` of the available input
budget (default 0.5). The first eligible update starts immediately; subsequent
updates require 32 new canonical messages by default. Catch-up pages continue an
existing frozen evidence boundary. At `switch_ratio` (default 0.85), or on overflow,
maintenance can bypass the message interval, but never the failed-page cooldown.
Merge previous memory with sequential new evidence pages. Prompts
`instructions.update`, `instructions.shrink` and `instructions.readback` are
editable through the same working-memory H target. Memory is limited by `memory_tokens`; an oversized update gets one
bounded shortening operation. Only normal, nonblank, final text is accepted.

The code owns `(covered, offset)` and a hash of the canonical source prefix.
The model cannot advance coverage or edit artifact identity. `max_pages` bounds
an update (default 2 pages). `update_timeout_seconds` bounds the entire auxiliary
update (default 20 seconds), including measurement, retries and shortening;
per-call limits cannot extend it. Cooperative cancellation has a separate bounded
retirement allowance. A later failed page preserves the successful continuous
prefix. A failed page records a retry fingerprint and timestamp without advancing
coverage; the same page waits 60 seconds before another attempt. Changed evidence,
memory or policy has a distinct fingerprint. State-only decisions never claim a
projection reduction or overflow recovery.
Clearing requires full coverage, a fitting smaller projection and permission to
rebase Provider continuation. The projection contains the first user task and
the memory artifact; subsequent events append normally. User corrections are
inputs to memory updates and remain available in canonical history.

A checkpoint records exact policy identity, immutable memory hash and source
coverage. Session persistence and projection replacement commit together.
Recovery validates source and artifact identity; missing/corrupt artifacts fail
before continuation. A changed policy rebuilds from canonical evidence rather
than attributing old state to the candidate. Fresh trials use fresh Session and
artifact scopes. Memory is task-local execution state, never automatically S.

H candidates may tune the prompts, memory size, update frequency, switch ratio,
pages, auxiliary output/attempt limits and timeout. Outer budgets, coverage and
integrity rules remain protected. Counting is conservative unless a supported
exact Provider counter is selected; bounded text does not prove factual fidelity.
See [shared checks](../../README.md#optimize-policy).

The method owns its history service and mounts a deterministic index plus original
messages/artifacts through ordinary `read`. It adds no historical tools. See
[memory resources](../../../resources/README.md) for scope and recovery.

## Files and offline checks

| File | Responsibility |
|---|---|
| [algorithm.py](algorithm.py) | Maintenance admission and safe projection switching |
| [maintenance.py](maintenance.py) | Bounded sequential pages, retries and successful-prefix retention |
| [state.py](state.py) | Coverage, frozen boundary, policy/model identity and failed-attempt evidence |
| [config.py](config.py), [registration.py](registration.py), [improvement.py](improvement.py) | Strict defaults, role admission and H grants |

Offline: `tests.lab.test_working_memory`, `tests.lab.test_reduction_safety` and
`tests.workflows.test_working_memory_improvement`. These checks establish control
and integrity behavior, not the quality of generated memory.

## Maintain one parameter definition

[defaults.yaml](defaults.yaml) owns this method's H text and numeric defaults.
Typed constructors and Catalog descriptors read that document. Ordinary default
references follow it on fresh assembly; complete frozen candidates keep their
selected values. Improvement edits `parameters.yaml` through the same grants and
owner validation for prompts and numbers. Model roles, integrity checks and
state/reset/recovery rules retain their existing protected owners.
