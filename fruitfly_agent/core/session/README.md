# Session

[Up: Core](../README.md)

Store and replay the canonical conversation in an append-only JSONL file.

## Stored data

| Record | Contents |
|---|---|
| Messages | Valid user, assistant, and tool messages |
| Context decisions | Committed reduction decisions |
| RuntimeManifest | Complete assembled environment snapshots written and validated by Run |
| Metadata contextProjection | Atomic replacement of the model projection when restoring with changed mechanisms; canonical facts remain intact |
| Run start/end | Model, message/turn/tool counts, stop reason, usage, and bounded error summaries |
| Provider failure | Error category, harness request count, and recovered or terminal disposition |
| Request context / receipt | Final projection estimate/source, configured limits, model, timestamp, and available input receipt; never cumulative occupancy |
| Provider activity | Adapter waiting/retrying/timeout phase, attempt limits, delay, and sanitized category/status |

Interrupted tool calls retain completed results and explicit unknown/not-executed outcomes. These records do not roll back effects or authorize replay. Input receipt values use the adapter's usage convention; cache fields and exact billing remain Provider-specific.

Sessions do not copy every Provider request, token event, or tool event. Use frontend events or `/trace` for live observation; these do not provide exact persisted request replay.

## Use and recover

| Need | Interface |
|---|---|
| Default persistence | Construct `Session` with a JSONL path. |
| Read-only discovery | `Session.inspect(path)` returns a validated snapshot and writer-lock status without creating files or repairing a torn tail. |
| Custom persistence | Implement `SessionLike` and inject it into `AgentLoopConfig`. |
| Resume an application | Follow [Run recovery](../../run/README.md#recovery). |

Records carry schema and kind identifiers. Append validates the consecutive entry ID and earlier parent reference before writing. Replay applies the same validation; incompatible data fails explicitly. An incomplete final JSON line can be discarded while retaining the valid prefix. A Session holds a POSIX writer lock for its lifetime. Failure to append a concise run record is logged and does not change the Agent result.

Run records belong to the most recent environment snapshot preceding their start entry. A changed environment appends a snapshot in the same file after successful startup. A metadata `contextProjection` uses the same validated messages shape as compaction, replaces only model context, and does not increment compaction counts. Inspection validates the prefix without repairing it; the writer performs supported tail repair after acquiring ownership.

| File | Responsibility |
|---|---|
| [protocol.py](protocol.py) | Session protocol and entry types |
| [storage.py](storage.py) | JSONL append, replay, validation, and locks |
| [__init__.py](__init__.py) | Public exports |

Session files may contain prompts, responses, tool output, and error text. Treat them as private runtime data. No module-specific environment variables.

```bash
.venv/bin/python -m unittest tests.core.test_session tests.core.test_loop -v
```

Standard Run may append `meta` entries with `kind="authorization"`, call/tool identity, operation, allow/deny outcome, and reason. These are concise decisions, not replayable approvals. Runtime grant caches and full permission prompt command/code bodies are not stored in these audit entries. The owning Session writer remains privileged relative to model file tools.
