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
