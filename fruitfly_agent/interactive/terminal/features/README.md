# Terminal Features

[Up: Terminal](../README.md)

Keep each user-facing function's command flow and menus in one package. Features capture explicit host operations and share supplied I/O/rendering interfaces. They do not receive Application or TerminalFrontend internals.

| Package / file | Responsibility |
|---|---|
| [Configuration](configuration/README.md) | Future-session choices, model forms, and rebuild requests |
| [Resume](resume/README.md) | Session selection, restoration requests, and history display |
| [Improvement](improvement/README.md) | Task source selection, iterative improvement, candidate review/activation, and saved cases |
| [assembly.py](assembly.py): bind_commands | Bind available built-in features and cancellation to the terminal registry |

Each feature exports its menu entry and a handler factory. Factories return synchronous/asynchronous handlers accepted by [TerminalCommandRegistry](../commands.py). CommandResult lets the input loop display output and handle exit. Application's public methods remain authoritative for work exclusion and runtime switching.

Add a feature package and register its handler through `command_handlers` or `frontend.commands.register()`. The input loop requires no new branch. Handlers needing a menu borrow the frontend's public menu scope while being dispatched; do not create a second stdin loop. Built-in feature assembly binds concrete callbacks without exposing private state.

Features depend on [Contracts](../../contracts/README.md), [I/O](../io/README.md), [Rendering](../rendering/README.md), and public bindings/registration interfaces. They do not import other feature packages. Shared behavior belongs to an appropriate lower layer. Feature-specific errors and effects belong to the injected service.

No new environment variables or model training. Existing confirmation steps govern model search, configuration saving, and external evaluation. Offline checks use fake Providers, controllers, and local state.

```bash
.venv/bin/python -m unittest tests.interactive.test_extensions tests.interactive.test_terminal tests.workflows.test_resume_history tests.workflows.test_optional_eval -v
```
