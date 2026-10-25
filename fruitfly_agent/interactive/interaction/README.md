# Interaction Mechanisms

[Up: Interactive](../README.md)

Implement generic interaction behavior shared by frontends and sessions. These mechanisms do not construct or replace runtimes.

| File / entry | Responsibility |
|---|---|
| [commands.py](commands.py): parse_command, CommandRouter | Parse commands, register handlers with descriptions, expose snapshots and route renderer-neutral results |
| [dispatch.py](dispatch.py): EventDispatcher | Run-scoped event sequencing, bounded traces, and observer failure isolation |
| [authorization.py](authorization.py): AuthorizationService | Serialize confirmations, reject stale replies, and retain transient runtime grants |

Command envelopes and EventSink belong to [Contracts](../contracts/README.md). Generic commands return CommandResult and do not perform terminal I/O. Asynchronous terminal feature handlers use the separate [terminal registry](../terminal/commands.py).

`/lab` reads one `InteractiveStatus` snapshot and returns a read-only command panel
plus a complete plain-text fallback. It groups active components and installed
tools using supplied metadata; missing phase metadata and unknown categories
remain visible. It never queries Catalog, configuration, improvement or model
services. Internal component visibility belongs to the host projection; optional
improvement availability comes from Application's status view.

AuthorizationService implements the public RuntimeAuthorization capability. RuntimeHandle owns its lifetime; Application enables frontend replies or binds a decision handler. Grants are local to one runtime and are cleared on close. Request prompt bodies are not retained in event traces. No new environment variables or durable grant storage.

These mechanisms consume public contracts and Core permission types. They cannot import Application, Session, or terminal implementations. Confirmation and cancellation do not undo completed external effects.

```bash
.venv/bin/python -m unittest tests.interactive.test_commands tests.interactive.test_authorization tests.interactive.test_session -v
```

`CommandRouter.register()` accepts optional `summary`, `usage` and `discoverable`
metadata alongside each handler. `descriptions()` returns a read-only snapshot
without invoking handlers. Default `/help` formats that snapshot. Terminal
composition merges base and terminal descriptions with terminal-first precedence;
its default help and completion use that effective view. Explicit custom help
handlers retain their normal priority. `HELP_TEXT` is the generated reference of built-in router entries,
including frontend-dependent placeholders; live help omits unavailable
placeholders. `/quit` parsing and description share the declared `/exit` alias.
