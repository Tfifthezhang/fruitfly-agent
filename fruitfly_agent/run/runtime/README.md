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

Preparation receives configuration selections, separate improvement/candidate/task material services, and explicit construction/presentation capabilities. It does not inspect a Factory, candidate store, improver implementation, or configuration draft. `PreparedRuntime` reports actual bindings to the composition root only when activation occurs. Successful activation commits the environment snapshot; changed mechanisms also commit a rebuilt model projection.

Preparation registers lightweight improvement targets and an offline method selector. Without a configured improver, the direct-call default is lazy; `/improvement` binds each selected method using borrowed model/task services. Per-profile confirmed choices live in separate workspace preferences. Preparation can create Session files and Provider clients; it does not execute Agent tasks. Failed preparation closes owned resources. Application cleans up failed startup. Activation hooks do not provide cross-process transactions or rollback arbitrary external effects.

Manifest schema remains 5. Recovery validates each recorded manifest against its own contents and allows changed environments; it does not restore arbitrary Python state or replay unknown paid work. See [Run recovery](../README.md#recovery) and [Session](../../core/session/README.md). No module-specific environment variables.

```bash
.venv/bin/python -m unittest tests.run.test_assembly tests.run.test_resources tests.run.test_cli tests.workflows.test_resume_history tests.workflows.test_decoupling -v
```

Checks use fake Providers and temporary state.

Assembly supplies an optional generic secret resolver from the host environment to Lab. Selected [web tools](../../lab/tools/web/README.md) receive only the named search credential; keys are not added to manifest parameters or the minimal child-process environment. Construction makes no search or fetch requests.

The optional [SSH environment](../../lab/environment/ssh/README.md) uses this
resolver for its named account and password. Construction makes no SSH request;
Application startup connects and retirement closes it. Catalog permits a backend
to supply `with_permissions(policy, confirm=..., audit=...)`, returning a guarded
environment and authorizer for its path namespace. Assembly records that
authorizer's `identity()` when supplied, otherwise the host policy identity.
Authentication values never enter either identity.

## Bound isolated task execution

[trial_budget.py](trial_budget.py) provides `TrialInvocationBudget` and `BudgetedRegistry`: reserve before each main or auxiliary Provider call, cap output requests, share one allocation, and preserve normal resource cleanup. The generic [trial.py](../trial.py) entry composes the normal Application using frozen H/source/S and copied artifacts. It verifies resolved mechanisms and models before submitting the complete task, writes actual runtime/invocation receipts, and rejects changed source material.

The external executor owns environment isolation. A trial packet explicitly authorizes ordinary local operations in its isolated workspace; standard protected credential paths remain denied. This does not change normal interactive authorization. Frozen state copies may change within a trial and are discarded as production learning state. Cancellation writes the available receipt and closes owned resources. Pre-construction errors may have no invocation receipt; unknown work is not assumed free or replayed. See [Original task experiments](../../lab/improvement/experiments/README.md).
