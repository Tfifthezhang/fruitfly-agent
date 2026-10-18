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

[snapshots.py](snapshots.py) exposes `FileMemorySnapshots(root, workspace)` for [original-task experiments](../../../../improvement/experiments/README.md). It captures complete direct-child Markdown files up to 128 KB each, records an empty root explicitly, and rejects symlink roots/files. The snapshot adapter is registered during assembly but reads no files until explicitly frozen. Each trial gets an independent writable copy; adopted text candidates do not adopt trial memory mutations.

## Learn environment memory

The separate **Learned environment memory** mechanism (`learned-memory`) appears under **Context → Context augmentation**. [learned.py](learned.py) registers a bounded retained document and its S target. Enter `initial_text` in the visible configuration field; `max_chars=16000` bounds the complete document. Enable the mechanism and start a session to expose **Environment memory → Exploratory memory learning** in `/improvement`.

[Exploratory memory learning](../../../../improvement/methods/memory_exploration/README.md) explicitly selects authorized practice, consumes task-verifier evidence and proposes consolidated knowledge. It requires disjoint training, selection and holdout, then stops for human adoption. Accepted memory is an immutable artifact projected in later sessions; deployment freezes memory and makes no curriculum or consolidation calls. S identity records the exact body independently of H/I. The initial text can be empty of learned facts, but must remain a nonempty document.

This mechanism does not silently harvest ordinary conversations or modify `memory-files` notes. File memory remains independently editable retrieval; learned memory is an explicitly versioned document. Native practice is tool-free; desktop or other environment exploration needs an injected isolated executor and verifier. There is no module-specific environment variable.
