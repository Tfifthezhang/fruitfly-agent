# Session

[Up: Core](../README.md)

Store and replay the canonical conversation in an append-only JSONL file.

## Stored data

| Record | Contents |
|---|---|
| Messages | Valid user, assistant, and tool messages |
| Context decisions | Committed reduction decisions |
| RuntimeManifest | Runtime identity written and checked by Run |
| Run start/end | Model, message/turn/tool counts, stop reason, usage, and bounded error summaries |
| Provider failure | Error category, attempt, and recovered or terminal disposition |

Sessions do not copy every Provider request, token event, or tool event. Use frontend events or `/trace` for live observation; these do not provide exact persisted request replay.

## Use and recover

| Need | Interface |
|---|---|
| Default persistence | Construct `Session` with a JSONL path. |
| Custom persistence | Implement `SessionLike` and inject it into `AgentLoopConfig`. |
| Resume an application | Follow [Run recovery](../../run/README.md#recovery). |

Records carry schema and kind identifiers. Replay validates entry IDs and parent references; incompatible data fails explicitly. An incomplete final JSON line can be discarded while retaining the valid prefix. A Session holds a POSIX writer lock for its lifetime. Failure to append a concise run record is logged and does not change the Agent result.

| File | Responsibility |
|---|---|
| [protocol.py](protocol.py) | Session protocol and entry types |
| [storage.py](storage.py) | JSONL append, replay, validation, and locks |
| [__init__.py](__init__.py) | Public exports |

Session files may contain prompts, responses, tool output, and error text. Treat them as private runtime data. No module-specific environment variables.

```bash
.venv/bin/python -m unittest tests.core.test_session tests.core.test_loop -v
```
