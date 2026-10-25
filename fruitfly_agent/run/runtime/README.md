# Runtime Preparation

[Up: Run](../README.md)

Assemble resources and prepare new or recovered runtime handles. Application owns startup, active-handle switching, cancellation, and retirement. This module does not add another lifecycle state machine.

| File / entry | Responsibility |
|---|---|
| [assembly.py](assembly.py): `build_runtime` | Construct Providers, assemble Lab components, and apply host permissions |
| [manifest.py](manifest.py): `RuntimeManifest` | Actual assembled runtime identity and serialization |
| [preparation.py](preparation.py): `RuntimePreparer.open` | Acquire a Session writer lease, verify recovery, bind injected services, return an unactivated handle |
| [activation.py](activation.py): `bind_activation` | Compose pre-commit and post-commit hooks around prepared handles |
| [recovery.py](recovery.py) | Session discovery, recorded bindings, manifest checks, and session paths |
| [permissions.py](permissions.py) | Host permission policy and minimal process environment |

Preparation receives configuration selections, separate improvement/candidate/task material services, and explicit construction/presentation capabilities. It does not inspect a Factory, candidate store, improver implementation, or configuration draft. `PreparedRuntime` reports actual bindings to the composition root only when activation occurs. Successful activation commits the environment snapshot; changed mechanisms also commit a rebuilt model projection.

Catalog registers object-owned improvement targets. The improvement host discovers execution and generator definitions without model requests, then constructs job-local stages after a frozen preview is confirmed. Preparation can create Session files and Provider clients; it does not execute Agent tasks. Failed preparation closes owned resources. Application cleans up failed startup. Activation hooks do not provide cross-process transactions or rollback arbitrary external effects.

Preparation uses [Session writer leases](../storage/README.md) scoped to one preparer. Configuration application recovers the already-owned Session without opening a competing writer. Both handles hold a lease until retirement or failed-start cleanup; Application serializes their use. An empty currently owned conversation can be rebound, while standalone empty-session recovery remains rejected.

Manifest schema 7 records all effective declared execution parameters and the
resolved harness inventory in runtime identity. Recovery also reads schemas 3, 4, 5 and 6 without adding invented
historical limits. It validates each manifest against its own contents and allows
changed environments; it does not restore arbitrary Python state or replay unknown
paid work. See [Run recovery](../README.md#recovery) and [Session](../../core/session/README.md).
No module-specific environment variables.

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

## Run non-interactive tasks

The public [CLI](../cli.py) selects `PermissionPolicy.unrestricted(workspace)`
with `--unrestricted` for a fresh task in an externally isolated environment.
Assembly uses the selected policy's `prepare_environment` and `bind` methods.
The standard policy filters process variables and binds guarded authorization;
the unrestricted policy retains the backend and installs an explicit allow
handler. No tool or Core benchmark branch is required. Runtime manifests record
the effective strategy. Timeout, cancellation and cleanup remain unchanged.

`--approve-tools` retains ordinary single-call approvals and protected checks.
Both flags reject interactive/resumed launches and conflict with each other.
Eval invokes `--unrestricted` inside Harbor task environments. Agent configuration
contains no permission preference.

## Bound fresh-task model requests

`limits.py` supplies `ModelCallBudget` and a Provider registry wrapper shared by
main and auxiliary models. Fresh non-interactive CLI tasks accept
`--max-model-calls`; `FRUITFLY_MAX_MODEL_CALLS` is the fallback. Interactive/resumed
launches reject this per-process allowance. An optional
`FRUITFLY_MODEL_USAGE_PATH` receives an atomic count before each Provider call.
Unknown responses remain charged. SDK-internal retries and shell-issued service
requests are outside this harness-invocation count; it is not a price limit.
The override does not rewrite harness/model configuration or create new keys.
