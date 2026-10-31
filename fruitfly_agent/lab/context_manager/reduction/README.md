# Reduce Request Context

[Up: Context Manager](../README.md)

The default [working-memory method](methods/working_memory/README.md) maintains
bounded task memory incrementally. `context-history` supplies original evidence.
Core validates and durably commits projections and checkpoints. Canonical Session
messages remain intact. A failed checkpoint write stops requests until recovery.

A projection can replace history only after complete source coverage and a
smaller fitting request. Partial pages retain an exact cursor; failed updates
preserve the previous checkpoint. Signed Provider continuation may forbid a
projection reset. Main and auxiliary requests use shared
[measurement](../measurement/README.md); estimates do not establish memory fidelity.

## Retrieve evidence and recover

[SessionHistory](../history.py) supplies `context_read` and `context_search`.
They expose public message sources and immutable artifacts with bounded offsets.
Tool arguments/results remain available; private thinking, opaque replay and
image bytes are excluded. Inspect original images when needed.

Run stores artifacts beside Session in `SESSION.jsonl.artifacts/reduction`.
Recovery checks required hashes and coverage. Direct in-memory construction has
no cross-process recovery. Uncommitted artifacts never become active state.
`context-history.parameters.max_artifact_bytes` defaults to 16 MiB, within
1024–67108864 bytes, and can be granted to Improvement.

## Optimize policy

The working-memory owner exposes prompts, memory capacity, update frequency,
switch ratio, page limits and auxiliary request limits through ordinary H
parameter targets. Each field has owner descriptions and bounds. A candidate
requires `configuration-materialization`, isolated state and actual execution.
Changed policy identity reprocesses canonical evidence. Coverage, artifact hashes,
permissions and outer budgets remain fixed. Task memory is execution state.

Concrete defaults, prompts and installation live under `methods/working_memory/`.
Shared [inference](inference.py), [cuts](cut.py), [registration](registration.py)
and [Improvement admission](improvement.py) remain outside the method.

Offline checks: `tests.lab.test_working_memory`, `tests.lab.test_reduction_safety`,
`tests.lab.test_long_context`, `tests.lab.test_algorithm_contracts`.
