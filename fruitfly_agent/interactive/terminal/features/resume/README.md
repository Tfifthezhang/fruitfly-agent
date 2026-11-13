# Resume Feature

[Up: Terminal Features](../README.md)

Use `TerminalResumeFrontend` as the menu entry and `resume_handler` to bind the command flow. Public entries are exported by this feature package. Consume [interaction contracts](../../../contracts/README.md) through explicit capabilities.

| File | Responsibility |
|---|---|
| [menu.py](menu.py) | Persisted-session picker with availability and reasons |
| [command.py](command.py) | Relative-path resolution, discovery, restoration request, and post-success history |

The host inspects sessions without repairing them, reports availability, and validates persisted contents/manifests. Continuation uses current configuration; historical environment differences do not hide sessions. This feature only selects a path and calls the public resume capability. Successful restoration displays canonical history; failure or cancellation retains the current conversation and does not display target history.

Menu selection borrows the existing reader/display. No model calls, tool replay, configuration writes, or session merging. Recovery validation and storage belong to Run.

Input and terminal control come from [I/O](../../io/README.md); display comes from [Rendering](../../rendering/README.md). This feature cannot import other features or Application/Session implementations. No new environment variables.

```bash
.venv/bin/python -m unittest tests.interactive.test_terminal tests.workflows.test_resume_history -v
```

The picker uses a bounded, deterministic preview of the first user request, the
latest recorded message time, model, user-turn and total message counts, and
availability. It makes no title-generation requests. Profile/prompt hashes remain
in the read model rather than the normal row. Older histories without message
timestamps use file modification time. Artifact loading alone does not imply a
research candidate.

Session discovery runs in a worker thread. Hosts can publish progressive metadata
snapshots; the picker renders them through its existing input owner. ANSI menus
allow selection/cancellation before discovery finishes. Numbered fallback menus
wait for the completed list. Background scanning never renders or reads input. Run may use disposable
metadata caches; selecting a row still performs complete recovery validation.

Restoration renders the newest 40 canonical messages. `/history older` appends
preceding pages in chronological order; `/history` refreshes the current snapshot
and newest page. Paging changes presentation only, preserves the active model
context, and never replays tools or requests. A resumed session resets the page.
