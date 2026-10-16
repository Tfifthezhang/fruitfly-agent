# Application Lifecycle

[Up: Interactive](../README.md)

Own application state, execution permission, queued inputs, runtime switching, and resource retirement. Frontends and injected services cannot create a separate application lifecycle authority.

| File / entry | Responsibility |
|---|---|
| [application.py](application.py): AgentApplication | Submit/queue/steer/cancel work; start, restore, rebuild, activate, and close runtimes |
| [runtime.py](runtime.py): RuntimeHandle | Concrete resource owner; start once per component identity and close in reverse order |
| [jobs.py](jobs.py): ImprovementJob | Own improvement tasks, progress, cancellation, and completion callbacks |

Construct AgentApplication with a [RuntimeFactory](../contracts/runtime.py). Application consumes the public handle protocol; the RuntimeHandle exported by this package is its default concrete implementation. Inject search, candidate, activation, task material, and authorization capabilities independently. Run performs concrete assembly.

The Application submission lock and state checks authorize work. ImprovementJob uses injected execution/completion callbacks and cannot activate a runtime. Correction operations delegate to [Session materials](../session/README.md) after Application permission checks. Failed preparation/startup retains the incumbent; failed retirement is recorded after a successful switch. Shutdown waits are bounded and retain resources still in use.

Configuration and external effects are owned by injected services and do not automatically roll back. No source reload, model training, or new environment variables. Lifecycle limits and authorization behavior are described by the parent guide.

```bash
.venv/bin/python -m unittest tests.interactive.test_application tests.interactive.test_run_control tests.interactive.test_extensions -v
```

Checks use fake Providers and owned local resources.
