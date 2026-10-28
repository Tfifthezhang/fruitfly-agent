# Maintain working memory

[Up: Reduction](../../README.md)

`WorkingMemoryReducer` implements `ContextReducer`. Select
`working-memory-reduction` instead of `compaction`. `WorkingMemoryConfig` declares
strict defaults; `registration.py` registers the method and H candidate fields.

After `update_every_messages` new canonical messages, or at `switch_ratio` of the
input budget, merge previous memory with sequential new evidence pages. Prompts
`update_instructions` and `shrink_instructions` are editable from the first
version. Memory is limited by `memory_tokens`; an oversized update gets one
bounded shortening operation. Only normal, nonblank, final text is accepted.

The code owns `(covered, offset)` and a hash of the canonical source prefix.
The model cannot advance coverage or edit artifact identity. `max_pages` bounds
an update; partial successful coverage can be checkpointed without clearing the
projection. Any failed page preserves the previously committed checkpoint.
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

H candidates may tune both prompts, memory size, update frequency, switch ratio,
pages, auxiliary output/attempt limits and timeout. Outer budgets, coverage and
integrity rules remain protected. Counting is conservative unless a supported
exact Provider counter is selected; bounded text does not prove factual fidelity.
See [shared checks](../../README.md#extend-a-method).
