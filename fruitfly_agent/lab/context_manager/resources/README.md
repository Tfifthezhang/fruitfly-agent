# Read Session History Resources

[Up: Context Manager](../README.md)

Each selected reduction method owns one `SessionHistory` per runtime. Core Session retains
canonical messages; the resource view exposes public text and immutable context
artifacts through the existing `read` tool. Private thinking and Provider replay
state are excluded. Images require their original image reader.

| File | Responsibility |
|---|---|
| `history.py` | Source binding, immutable hash-checked artifacts and recovery validation |
| `mount.py` | Mount shared history under an owner namespace and artifact directory |
| `views.py` | Deterministic history index and original-message/artifact views |
| `__init__.py` | Public internal-service exports |

The shared `mount_history` entry mounts `resource://<session-scope>/memory/` for
working memory or `resource://<session-scope>/compaction/` for layered compaction. Its `index`
contains message references and short navigation excerpts. Resource references
never fall through to the execution filesystem. Reads check the active scope;
write/edit, traversal, unavailable owners and other sessions are rejected.
Runtime retirement closes the registry. Recovery of the same Session restores
its scope and validates required artifact hashes and source coverage.

These are trusted in-process capabilities, not an OS sandbox. There is no generated
topic archive or semantic history search. `tests.lab.test_context_history` and
`tests.workflows.test_layered_compaction_improvement` exercise routing and isolation.

`SessionHistory.execution_artifacts()` exports immutable context text and committed
coverage checkpoints for trial evidence. Runtime resource scopes retire with the
trial; later inspection reads the collected evidence copies.
