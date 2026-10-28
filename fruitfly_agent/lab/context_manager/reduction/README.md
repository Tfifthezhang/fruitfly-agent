# Reduction

[Up: Context Manager](../README.md)

Enable `context-history` for shared evidence tools, then choose one reduction method in Catalog's `reduction` group. Canonical Session
messages remain intact. Core validates and durably commits proposed projections
and task-local checkpoints; a failed write preserves the previous projection and
checkpoint and stops further requests until the Session is reopened and validated.
This is independent of Improvement's orchestration kernel.

| Method | Configuration ID | Behavior |
|---|---|---|
| [Summarizing](methods/summarizing/README.md) | `compaction` | Summarize bounded evidence pages on demand; retain a complete recent tail. |
| [Working memory](methods/working_memory/README.md) | `working-memory-reduction` | Update bounded task memory incrementally; reset only after complete source coverage. |

[Measurement](../measurement/README.md) is selected separately and measures the
final main request, including tools, framing, images and output reserve. Reduction
uses its observation when present. A Provider overflow still has bounded reactive
recovery. Heuristic estimates cannot establish exact occupancy or memory fidelity.
Fixed instructions/tools or protected signed continuation can prevent any legal
reduction; the loop then returns a structured failure instead of discarding them.

## Retrieve original evidence

[SessionHistory](../history.py) supplies `context_search` and `context_read` to both
methods. It searches public canonical messages by literal text and returns source
IDs and character offsets. Read source IDs or `sha256:` artifacts with bounded
pagination. Tools are session-scoped and require no IPython or arbitrary path
access. Tool arguments and results are included; private thinking, opaque replay
and image bytes are excluded. Image descriptions explicitly require original
image inspection.

Run injects the artifact directory beside the Session:
`SESSION.jsonl.artifacts/reduction`. Hash-verified immutable text objects are
written before a checkpoint refers to them. Recovery rejects missing or modified
required artifacts. In-memory direct construction has no cross-process recovery.
Uncommitted objects can remain after failed commits; they are never active state.
`context-history.max_artifact_bytes` defaults to 16 MB (validated within 1 KB–64 MB)
per artifact and is an editable H parameter. Larger reductions fail
without changing context. Store external source data through ordinary artifacts.

## Extend a method

Concrete implementations, defaults, prompts and method declarations live under
`methods/<name>/`. Shared [inference](inference.py), [cuts](cut.py),
[registration](registration.py) and [Improvement admission](improvement.py) remain
outside. Methods do not depend on sibling implementations.

Every method exposes meaningful H policy parameters through the existing Catalog
parameter target. Experiment grants authorize fields and bounds; candidates use
shared configuration materialization and assembly. The backend must declare
`configuration-materialization`; unsupported native file-only trials reject such
changes. Policy identity includes exact prompt text. Coverage hashes, replay
rules, artifact identities, host permissions and outer call allowances are fixed.
Task memory is Session execution state, not an automatic S learning update.

```bash
.venv/bin/python -m unittest tests.lab.test_summarizing_compaction tests.lab.test_reduction_safety tests.lab.test_working_memory tests.lab.test_context_measurement -v
```
