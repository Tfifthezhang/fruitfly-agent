# Lab Catalog

[Up: Lab](../README.md)

Register mechanisms, validate selections, and assemble a runtime deterministically. Run supplies workspace, Session, and Provider bindings; Catalog owns registration and assembly contracts. Independent improvement method packages own their definitions and installers.

## Register a mechanism

| Step | Action |
|---|---|
| 1 | Implement the relevant [Lab contract](../README.md#develop-an-algorithm). |
| 2 | Define a stable ID, concise distinguishing description, implementation/guide paths, contributions, parameters, dependencies, effects, and installer. |
| 3 | Add the definition to built-ins or use `builtin_catalog().extended(definitions)`. |
| 4 | Select the mechanism in a harness profile and inject the catalog into `RunApplicationFactory`. |
| 5 | Verify assembly, Application use, and cleanup offline. |

The [offline example](../../../examples/extensions/README.md) completes this path. The CLI does not scan Python packages for plugins.

An improvement package exposes its own definition factory; built-ins explicitly collect [OPRO's definition](../improvement/methods/opro/README.md). External methods can supply definitions through `builtin_catalog().extended(definitions)`. Shared text improver assembly belongs to [Improvement](../improvement/README.md#extend-search), so Catalog does not implement search strategies or declare their method-specific parameters.

## Files

| File | Responsibility |
|---|---|
| [models.py](models.py) | Definitions, selections, and UI selection groups |
| [catalog.py](catalog.py) | Parameter, dependency, capability, and conflict resolution |
| [builtins.py](builtins.py) | Explicit built-in definitions and installers |
| [SSH registration](../environment/ssh/README.md) | Optional remote execution, credentials and namespace permissions |
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

`MechanismDefinition.setup` optionally declares `MechanismSetup` from
`catalog.models`: ordered parameter fields, required fields, hidden
`SetupCredential` inputs bound to secret-variable parameters, and setup guidance.
Run projects this metadata into Interactive's generic setup contract. Forms
collect secrets separately from parameters, validate each field, review with
hidden values, and stage selection only after confirmation. Backend-specific
validation stays with the definition. Configuration makes no backend connection.

Every `MechanismDefinition` declares a nonempty single-line descriptor description,
an explicit `implementation_path` to a Python file, and `documentation_path` to a
Markdown guide. Registration rejects missing paths, parent traversal and control
characters. Paths are declared by the owning algorithm; frontends do not infer
them from imports or inspect source. Built-in checks verify that files exist and
descriptions differ. Paths describe the installed package or extension source;
the terminal does not open an editor or execute them.

`input_parameters` explicitly names user-provided resources or content that remain
editable in ordinary configuration, such as Skill paths, initial text and HTTP
endpoints. Other tuning parameters remain validated YAML settings. Display paths
and field visibility do not enter runtime identity. All effective parameters and
implementation IDs continue to do so.

| Declaration | Use |
|---|---|
| `selection_group` and label | Generate an algorithm selector for a shared responsibility. |
| `exclusive_group` | Prevent incompatible simultaneous implementations. |
| `provides/requires_capabilities` | Require a unique enabled provider of a capability. |
| `artifact_slots` | Declare consumed named text bindings. |
| `text-target:ID` component | Register an object's snapshot, validation, and trial adapter. |
| `text-improver` component | Provide `preview`, `search`, and `cancel` through the shared host contract. |

Selection groups share display placement and exclusivity. Display metadata does not enter runtime identity; effective parameters and implementation IDs do. See [Algorithms](../algorithms/README.md), [Improvement](../improvement/README.md), and [Harness configuration](../../run/configuration/README.md).

No Catalog-specific environment variables. Catalog itself makes no model requests; selected mechanisms declare their own effects.

`MechanismDefinition.configuration_category` optionally declares menu placement
without adding a Core mechanism layer. [Learning](../learning/README.md) uses the
`learning` category. Catalog exposes `build_learning` and the policy/processor
component keys as explicit assembly entries. The Run host supplies persistence;
the Lab method supplies material processing. Offline legacy configuration and
candidate classifiers are also exposed for the Run migration entry; runtime
hosts do not branch on concrete algorithm names.

```bash
.venv/bin/python -m unittest tests.lab.test_catalog tests.run.test_configuration tests.run.test_assembly -v
```

## Assemble host permissions

[permissions.py](permissions.py) exports `PermissionPolicy` and `apply_permission_policy`. The latter attaches a generic authorizer and wraps the assembled execution environment. Run imports these public host entry points rather than concrete environment implementation modules. This host policy is not a selectable research algorithm and cannot be disabled by a model-edited mechanism selection.

`AssemblyContext.process_environment` supplies an explicit minimal environment to owned process backends. IPython uses it at process startup; Providers retain host-managed credentials.

`AssemblyContext.secret_resolver(name)` is an optional host capability for selected network tools. It defaults to absent for existing callers. Run binds its secret environment lookup; Lab does not read ambient environment variables. Returned values must stay out of selection parameters, manifests, process environments and errors. The [web tools](../tools/web/README.md) use this capability for search credentials without making requests during construction.

## Register experiment dependencies

Built-in file memory, workspace skill files and local knowledge register initial text snapshot sources through `persistent-state-snapshots`. Live HTTP context registers an `experiment-blockers` reason because responses cannot be frozen. Installers register capabilities without taking snapshots or starting model work. Custom mechanisms must register each persistent dependency they read; arbitrary plugin heap state and external services remain unsupported. See [Algorithm versions](../algorithms/README.md) and [Original task experiments](../improvement/experiments/README.md).

## Declare per-job improvement support

`MechanismDefinition.improvement` optionally supplies a `MethodDefinition` with supported H/S/I roles, target schemas, required execution capabilities and an offline binder. Existing `layer × family` contributions still describe system position. No new Core classification is introduced. [Method selection](../improvement/methods/README.md) checks declarations against the active target and host. Definition and method discovery must not make model requests. Registered methods are available on demand. Configuration menus omit the improvement category. Optional `prepare_targets(state, context)` registers lightweight method-owned targets and consumes declared artifacts without enabling the search algorithm or creating Providers. Per-job binders borrow runtime services and own their search state. Existing enabled hosts and YAML parameter defaults remain supported.
