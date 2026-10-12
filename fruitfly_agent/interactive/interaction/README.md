# Interaction Mechanisms

[Up: Interactive](../README.md)

Implement generic interaction behavior shared by frontends and sessions. These mechanisms do not construct or replace runtimes.

| File / entry | Responsibility |
|---|---|
| [commands.py](commands.py): parse_command, CommandRouter | Parse local commands and route renderer-neutral built-in/custom handlers |
| [dispatch.py](dispatch.py): EventDispatcher | Run-scoped event sequencing, bounded traces, and observer failure isolation |
| [authorization.py](authorization.py): AuthorizationService | Serialize confirmations, reject stale replies, and retain transient runtime grants |

Command envelopes and EventSink belong to [Contracts](../contracts/README.md). Generic commands return CommandResult and do not perform terminal I/O. Asynchronous terminal feature handlers use the separate [terminal registry](../terminal/commands.py).

AuthorizationService implements the public RuntimeAuthorization capability. RuntimeHandle owns its lifetime; Application enables frontend replies or binds a decision handler. Grants are local to one runtime and are cleared on close. Request prompt bodies are not retained in event traces. No new environment variables or durable grant storage.

These mechanisms consume public contracts and Core permission types. They cannot import Application, Session, or terminal implementations. Confirmation and cancellation do not undo completed external effects.

```bash
.venv/bin/python -m unittest tests.interactive.test_commands tests.interactive.test_authorization tests.interactive.test_session -v
```
