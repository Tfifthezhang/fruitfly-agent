# Interactive

[Up: Runtime Architecture](../README.md)

Run multi-turn sessions through a frontend-independent Application. Inject a RuntimeFactory; Application manages submission, cancellation, recovery, and resource cleanup.

## Use the Application

| Operation | Behavior |
|---|---|
| `start` / `close` | Start owned runtime resources; cancel and drain active work before cleanup. `shutdown_timeout=10` bounds quiescence; an uncooperative runtime is retained with an explicit error. |
| `submit` | Execute one input. |
| `enqueue` | Process queued inputs in order. |
| `steer` | Add text or image content to the active run. |
| `load_attachment` | Ask the host to read and validate an explicitly selected local image. |
| `cancel` | Set the cooperative signal and interrupt owned work after a 50 ms grace; clear pending Application input. User cancellation returns `aborted`; external task cancellation still propagates after end delivery. |
| `apply_configuration` | While idle, prepare the host's draft for the current Session; start a replacement before committing and switching. |
| `rebuild` / `resume` | Open a fresh session or recover another Session; prepare and start a replacement before switching. |
| `conversation` | Read an immutable snapshot of original user, assistant, and tool messages, independent of model context reduction. |
| `activate_runtime` | Validate the expected parent and activate a prepared candidate. |

The [offline example](../../examples/extensions/README.md) demonstrates `start → submit → close`. For terminal operations, see [Terminal](terminal/README.md).

`submit`, `enqueue` and `steer` accept strings or lists of Core `TextBlock` and
`ImageBlock` values (`UserContent`). Submission copies the list and validates
declared image support before queueing/persistence. Image-only inputs are valid.
`validate_input` performs this preflight without model requests. Host resource
registration happens when input becomes a message; cancelled queued input is
not committed. Events and history use media-type markers, never Base64 data.

## State and events

| Item | Meaning |
|---|---|
| Lifecycle | starting, idle, running, improving, rebuilding, resuming, closing, closed |
| Event envelope | Serializable event type, run ID, and sequence metadata for frontend ordering |
| Run events | Start/finish and activity snapshots |
| Assistant events | Text and thinking deltas |
| Tool events | Start, output, and finish |
| Compaction events | Context reduction activity |
| Event sink failure | Ordinary observer failures do not change the Agent result. |

Frontends consume Application and Interactive events. They do not construct Providers, read algorithm files, or decide candidate quality.

`/lab` consumes the status snapshot's visible active component descriptions,
installed tool names and injected improvement availability. Run supplies component
metadata independently of the experimental-mechanism ID collection. The command
returns a read-only structured panel and plain-text fallback; terminal rendering
owns section colors, alignment and width adaptation. Inspection makes no service
queries, model calls or configuration changes. See [active harness inspection](terminal/README.md#inspect-the-active-harness).

Welcome, `/lab` and `/status` distinguish the local workspace from the optional
execution-environment view. Remote execution includes its server/port and working
directory. These are active runtime facts, independent of saved drafts and ongoing
connection health. Failed replacement retains the previous facts. Built-in chat
uses native terminal scrollback, including after menus and exit.

`conversation()` projects canonical messages into `ConversationMessage` and `ConversationBlock` views. Text remains complete; image blocks contain only their media type, thinking blocks contain an omission marker, and tool calls contain only their name. Internal context summaries are excluded. Reading history emits no events and changes neither persisted messages nor model context.

## Inject independent capabilities

| RuntimeHandle field / contract | Responsibility |
|---|---|
| `session`: [RuntimeSession](contracts/runtime.py) | Public conversation, observation, cancellation, and submission operations; InteractiveSession is the default implementation. |
| `improvement`: [ImprovementService](contracts/improvement.py) | Preview, confirmed search, and cancellation. Optional ImprovementActivityService supplies progress observations; ImprovementHistoryService exposes submitted experiment results. |
| `candidates`: [CandidateService](contracts/candidates.py) | List, inspect, acknowledge, and review candidates. Does not require a search service. |
| `candidate_activation`: [CandidateActivationService](contracts/candidates.py) | Prepare an isolated handle. Application owns startup and switching. |
| `task_packs`: [TaskPackService](contracts/task_packs.py) | Read task materials and save corrections. Does not require improvement or candidate services. |
| `authorization`: [AuthorizationService](interaction/authorization.py) | Serialize permission requests and retain grants for this runtime only. |

Configuration and model setup come from the injected RuntimeFactory/controller. Confirmed generic improvement uses Application jobs. Run binds concrete implementations; Interactive imports neither Run, Lab, Providers, nor Eval.

Each runtime capability is optional and independently injected. Use explicit `candidates=` and `task_packs=` fields even when one object implements several contracts. Missing query capabilities return empty candidate lists or unavailable material status; operations requiring a missing service raise an explicit error. Protocol and view definitions belong to `contracts/`. The package-level `fruitfly_agent.interactive` API exports the usual Application, concrete RuntimeHandle, Session, views, and terminal entries. Internal consumers import their owning modules directly.

Application retains the only application lifecycle state and submission lock. [ImprovementJob](application/jobs.py) owns a task, progress, cancellation, and observer isolation through execution/completion callbacks; it cannot grant execution permission or activate a runtime. [TaskMaterials](session/materials.py) reads public canonical items and creates correction provenance. Application checks that saving is allowed before delegating. Task examples support Harness improvement and evaluation; saving does not train a model or alter conversation facts.

To add a frontend, consume Application's public operations and the capability protocols. To add a terminal command, use the [command extension interface](terminal/README.md#register-a-command). Concrete mechanisms and scoring stay with Lab and the host.

Replacement paths share preparation and retirement: start resources, bind events, invoke activation, then switch the active handle. Failed replacement keeps the active handle; failure to retire the previous handle is exposed through `last_error` after a successful switch. Configuration writes and external side effects do not automatically roll back. No source hot reload or cross-process activation transaction. Improvement progress covers the current batch, not overall search completion.

Resume continues canonical history in the original file with the selected current configuration. Discovery exposes availability/reasons rather than filtering by the active manifest digest. Run records changed environments after successful startup; history display never triggers model/tool replay. `/improvement` selects current instructions, explicit input files or saved task packages for a bounded component workflow. The light panel selects explicit material and inputs for a simple base-prompt comparison; advanced settings and H/S/I experiments use the independent experiment CLI with file configuration. Results and history include empty/failed/cancelled experiments, and candidates remain subject to human adoption. Container benchmark evaluation belongs to the optional external Eval CLI.

## Modules

| Package | Owns | May consume |
|---|---|---|
| [Contracts](contracts/README.md) | Runtime/service protocols, command envelopes, events, and frontend views | Contracts and public Core types |
| [Application](application/README.md) | Lifecycle, work exclusion, improvement tasks, and concrete runtime resource ownership | Contracts, Session helpers, and interaction mechanisms |
| [Session](session/README.md) | Core integration, canonical conversation projections, and correction material extraction | Contracts, interaction mechanisms, and Core |
| [Interaction](interaction/README.md) | Generic command routing, event dispatch, and authorization | Contracts and public Core permission types |
| [Terminal](terminal/README.md) | Frontend composition, input, rendering, and registered features | Contracts, generic interaction commands, and terminal infrastructure |

The root contains only this guide and public exports. Contracts never import their implementations, even under TYPE_CHECKING. Application consumes a RuntimeHandle protocol; [application/runtime.py](application/runtime.py) supplies the default concrete owner. RuntimeSession and RuntimeFactory describe the host boundary in [contracts/runtime.py](contracts/runtime.py).

Terminal features share input and rendering facilities through public interfaces. They cannot import other features or Application/Session implementations. Adding a feature does not change the input loop. Directory dependency checks enforce these responsibilities.

No module-specific environment variables. [Run](../run/README.md) constructs the default factory; [Improvement](../lab/improvement/README.md) and [Eval](../../fruitfly_eval/README.md) own their execution semantics.

```bash
.venv/bin/python -m unittest discover -s tests/interactive -t . -v
.venv/bin/python -m unittest discover -s tests/workflows -t . -v
```

Model setup fields use `kind="constant"` for service-selected values and `kind="bool"` for capability checkboxes. A singleton `choices` tuple fixes a required value. Other fields use line input. Frontends return field names and string boolean values through the existing staging contract.

`InteractiveStatus` keeps separate last prepared-input estimates, last request receipts, and last-run reported cumulative usage. Snapshots include their source/model/time and can be restored from concise Session records. Reading status does not run context mechanisms, model calls, or tools. Missing estimates/receipts are unknown. These snapshots describe previous requests, not a live recomputation of the next request.

`/status` reports `messages` as the number of committed canonical Session messages, including user inputs, assistant responses and individual tool results. It is not a conversation-turn count or the length of the model projection. The count includes messages committed during an active run, survives context reduction and restores from original message records. Metadata, compaction records, streamed text fragments and queued inputs that have not become messages do not increase it. Reading status inspects the current Session records without preparing a request, invoking a model or changing storage. Embedded sessions without a Session store fall back to the retained in-memory message count.

After the model/workspace/session state and pending candidates, `/status` displays context usage as a 20-cell ASCII bar and percentage of the configured window, followed by the session's compaction count. Usage prefers the prepared-input estimate, then falls back to a same-model Provider receipt; the line labels the source and last-request scope. The bar fills to at most 100%, while the percentage preserves values above capacity. Missing capacity or matching measurements yields `unknown` without a bar. `compaction_count` counts committed reductions, excludes cancelled or invalid proposals, accumulates across turns, and restores from persisted compaction entries.

Async cancellation cannot preempt synchronous file I/O, abandoned thread work, or arbitrary noncooperating code. Cleanup does not undo completed external effects. If quiescence exceeds its deadline, closing remains incomplete rather than closing resources still in use.

## Confirm sensitive operations

[authorization.py](interaction/authorization.py) provides `AuthorizationService`, owned by `RuntimeHandle.authorization`. Requests are serialized and use `AuthorizationRequested` / `AuthorizationResolved` events. A frontend replies with `respond(request_id, "once" | "session" | "deny")`; stale replies are rejected. Prompt bodies are not retained in the interactive trace.

Application hosts enable interactive replies with `enable_authorization()` or
inject an asynchronous handler with `set_authorization_handler(handler)`. Without
either, requests are denied. Confirmation expires after 300 seconds by default.
Cancellation interrupts waits. `clear_authorizations()` revokes remembered grants
and denies pending requests without undoing completed effects or preempting
already authorized work. Hosts selecting unrestricted execution do not invoke
this confirmation service.

Single approval belongs to one call. Session file approvals cover the displayed directories and operation; a read grant does not authorize writes. Local-execution session approval explicitly grants current-user code execution. Grants exist only in the runtime service, are absent from Session records, and are cleared on close; replacement/restoration constructs a fresh service. Embedded hosts can observe configured roots and grant/pending state through `Application.status` without authorizing anything; the terminal `/status` omits these details.
