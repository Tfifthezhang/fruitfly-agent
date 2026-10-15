# Lab Catalog

[Up: Lab](../README.md)

Register mechanisms, validate selections, and assemble a runtime deterministically. Run supplies workspace, Session, and Provider bindings; Catalog owns registration and assembly contracts. Independent optimization method packages own their definitions and installers.

## Register a mechanism

| Step | Action |
|---|---|
| 1 | Implement the relevant [Lab contract](../README.md#develop-an-algorithm). |
| 2 | Define a stable ID, contributions, parameters, dependencies, effects, and installer. |
| 3 | Add the definition to built-ins or use `builtin_catalog().extended(definitions)`. |
| 4 | Select the mechanism in a harness profile and inject the catalog into `RunApplicationFactory`. |
| 5 | Verify assembly, Application use, and cleanup offline. |

The [offline example](../../../examples/extensions/README.md) completes this path. The CLI does not scan Python packages for plugins.

An optimization package exposes its own definition factory; built-ins explicitly collect [OPRO's definition](../optimization/opro/README.md). External methods can supply definitions through `builtin_catalog().extended(definitions)`. Shared text optimizer assembly belongs to [Optimization](../optimization/README.md#extend-search), so Catalog does not implement search strategies or declare their method-specific parameters.

## Files

| File | Responsibility |
|---|---|
| [models.py](models.py) | Definitions, selections, and UI selection groups |
| [catalog.py](catalog.py) | Parameter, dependency, capability, and conflict resolution |
| [builtins.py](builtins.py) | Explicit built-in definitions and installers |
| [assembly.py](assembly.py) | Assembly context, state, and installer execution |

## Assembly contract

| Concern | Contract |
|---|---|
| Installer | Synchronous `(state, context, parameters) -> AssemblyState`; run only when enabled. |
| Validation | Disabled selections still validate ID and parameters; dependencies are not automatically enabled. |
| Unknown mechanism | Raise `ValueError` with available IDs; remove the selection or [register a mechanism](#register-a-mechanism). |
| Compaction parameters | Configure summarization directly; `compaction.profile` is unsupported even when the selection is disabled. Remove that field. |
| Ordering | Satisfy ID/capability dependencies, then use `(install_order, mechanism_id)` among eligible mechanisms. |
| State | Preserve existing capabilities with replacement helpers; mutable hubs must belong exclusively to the candidate runtime. |
| Context stages | Match declared phases and counts; stage IDs use the mechanism ID or its dotted prefix. |
| Reduction | One slot; supply a reducer or a reduction stage, never both. |
| Hooks and callbacks | Clone registries before adding hooks; callback wrappers preserve existing behavior and define merge order. |
| Owned resources | Call `context.own(resource)` immediately after construction; borrowed resources remain with their owner. |
| Returned components | Transfer ownership on return, including when later contract validation fails. |
| Lifecycle | Application deduplicates by identity, starts components, and closes owned objects in reverse order. |
| External effects | Declare effects accurately; declarations do not create isolation, hot reload, or rollback. |
| Implementation identity | Explicit `implementation_id` enters the manifest; it is not an automatic source hash. |

`AssemblyContext` supplies workspace, Session, main model, `provider_resolver(profile, max_output_tokens)`, and optional artifact readers/bindings. Installers must not run research jobs or call models during assembly. Failed assembly prevents activation but does not roll back arbitrary file writes.

## Configuration and targets

| Declaration | Use |
|---|---|
| `selection_group` and label | Generate an algorithm selector for a shared responsibility. |
| `exclusive_group` | Prevent incompatible simultaneous implementations. |
| `provides/requires_capabilities` | Require a unique enabled provider of a capability. |
| `artifact_slots` | Declare consumed named text bindings. |
| `text-target:ID` component | Register an object's snapshot, validation, and trial adapter. |
| `text-optimizer` component | Provide `preview`, `search`, and `cancel` through the shared host contract. |

Selection groups share display placement and exclusivity. Display metadata does not enter runtime identity; effective parameters and implementation IDs do. See [Algorithms](../algorithms/README.md), [Optimization](../optimization/README.md), and [Harness configuration](../../run/configuration/README.md).

No Catalog-specific environment variables. Catalog itself makes no model requests; selected mechanisms declare their own effects.

```bash
.venv/bin/python -m unittest tests.lab.test_catalog tests.run.test_configuration tests.run.test_assembly -v
```

## Assemble host permissions

[permissions.py](permissions.py) exports `PermissionPolicy` and `apply_permission_policy`. The latter attaches a generic authorizer and wraps the assembled execution environment. Run imports these public host entry points rather than concrete environment implementation modules. This host policy is not a selectable research algorithm and cannot be disabled by a model-edited mechanism selection.

`AssemblyContext.process_environment` supplies an explicit minimal environment to owned process backends. IPython uses it at process startup; Providers retain host-managed credentials.

## Register experiment dependencies

Built-in file memory, workspace skill files and local knowledge register initial text snapshot sources through `persistent-state-snapshots`. Live HTTP context registers an `experiment-blockers` reason because responses cannot be frozen. Installers register capabilities without taking snapshots or starting model work. Custom mechanisms must register each persistent dependency they read; arbitrary plugin heap state and external services remain unsupported. See [Algorithm versions](../algorithms/README.md) and [Original task experiments](../optimization/experiments/README.md).
