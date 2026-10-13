# Runtime Preparation

[Up: Run](../README.md)

Assemble resources and prepare new or recovered runtime handles. Application owns startup, active-handle switching, cancellation, and retirement. This module does not add another lifecycle state machine.

| File / entry | Responsibility |
|---|---|
| [assembly.py](assembly.py): `build_runtime` | Construct Providers, assemble Lab components, and apply host permissions |
| [manifest.py](manifest.py): `RuntimeManifest` | Actual assembled runtime identity and serialization |
| [preparation.py](preparation.py): `RuntimePreparer.open` | Open Session, verify recovery, bind injected services, return an unactivated handle |
| [activation.py](activation.py): `bind_activation` | Compose pre-commit and post-commit hooks around prepared handles |
| [recovery.py](recovery.py) | Session discovery, recorded bindings, manifest checks, and session paths |
| [permissions.py](permissions.py) | Host permission policy and minimal process environment |

Preparation receives configuration selections, separate optimization/candidate/task material services, and explicit construction/presentation capabilities. It does not inspect a Factory, candidate store, optimizer implementation, or configuration draft. `PreparedRuntime` reports actual bindings to the composition root only when activation occurs. Successful activation commits the environment snapshot; changed mechanisms also commit a rebuilt model projection.

Preparation can create Session files and Provider clients; it does not execute Agent tasks. Failed preparation closes owned resources. Application cleans up failed startup. Activation hooks do not provide cross-process transactions or rollback arbitrary external effects.

Manifest schema remains 5. Recovery validates each recorded manifest against its own contents and allows changed environments; it does not restore arbitrary Python state or replay unknown paid work. See [Run recovery](../README.md#recovery) and [Session](../../core/session/README.md). No module-specific environment variables.

```bash
.venv/bin/python -m unittest tests.run.test_assembly tests.run.test_resources tests.run.test_cli tests.workflows.test_resume_history tests.workflows.test_decoupling -v
```

Checks use fake Providers and temporary state.
