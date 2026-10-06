# Interactive

[Up: Runtime Architecture](../README.md)

Run multi-turn sessions through a frontend-independent Application. Inject a RuntimeFactory; Application manages submission, cancellation, recovery, and resource cleanup.

## Use the Application

| Operation | Behavior |
|---|---|
| `start` / `close` | Start owned runtime resources; close after pending work and cleanup. |
| `submit` | Execute one input. |
| `enqueue` | Process queued inputs in order. |
| `steer` | Add text to the active run. |
| `cancel` | Request cooperative cancellation. |
| `rebuild` / `resume` | Prepare and start a replacement before switching. |
| `activate_runtime` | Validate the expected parent and activate a prepared candidate. |

The [offline example](../../examples/extensions/README.md) demonstrates `start → submit → close`. For terminal operations, see [Terminal](terminal/README.md).

## State and events

| Item | Meaning |
|---|---|
| Lifecycle | starting, idle, running, optimizing, rebuilding, resuming, closing, closed |
| Event envelope | Serializable event type, run ID, and sequence metadata for frontend ordering |
| Run events | Start/finish and activity snapshots |
| Assistant events | Text and thinking deltas |
| Tool events | Start, output, and finish |
| Compaction events | Context reduction activity |
| Event sink failure | Ordinary observer failures do not change the Agent result. |

Frontends consume Application and Interactive events. They do not construct Providers, read algorithm files, or decide candidate quality.

## Injected services

| Service | Responsibility / boundary |
|---|---|
| Configuration | Save next-session choices; active status reads actual runtime/Session identity. |
| Optimization | Preview, explicit cost confirmation, search, progress, and review through generic views. |
| Candidate activation | Prepare an isolated handle; confirm switching to a new empty session. |
| Task packs | Show completed tasks and save corrected train cases; no automatic model call or holdout changes. |
| Evaluation | Start an optional independent process while idle and forward events/logs. |

Failed replacement keeps the active handle. Configuration writes and external side effects do not automatically roll back. No source hot reload or cross-process activation transaction. Optimization progress covers the current batch, not overall search completion.

## Files

| File | Responsibility |
|---|---|
| [application.py](application.py) | Lifecycle and injected service operations |
| [session.py](session.py), [core_bridge.py](core_bridge.py) | Multi-turn Core integration and event conversion |
| [events.py](events.py), [models.py](models.py) | Frontend events and views |
| [dispatch.py](dispatch.py), [commands.py](commands.py) | Observer isolation and command routing |
| [configuration.py](configuration.py), [optimization.py](optimization.py), [evaluation.py](evaluation.py) | Host-injected service contracts |
| [Terminal](terminal/README.md) | Default frontend |

No module-specific environment variables. [Run](../run/README.md) constructs the default factory; [Optimization](../lab/optimization/README.md) and [Eval](../../eval/README.md) own their execution semantics.

```bash
.venv/bin/python -m unittest discover -s tests/interactive -t . -v
.venv/bin/python -m unittest discover -s tests/workflows -t . -v
```
