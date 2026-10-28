# Component Editor

[Up: Improvement](../README.md)

[__init__.py](__init__.py) supplies `AgentEditor`, `AgentSelector` and
`AgentReflector`. The editor reads detached evidence and edits only granted
`harness/<component-id>/` paths using list/read/search/write/delete and structured submission tools. It receives
no Bash, production environment, adoption operation or live Session.

[instructions.py](instructions.py) owns validated stage instructions and their I
artifact adapter. Editing I requires an improver-comparison runner. The file-task runner rejects that scope before model work. The registered
[editor experiment](../improver/README.md) executes it through a separate comparison
runner. Candidate validation freezes `system`, `select` and `reflect`; only
`propose`, `invariant`, `domain`, `compose` and the separately granted
`max_tool_calls` and `max_turns` can change. New instruction snapshots
use the `editor-instructions-v3` target contract. Every snapshot must contain all
registered stage fields, `max_tool_calls` and `max_turns`; missing fields are rejected.

The simple strategy uses `propose`; Harness² distinguishes invariant and domain missions.
The composer can retain, revise or reject edits. Every changed component needs a
successfully supplied execution ID. Invalid structural/attribution output allows one repair;
otherwise the original snapshot is retained. This validates structure, not quality.

Selection sees task inputs, anonymous outputs and deliverables. It chooses an
existing run; it cannot assert verification. `NO_CLEAR_CHOICE` or a malformed
choice retains the first reference. Model-request errors still propagate. Reflection can return `NO_ENTRY` or a
lesson citing completed executions of distinct harnesses. Lessons retain cue,
limitations and the reusable snapshot. No entry is committed inside the editor.

The I editor component configures `max_tool_calls` (default 48, range 1–256)
and stage `instructions`. `max_turns` defaults to 12 (range 1–256) and uses Core turn/continuation semantics; all requests consume the
job's shared model allocation. The I feedback component sets default text page size
(12000 characters, range 1–24000). Experiment grants may narrow mutable instruction
fields; the editor sees those exact grants in `context/edit-grants.json`. Text pages and the complete evidence workspace are
bounded. PNG/JPEG are visual; other binary originals require an explicit renderer.
Requests use injected model configuration and may incur cost only during a job.

Offline checks: `tests.lab.test_improvement_pipeline`.

## Keep judgments independent

`agent.py` owns candidate editing; `generators.py` owns generator registration and
composition. A bounded [workspace session](../workspaces.py) supplies tools
without owning editing or scoring policy. Selection now belongs to
[Assessment](../assessment/README.md); reflection belongs to
[Experience](../experience/README.md). Legacy imports remain explicit compatible
exports, not duplicate implementations. Run constructs a separate read-only
inspector by default, even when editor and inspector use the same model profile.


## Submit and repair a draft

`submit_candidate` validates the current files and evidence-grounded reasons, then
ends the existing Core Agent loop without an extra model request. One submission
slot is reserved beyond the ordinary editor tool allowance. Strict JSON final
responses remain accepted; prose surrounding JSON is rejected. A format repair
uses the current draft, exact grants, successfully supplied evidence IDs and the
validation error. When evidence has not been supplied, the second attempt retains
the original evidence workspace and requests access recovery instead. A missing
reference never becomes evidence merely because its run ID is known. Two failed
attempts retain the baseline. Supply receipts establish returned content, not
whether a model understood it or whether its hypothesis is correct.

I feedback exposes `evidence.access_mode` (`search` or `paged`), `projection` and
`page_characters`. Search returns literal matches with original character offsets
and bounded excerpts over granted files. Large originals remain artifact references;
read pages and search results carry source hashes. No private paths are added.
