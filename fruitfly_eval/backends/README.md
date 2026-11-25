# Compose evaluation backends

[Up: Eval](../README.md)

Backends own prepared material and execution environment mechanisms. Benchmark
adapters own dataset identity and official outcome interpretation. The existing
[Catalog](../catalog.py) composes these capabilities; this package has no separate
registry, model selection, inference request policy or automatic backend fallback.

## Provide preparation

Expose a `preparation` object satisfying `PreparationBackend` on an adapter.
`read_host` parses the owner's machine settings. `prepare` freezes materials and
may prepare containers, but must not perform model inference. `load` validates
persisted material before returning its task inventory. `inspect` reports current
readiness and unknown external conditions without executing tasks. All methods
receive the selected descriptor, so one implementation can serve many datasets.

Prepared task rows expose exact `id` values. `select_prepared_tasks` rejects
unknown names and copies subsets without rewriting the source receipt. Additional
source/runtime material remains owned by the backend and is validated by `load`.
Missing preparation capability is an explicit error, not a switch to Harbor.

An adapter supporting explicit machine files also implements `HostConfigured`.
Eval supplies `--host-config` through that port rather than testing a concrete
adapter class. Ordinary run-only adapters need neither preparation nor host-file
support. Unsupported explicit capabilities fail before task execution.

| File | Responsibility |
|---|---|
| `__init__.py` | Preparation and explicit host configuration protocols; capability admission |
| `harbor.py` | Existing Harbor preparation through the shared port |
| `control.py` | Optional scoped stop capability |
| `isolated.py` | Explicit interpreter/source subprocess protocol without shell dispatch |
| `mounts.py` | Shared prepared dependency mounts, private trial relay mounts and environment ownership |

The [Harbor owner](../harbor/README.md) retains its configuration and receipt
validation. Sources do not acquire permission to inspect Provider accounts or
implement model-specific authentication. Native Agent model configuration remains
owned by the normal Runtime specification and Providers.

Offline checks: `tests.eval.test_backend_preparation`, `tests.eval.test_cli`,
`tests.eval.test_task_selection`, `tests.eval.test_host_serialization`.
`WorkspaceInputs` lets an adapter contribute validated relative initialization
files without changing generic scaffolding. It cannot replace shared system,
model or secret files. `ExecutionControl` routes stop through the retained
request and the same Catalog; no concrete adapter check selects it.

A second fake backend demonstrates independent preparation and exact selection;
these tests do not establish real container or model compatibility.

Common machine settings may reference an owner document with `backend: {file: ...}`.
The common parser validates the reference only; backend fields remain with their
owner. Derived hosts preserve the absolute reference. The built-in Harbor backend
rejects an unused backend document instead of silently ignoring it.
