# Interactive

[Up: Runtime Architecture](../README.md)

Run multi-turn sessions through a frontend-independent Application. Inject a RuntimeFactory; Application manages submission, cancellation, recovery, and resource cleanup.

## Use the Application

| Operation | Behavior |
|---|---|
| `start` / `close` | Start owned runtime resources; cancel and drain active work before cleanup. `shutdown_timeout=10` bounds quiescence; an uncooperative runtime is retained with an explicit error. |
| `submit` | Execute one input. |
| `enqueue` | Process queued inputs in order. |
| `steer` | Add text to the active run. |
| `cancel` | Set the cooperative signal and interrupt owned work after a 50 ms grace; clear pending Application input. User cancellation returns `aborted`; external task cancellation still propagates after end delivery. |
| `rebuild` / `resume` | Prepare and start a replacement before switching. |
| `conversation` | Read an immutable snapshot of original user, assistant, and tool messages, independent of model context reduction. |
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

`conversation()` projects canonical messages into `ConversationMessage` and `ConversationBlock` views. Text remains complete; image blocks contain only their media type, thinking blocks contain an omission marker, and tool calls contain only their name. Internal context summaries are excluded. Reading history emits no events and changes neither persisted messages nor model context.

## Injected services

| Service | Responsibility / boundary |
|---|---|
| Configuration | Save next-session choices; active status reads actual runtime/Session identity. |
| Model setup | Optional form descriptions, offline staging, and credential set/missing status; the host owns specifications and persistence. |
| Optimization | Preview, explicit cost confirmation, search, progress, and review through generic views. |
| Candidate activation | Prepare an isolated handle; confirm switching to a new empty session. |
| Task packs | Show completed tasks and save corrected train cases; no automatic model call or holdout changes. |
| Evaluation | Start an optional independent process while idle and forward events/logs. |

Replacement paths share preparation and retirement: start resources, bind events, invoke activation, then switch the active handle. Failed replacement keeps the active handle; failure to retire the previous handle is exposed through `last_error` after a successful switch. Configuration writes and external side effects do not automatically roll back. No source hot reload or cross-process activation transaction. Optimization progress covers the current batch, not overall search completion.

## Files

| File | Responsibility |
|---|---|
| [application.py](application.py) | Application state, queued work, and injected service operations |
| [runtime.py](runtime.py) | RuntimeHandle resource lifecycle and RuntimeFactory contract |
| [session.py](session.py), [core_bridge.py](core_bridge.py) | Multi-turn Core integration and event conversion |
| [events.py](events.py), [models.py](models.py) | Frontend events and views |
| [conversation.py](conversation.py) | Immutable canonical history projection for frontends |
| [dispatch.py](dispatch.py), [commands.py](commands.py) | Observer isolation and command routing |
| [configuration.py](configuration.py), [optimization.py](optimization.py), [evaluation.py](evaluation.py) | Host-injected service contracts |
| [model_setup.py](model_setup.py) | Optional model form and credential service protocol; views contain no key values |
| [Terminal](terminal/README.md) | Default frontend |

No module-specific environment variables. [Run](../run/README.md) constructs the default factory; [Optimization](../lab/optimization/README.md) and [Eval](../../eval/README.md) own their execution semantics.

```bash
.venv/bin/python -m unittest discover -s tests/interactive -t . -v
.venv/bin/python -m unittest discover -s tests/workflows -t . -v
```

Model setup fields use `kind="constant"` for service-selected values and `kind="bool"` for capability checkboxes. A singleton `choices` tuple fixes a required value. Other fields use line input. Frontends return field names and string boolean values through the existing staging contract.

`InteractiveStatus` keeps separate last prepared-input estimates, last request receipts, and last-run reported cumulative usage. Snapshots include their source/model/time and can be restored from concise Session records. Reading status does not run context mechanisms, model calls, or tools. Missing estimates/receipts are unknown. These snapshots describe previous requests, not a live recomputation of the next request.

After the model/workspace/session state and pending candidates, `/status` displays only context usage as a percentage of the configured window and the session's compaction count. Usage prefers the prepared-input estimate, then falls back to a same-model Provider receipt; the line labels the source and last-request scope. Missing capacity or matching measurements yields `unknown`. `compaction_count` counts committed reductions, excludes cancelled or invalid proposals, accumulates across turns, and restores from persisted compaction entries.

Async cancellation cannot preempt synchronous file I/O, abandoned thread work, or arbitrary noncooperating code. Cleanup does not undo completed external effects. If quiescence exceeds its deadline, closing remains incomplete rather than closing resources still in use.

## Confirm sensitive operations

[authorization.py](authorization.py) provides `AuthorizationService`, owned by `RuntimeHandle.authorization`. Requests are serialized and use `AuthorizationRequested` / `AuthorizationResolved` events. A frontend replies with `respond(request_id, "once" | "session" | "deny")`; stale replies are rejected. Prompt bodies are not retained in the interactive trace.

Application hosts can enable interactive replies with `enable_authorization()` or inject an asynchronous decision handler with `set_authorization_handler(handler)`. Without either, requests are denied. Confirmation expires after 300 seconds by default. Cancellation interrupts pending waits. `clear_authorizations()` revokes remembered grants and denies a pending request. It does not undo completed effects or preempt an already authorized operation.

Single approval belongs to one call. Session file approvals cover the displayed directories and operation; a read grant does not authorize writes. Local-execution session approval explicitly grants current-user code execution. Grants exist only in the runtime service, are absent from Session records, and are cleared on close; replacement/restoration constructs a fresh service. Embedded hosts can observe configured roots and grant/pending state through `Application.status` without authorizing anything; the terminal `/status` omits these details.
