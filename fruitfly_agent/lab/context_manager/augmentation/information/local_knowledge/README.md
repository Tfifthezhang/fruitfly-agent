# Local Knowledge

[Up: Information Spaces](../README.md)

Retrieve cited passages from local Markdown and text files. This source does not write documents or maintain a vector index.

| Item | Behavior |
|---|---|
| Mechanism / source ID | `knowledge-files` / `workspace-knowledge` |
| Default root | `.fruitfly/knowledge/`, within the workspace |
| Files | Recursive `.md` and `.txt`; skip hidden paths, escaping symlink targets, and files larger than 1 MB |
| Scan / chunks | Up to 256 files; roughly 1500 characters per chunk |
| Retrieval | Lexical matches with source path and line numbers |
| API | `LocalKnowledgeSource`, `create_local_knowledge_space(root)` |

Enable **mechanisms · context-manager → knowledge-files**. No module-specific environment variables.

Change chunking or ranking through [Information source contracts](../README.md#extend-a-source). Keep citations aligned with source text, document index/cache invalidation, and verify updates and empty matches. File-count limits do not bound full directory enumeration; see [Known limitations](../../../../ALGORITHM_AUDIT.md).

```bash
.venv/bin/python -m unittest tests.lab.test_information_sources.InformationSourcesTest.test_knowledge_reindexes_current_files_and_cites_lines -v
```
