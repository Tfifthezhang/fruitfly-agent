# Session Integration

[Up: Interactive](../README.md)

Integrate the public Core loop with multi-turn conversation state and frontend observations. This package has no terminal I/O or Application lifecycle state.

| File / entry | Responsibility |
|---|---|
| [session.py](session.py): InteractiveSession | One active Core execution, conversation state, steering, and cooperative cancellation |
| [core_bridge.py](core_bridge.py): CoreEventBridge | Translate public Core hooks and streams into frontend events |
| [conversation.py](conversation.py): conversation_snapshot | Immutable, safe canonical history projection |
| [materials.py](materials.py): correction_snapshot, TaskMaterials | Completed-task selection and correction provenance through injected readers/writer |

InteractiveSession implements [RuntimeSession](../contracts/runtime.py). Canonical facts remain distinct from model context projections. History reads do not emit events or run tools/models. TaskMaterials selects completed text tasks and records original-output hashes, message identity, session path, and parent manifest. It does not decide when saving is allowed; Application checks that boundary.

The host can inject `execution_environment` as an immutable
`InteractiveExecutionEnvironment` view. Status exposes it independently of the
local `working_directory`; remote paths never pass through local path resolution.
Session does not inspect backends or open connections to construct this view.

With a Session store, `status.message_count` and `RunStarted.message_count` count
committed `message` records, including user, assistant and tool-result messages.
Reads include records appended by the active loop and preserve the original total
after compaction or restoration. They exclude metadata, compaction records,
stream fragments and inputs waiting to become messages. Counting reads Session
records without decoding message bodies or mutating storage. Hosts without a
Session store retain the in-memory message-list fallback.

Durable message storage belongs to [Core Session](../../core/session/README.md). Persisted configuration/artifact recovery belongs to Run. Cancellation uses a cooperative signal and a short interrupt grace; it cannot preempt arbitrary synchronous or noncooperating code. Event observer isolation belongs to [Interaction](../interaction/README.md).

No new environment variables or model training. Submission invokes the injected Core loop/Provider and can have model/tool effects; offline checks use substitutes.

```bash
.venv/bin/python -m unittest tests.interactive.test_session tests.interactive.test_conversation tests.interactive.test_context_status tests.interactive.test_extensions -v
```

Tool observation reads the current request's tool declarations and uses their labels
or isolated `describe_call` callbacks. Tool completion comes from Core's result
callback, including errors and cancellation, rather than success-only rewrite hooks.
The bridge correlates descriptions and monotonic elapsed time by call ID and retains
previous result callbacks. Unknown tools and results without a start event still
produce completion observations, with unavailable elapsed time left unset.
