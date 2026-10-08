# Extension Contracts

[Up: Core](../README.md)

Define components and hooks that Core calls directly. Concrete strategies and Provider SDKs live outside this module.

| File / contract | Behavior |
|---|---|
| [protocols.py](protocols.py) | Structural `Provider`, `SessionLike`, and related component contracts |
| [hooks.py](hooks.py) | Active handlers can modify events; passive observers receive private snapshots. |
| [callbacks.py](callbacks.py) | Invoke synchronous or asynchronous run callbacks with call-site defaults; preserve cancellation. |
| [../config.py](../config.py) | Run-local callbacks and injected components |

`REQUEST_PREPARED` is observation-only: register with `HookRegistry.on`; active registration is rejected. Its frozen `RequestPreparedEvent` carries the final projection estimate, source, model, limits, and timestamp. `AFTER_RESPONSE` carries the receipt timestamp. Task cancellation emits an aborted `BEFORE_RUN_END` snapshot to passive observers and still propagates `CancelledError`; active end handlers cannot turn this interruption into success.

Core invokes active handlers before passive observers and isolates ordinary handler failures. Use existing hooks or callbacks before adding a new Core protocol. Algorithms belong in [Lab](../../lab/README.md); assembly belongs in [Run](../../run/README.md). No module-specific environment variables.

```bash
.venv/bin/python -m unittest tests.core.test_protocols tests.core.test_hooks -v
```
