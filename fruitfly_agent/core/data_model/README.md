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

No module-specific environment variables or installation steps.

```bash
.venv/bin/python -m unittest tests.core.test_data_model tests.core.test_session -v
```
