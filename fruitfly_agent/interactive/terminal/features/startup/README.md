# Start an interactive session

[Up: Terminal Features](../README.md)

`TerminalStartupFrontend` in [menu.py](menu.py) displays an offline
[`StartupSnapshot`](../../../contracts/startup.py) and returns `start`,
`configure` or `exit`. Incomplete configuration focuses Configure and cannot
start. Run supplies non-secret model, execution and session descriptions.
Configuration completeness does not establish network availability.

Run opens the [shared configuration editor](../configuration/README.md) on a
Configure choice. Saving returns to this panel without starting resources.
Only Start prepares and starts an Application. A recoverable startup failure
returns here with its reason; configuration remains available. There is no
automatic local fallback. Cleanup failures end the process instead of retrying.

`wait_for_start(task, environment=...)` displays progress and waits for a
host-created task. Ctrl+C cancels it and waits for owner cleanup. Raw terminal
input uses bounded polls; numbered input uses SIGINT without a concurrent line
reader. The previous signal handler is restored after every attempt.
Application retains lifecycle authority; the panel never constructs a runtime.
`lend_input()` suspends startup key polling while the host's external-service
confirmation owns input, so approval and cancellation cannot consume each other's keys.

The panel uses the existing menu renderer, numbered fallback and transient
screen. It owns no configuration, persistent state or environment variables.
Malformed configuration and extension-loading errors occur before the panel;
this feature does not repair raw YAML. See [Run startup](../../../../run/README.md#start-from-the-cli).

```bash
.venv/bin/python -m unittest tests.interactive.test_terminal_startup tests.workflows.test_startup_recovery tests.workflows.test_startup_terminal -v
```

These checks use fake Providers and SSH, plus local terminal processes. They
do not establish compatibility with a real remote server.
