# Read Working-Memory Resources

[Up: Context Manager](../README.md)

Working memory owns one `SessionHistory` per runtime. Core Session retains
canonical messages; the resource view exposes public text and immutable memory
artifacts through the existing `read` tool. Private thinking and Provider replay
state are excluded. Images require their original image reader.

| File | Responsibility |
|---|---|
| `history.py` | Source binding, immutable hash-checked artifacts and recovery validation |
| `views.py` | Deterministic history index and original-message/artifact views |
| `__init__.py` | Public internal-service exports |

The memory installer mounts `resource://<session-scope>/memory/`. Its `index`
contains message references and short navigation excerpts. Resource references
never fall through to the execution filesystem. Reads check the active scope;
write/edit, traversal, unavailable owners and other sessions are rejected.
Runtime retirement closes the registry. Recovery of the same Session restores
its scope and validates required artifact hashes and source coverage.

These are trusted in-process capabilities, not an OS sandbox. There is no generated
topic archive or semantic history search. `tests.lab.test_context_history` and
`tests.workflows.test_working_memory_improvement` exercise routing and isolation.

`SessionHistory.execution_artifacts()` exports immutable memory text and committed
coverage checkpoints for trial evidence. Runtime resource scopes retire with the
trial; later inspection reads the collected evidence copies.
