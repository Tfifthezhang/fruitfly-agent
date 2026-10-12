# Resume Feature

[Up: Terminal Features](../README.md)

Use `TerminalResumeFrontend` as the menu entry and `resume_handler` to bind the command flow. Public entries are exported by this feature package. Consume [interaction contracts](../../../contracts/README.md) through explicit capabilities.

| File | Responsibility |
|---|---|
| [menu.py](menu.py) | Compatible persisted-session picker |
| [command.py](command.py) | Relative-path resolution, discovery, restoration request, and post-success history |

The host discovers sessions and validates persisted contents/manifests. This feature only selects a path and calls the public resume capability. Successful restoration displays canonical history; failure or cancellation retains the current conversation and does not display target history.

Menu selection borrows the existing reader/display. No model calls, tool replay, configuration writes, or session merging. Recovery validation and storage belong to Run.

Input and terminal control come from [I/O](../../io/README.md); display comes from [Rendering](../../rendering/README.md). This feature cannot import other features or Application/Session implementations. No new environment variables.

```bash
.venv/bin/python -m unittest tests.interactive.test_terminal tests.workflows.test_resume_history -v
```
