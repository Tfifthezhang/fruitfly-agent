# Data Model

[Up: Core](../README.md)

Shared message, context, and runtime values. This module performs no I/O and implements no algorithms.

| File | Defines |
|---|---|
| [messages.py](messages.py) | User, assistant, and tool messages; content blocks; usage; loop results |
| [context.py](context.py) | `ContextSnapshot`, `ContextDecision`, and `ContextItem` |
| [runtime.py](runtime.py) | Loop context, Provider request views, and callback results |
| [__init__.py](__init__.py) | Public exports |

| Rule | Meaning |
|---|---|
| Message serialization | Used by [Session](../session/README.md); field changes require compatibility tests. |
| Context decisions | Proposals committed by Core, not by algorithms. |
| Optional cancellation signal | Run-local `asyncio.Event`, default `None`; not persisted or restored. |
| Algorithm state | Owned by its Lab implementation or explicit artifacts. |
| `LoopDiagnostics` | Optional immutable terminal facts on `AgentLoopResult`; counts and termination, not quality or verification |
| `AgentToolResult.is_error` | Defaults false; `.error(...)` sets true and Core preserves it |
| `AssistantMessage.provider_state` | Optional finite JSON continuation; Core stores it, Providers validate and interpret it; omitted from repr and text summaries |
| `AssistantMessage.continue_turn` | Explicit non-final response; Core requests continuation within its bounded policy |
| `Usage.reasoning_tokens` | Optional output-token subset; never added again to total_tokens; missing means unknown |

No module-specific environment variables or installation steps.

```bash
.venv/bin/python -m unittest tests.core.test_data_model tests.core.test_session -v
```
