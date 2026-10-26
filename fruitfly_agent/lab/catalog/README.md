# Lab Catalog

[Up: Lab](../README.md)

Register mechanisms, validate selections, and assemble a runtime deterministically. Run supplies workspace, Session, and Provider bindings; Catalog owns registration and assembly contracts. Object modules own target adapters; Improvement owns per-job stage contracts.

Start with [Register configurable components](CONFIGURATION.md) to expose a new
implementation through the shared H/S/I configuration protocol. See
[Component documents](../../runtime_spec/COMPONENTS.md) for the file grammar and
[Experiment configuration](../../experiments/CONFIGURATION.md) for edit grants.

## Register a mechanism

| Step | Action |
|---|---|
| 1 | Implement the relevant [Lab contract](../README.md#develop-an-algorithm). |
| 2 | Define a stable ID, concise distinguishing description, implementation/guide paths, contributions, parameters, dependencies, effects, and installer. |
| 3 | Add the definition to built-ins or use `builtin_catalog().extended(definitions)`. |
| 4 | Select the mechanism in a harness profile and inject the catalog into `RunApplicationFactory`. |
| 5 | Verify assembly, Application use, and cleanup offline. |

The [offline example](../../../examples/extensions/README.md) completes this path. The CLI does not scan Python packages for plugins.

Improvement registers one shared workflow configuration. Per-job generator factories and stage bindings use the [public Improvement API](../improvement/README.md#extend-search), independently of selectable runtime mechanisms.

## Files

| File | Responsibility |
|---|---|
| [components.py](components.py) | Offline `ComponentSpec` / `ResolvedHarness` inventory and actual assembly verification |
| [models.py](models.py) | Definitions, selections, and UI selection groups |
| [catalog.py](catalog.py) | Parameter, dependency, capability, and conflict resolution |
| [builtins.py](builtins.py) | Explicit built-in definitions and installers |
| [SSH registration](../environment/ssh/README.md) | Optional remote execution, credentials and namespace permissions |
| [assembly.py](assembly.py) | Assembly context, state, and installer execution |
| [tool_providers.py](tool_providers.py) | Async external-tool preparation, status and separate authorization contracts |

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

## Prepare external tools

`MechanismDefinition.tool_provider(parameters, ToolProviderContext)` optionally
prepares dynamic tool declarations asynchronously. Run calls it only for enabled
mechanisms before `build_runtime`. The context supplies workspace, secret lookup,
startup approval, immediate resource ownership and content-addressed artifact I/O.
Return `PreparedToolProvider` with frozen tools, resources, compact identity,
one external authorization policy per tool and a read-only status callback.
Register each resource through `context.own` before awaiting startup so later
failures can clean it up. Configuration discovery never invokes this callback.

Pass prepared results through `AssemblyContext.tool_providers` and
`resolve_harness(..., tool_providers=...)`; the installer adds exactly those tools.
Synchronous assembly rejects an enabled provider without preparation. An offline
inventory cannot claim dynamic names before preparation. Generic status/startup
views keep transport logic out of Run and Interactive. See [MCP](../mcp/README.md)
for the implemented stdio provider and its limits.

## Configuration and targets

`MechanismDefinition.prepare_targets(state, context)` optionally exposes object-owned
adapters independently of mechanism or search enablement. It runs after assembly and must be idempotent. It may
consume declared artifacts and register targets; it must not start Providers,
research or external execution. Disabled capabilities must not consume bindings
for tools that are absent. Returned resources follow normal construction ownership.


`MechanismDefinition.setup` optionally declares `MechanismSetup` from
`catalog.models`: ordered parameter fields, required fields, hidden
`SetupCredential` inputs bound to secret-variable parameters, and setup guidance.
Run projects this metadata into Interactive's generic setup contract. Forms
collect secrets separately from parameters, validate each field, review with
hidden values, and stage selection only after confirmation. Backend-specific
validation stays with the definition. Configuration makes no backend connection.

`MechanismSetup.credential_resolver(parameters)` optionally computes hidden fields
from the current form values. It returns `SetupCredential` declarations, never key
values. `definition.setup_credentials(parameters)` validates the resolved fields.
A credential's `variable` can declare the resolved secret name; blank retains the
existing binding to the named string parameter. `allow_whitespace=False` is suitable
for API keys; its default preserves credentials such as SSH passwords. Ordinary
form fields and hidden values use separate mappings, so a visible variable-name
field may also name its corresponding hidden credential binding. Declarations
within each mapping must remain distinct.

Run and Interactive pass pending non-secret values to form projection and
validation. The terminal refreshes credentials after ordinary fields, so changing
service or variable in the same form changes the credential binding without
staging partial configuration. Static SSH setup declarations remain supported.

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
| `GeneratorRegistry` | Declare per-job candidate generators through the Improvement API. |

Selection groups share display placement and exclusivity. Display metadata does not enter runtime identity; effective parameters and implementation IDs do. See [Algorithms](../algorithms/README.md), [Improvement](../improvement/README.md), and [Harness configuration](../../run/configuration/README.md).

No Catalog-specific environment variables. Catalog itself makes no model requests; selected mechanisms declare their own effects.

`MechanismDefinition.configuration_category` optionally declares menu placement
without adding a Core mechanism layer. Offline legacy configuration and
candidate classifiers are also exposed for the Run migration entry; runtime
hosts do not branch on concrete algorithm names.

```bash
.venv/bin/python -m unittest tests.lab.test_catalog tests.run.test_configuration tests.run.test_assembly -v
```

## Assemble host permissions

[permissions.py](permissions.py) exports `PermissionPolicy` and `apply_permission_policy`. The latter delegates to the selected policy’s `bind` method. The standard strategy attaches an authorizer and wraps the execution environment; `PermissionPolicy.unrestricted(workspace)` keeps the backend and allows tools explicitly. `prepare_environment` supplies the selected strategy’s process environment before installers run. Run imports these public host entry points rather than concrete environment implementation modules. This host policy is not a selectable research algorithm and cannot be disabled by a model-edited mechanism selection.

`AssemblyContext.process_environment` supplies an explicit minimal environment to owned process backends. IPython uses it at process startup; Providers retain host-managed credentials.

`AssemblyContext.secret_resolver(name)` is an optional host capability for selected network tools. It defaults to absent for existing callers. Run binds its secret environment lookup; Lab does not read ambient environment variables. Returned values must stay out of selection parameters, manifests, process environments and errors. The [web tools](../tools/web/README.md) use this capability for search credentials without making requests during construction.

## Describe the execution environment

Catalog exports `ExecutionEnvironmentDescription` and
`EXECUTION_ENVIRONMENT_COMPONENT` from [Environment](../environment/README.md).
An environment installer can register
`state.with_component(EXECUTION_ENVIRONMENT_COMPONENT, description)` with the
backend's display label, working directory and optional server address. Publish
only non-secret text; never include authentication values or transport objects.
This adds no connection or health request. Run translates the installed view into
Interactive status; Application exposes a replacement only after successful startup
and activation. Backends without a description remain supported and display
Unavailable. Permission wrappers do not alter this metadata.

## Declare credential requirements

`MechanismDefinition.credential_variables(parameters)` optionally returns a tuple
of secret environment variable names. The callback is pure and offline: it must
not read values, construct resources or make requests. It receives normalized
parameters so conditional backend requirements and overrides have one owner.
`definition.required_credentials(parameters)` validates, deduplicates and sorts
these names. `catalog.required_credentials(selections)` also validates selections
and collects requirements from enabled mechanisms only. Unknown/duplicate
selections and invalid variable names fail explicitly.

Assembly resolves declared names through the host's `secret_resolver` before each
installer. Missing values fail before that installer constructs resources. The
installer receives a snapshot resolver limited to those declared names. Mechanisms
without this declaration retain the existing assembly context behavior. Secret
values never enter metadata, parameters or manifests. Configuration consumes the
same declaration to show set/missing status; Eval uses it to forward credentials
to task containers without tool-specific branches. Setup form credentials remain
independently declared through `MechanismSetup`; existing forms are unchanged.

## Declare auxiliary model dependencies

`MechanismDefinition.model_profiles(parameters)` optionally returns a tuple of
non-empty model catalog labels. It receives normalized enabled parameters and
must remain pure and offline. `catalog.required_model_profiles(selections)`
validates and combines those declarations. An empty tuple means reuse the active
model. Component improvement declares its optional editor model this way; Eval
stages only the main and declared auxiliary models and their named credentials.
Custom mechanisms requesting additional models must declare them.

## Register experiment dependencies

Built-in file memory, workspace skill files and local knowledge register initial text snapshot sources through `persistent-state-snapshots`. Live HTTP context registers an `experiment-blockers` reason because responses cannot be frozen. Installers register capabilities without taking snapshots or starting model work. Custom mechanisms must register each persistent dependency they read; arbitrary plugin heap state and external services remain unsupported. See [Algorithm versions](../algorithms/README.md) and [Original task experiments](../improvement/README.md).

## Declare per-job improvement support

Per-job candidate generators register through `GeneratorRegistry`; stage factories are injected with `WorkflowBindings`. Catalog owns mechanism construction and object adapters, without a parallel algorithm selector or method binder.
## Resolve one harness inventory

`resolve_harness(profile, catalog)` reads enabled selections and owner declarations
without constructing Providers or running installers. `ResolvedHarness.select`
checks configured component existence, execution capabilities and H/S/I roles.
Availability is not authorization: experiments explicitly select editable IDs.
Absent owners provide no editable state. Unsupported explicit selections fail
rather than enabling mechanisms or silently removing components.

Enabled mechanisms' declared tools supply guidance components generically. Other
components use `component_specs(parameters, enabled)` returning `ComponentSpec`
values. The callback is pure and receives normalized enabled parameters; disabled
owners receive an empty mapping. Owners with no active component return an empty
tuple. Object-target preparation and this declaration must agree.

`component_validator(component_id, options, inventory)` optionally validates
component-owned search options offline. `execution_fields` declares controlled
scalar runtime settings. No component names are interpreted by the experiment CLI.
Actual assembly verifies declared tools, targets and roles before execution and
records the final schema and effective execution values.

Run, Lab and Eval consume the [shared runtime specification](../../runtime_spec/README.md);
Catalog retains mechanism dependency, conflict, parameter and component ownership.
The [execution policy adapter](../execution_policy/README.md) uses these contracts.

```bash
.venv/bin/python -m unittest tests.lab.test_harness_inventory tests.experiments.test_harness_validation
```
