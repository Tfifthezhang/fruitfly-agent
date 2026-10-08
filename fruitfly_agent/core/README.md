# Core

[Up: Runtime Architecture](../README.md)

Core runs the Agent loop and defines the contracts used by the surrounding modules. It does not import Providers, Lab, Interactive, or Eval.

## Run a task

Configure `AgentLoopConfig` with a Provider, tools, execution environment, context pipeline, and optional Session, then call `run_agent_loop`. The [offline example](../../examples/extensions/README.md) shows these capabilities through the Application.

| Area | Entry point | Responsibility |
|---|---|---|
| Loop | [loop.py](loop.py), [config.py](config.py) | `run_agent_loop`, configuration, callbacks, and termination |
| Messages and views | [Data model](data_model/README.md) | Shared runtime data |
| Components and hooks | [Extensions](extensions/README.md) | Provider, Session, and lifecycle contracts |
| Tool dispatch | [Tool runtime](tool_runtime/README.md) | Argument validation and execution |
| Execution backend | [Environment](env/README.md) | Filesystem and shell protocols |
| Model context | [Context](context/README.md) | Stage execution, reduction, and overflow recovery |
| Persistence | [Session](session/README.md) | Append-only conversation storage |
| Model stream | [model_stream.py](model_stream.py) | Stream events and terminal states |
| Mechanisms | [mechanisms.py](mechanisms.py) | Generic mechanism descriptions |

## Runtime rules

| Case | Behavior |
|---|---|
| Tool failure | Lookup, argument, blocking, and ordinary execution failures become error `ToolResultMessage` entries. |
| Callback failure | Use the default defined at the call site; propagate task cancellation. |
| Environment failure | Operations return `Result`; `unwrap()` raises on a failed result. |
| Provider failure | Adapters may retry transient errors within configured limits; Core routes overflow to recovery and other failures to a terminal result. |
| Output token limit | Skip all tool calls in the truncated response and record associated error results. Three consecutive truncated responses end with an `output_limit` error; a complete response resets the counter. |
| Tool budget | `max_tool_calls_per_turn` limits attempts within one outer turn. Execute only the remaining batch allowance; skipped calls each receive an associated error result. Follow-up turns receive a fresh allowance. |
| Turn budget | `max_turns` bounds outer turns, including follow-ups; it is not a Provider request or monetary limit. |
| Tool termination | Finish only when every result in the batch requests termination. |
| Cancellation | Propagate task cancellation after recording an aborted snapshot and notifying passive end observers. Preserve completed tool outcomes and pair unresolved calls with interrupted/unknown results; effects are not rolled back or automatically replayed. |
| Context change | Validate and persist a decision before committing the model projection. |
| Canonical conversation | Preserve valid conversation facts rather than replacing them with summaries. |
| Provider overflow | Use bounded recovery; return a structured overflow failure if recovery cannot proceed. |
| Streaming failure | Return an error terminal state rather than an assistant message; close suspended stream producers. |

Concrete algorithms belong in Lab. Extend Core only when an existing public protocol cannot express a general runtime requirement. Core has no module-specific environment variables.

## Verify

```bash
.venv/bin/python -m unittest discover -s tests/core -t . -v
```

`REQUEST_PREPARED` observes the final request projection after context transformations and budgeting. Estimates use the selected reducer; no estimator means unknown. Core records request statistics and Provider activity without storing complete request bodies. See [Session records](session/README.md) and [Provider waiting policy](../providers/PROVIDER_GUIDE.md#bound-waiting-and-retries).

`AgentLoopConfig.tool_authorizer` is an execution-scoped generic authorization seam. It runs after final tool argument validation and does not use ordinary fail-open Hook callbacks. See [Tool authorization](tool_runtime/README.md#authorize-final-calls). Direct Core callers without an authorizer remain unrestricted; standard Run installs a policy.
