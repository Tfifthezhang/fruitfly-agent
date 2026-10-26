# File Memory

[Up: Information Spaces](../README.md)

Read persistent notes maintained by the user or model with ordinary file tools. This source does not extract or write memories automatically.

| Item | Behavior |
|---|---|
| Mechanism / source ID | `memory-files` / `workspace-memory` |
| Default root | `.fruitfly/memory/`, within the workspace |
| Index | `MEMORY.md`, up to 2000 characters |
| Topic notes | Direct-child Markdown files, up to 16000 characters each |
| Retrieval | Always return the index; match topic notes lexically. |
| Updates | File edits take effect on the next query. |
| API | `FileMemorySource`, `FileMemoryRetriever`, `create_file_memory_space(root)` |

Enable **mechanisms · context-manager → memory-files**. Use `read`, `write`, and `edit` to maintain notes. Keep secrets and temporary task state out of memory.

Extend through [Information source contracts](../README.md#extend-a-source). Preserve stable references and declare file scope, ordering, budgets, and update behavior. Automatic memory extraction belongs in a separately declared improvement mechanism, not hidden inside retrieval. No module-specific environment variables.

```bash
.venv/bin/python -m unittest tests.lab.test_information_sources.InformationSourcesTest.test_file_memory_reflects_normal_file_edits -v
```

[snapshots.py](snapshots.py) exposes `FileMemorySnapshots(root, workspace)` for [Improvement state identity](../../../../improvement/README.md). It captures complete direct-child Markdown files up to 128 KB each, records an empty root explicitly, and rejects symlink roots/files. The snapshot adapter is registered during assembly but reads no files until explicitly frozen. Native trials receive only explicit task inputs; they do not copy this memory directory or run live retrieval. Adopting a text candidate does not adopt trial file mutations.

## Learn environment memory

The separate **Learned environment memory** mechanism (`learned-memory`) appears under **Context → Context augmentation**. [learned.py](learned.py) registers a bounded retained document and its S target. Enter `initial_text` in the visible configuration field; `max_chars=16000` bounds the complete document. Select its component under S in the system config, then grant `parameters.initial_text` in experiment `edit` to permit candidate changes.

Enable the retained memory document and select its S component in [Improvement](../../../../improvement/README.md). Independent verification precedes persistent publication. Accepted text is projected into later sessions, and its exact body enters S identity. Ordinary task-local experience is recorded separately by the workflow.

This mechanism does not silently harvest ordinary conversations or modify `memory-files` notes. File memory remains independently editable retrieval; learned memory is an explicitly versioned document. Native trials use isolated in-memory read/write/edit files; desktop or other environment exploration needs an injected isolated executor and verifier. There is no module-specific environment variable.
