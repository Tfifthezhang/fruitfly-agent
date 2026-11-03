# Register Configurable Components

[Up: Catalog](README.md)

Every selectable runtime or improvement capability needs a registered configuration
position. Internal helper classes do not need their own configuration entry.
Use the [component document grammar](../../runtime_spec/COMPONENTS.md); do not add
algorithm-specific parsing to Run, the terminal or Eval.

## Choose the owner

| Capability | Owner and registration |
|---|---|
| Tool, environment, context mechanism, retained document | Owning Lab module, composed by Catalog |
| Candidate generator | Improvement `GeneratorRegistry` |
| Round flow and incumbent retention | Fixed Improvement engine; stopping conditions remain separate |
| Completed assessment/comparison | Shared prompt-driven model evaluator |
| Task execution | Execution registry |
| Model protocol | Providers |

These implementations keep their own execution interfaces. Shared configuration
declarations provide discovery, validation and composition, not one universal
algorithm implementation. Registration and inspection must remain offline.

## Declare a mechanism

A `MechanismDefinition` already supplies parameter descriptors, dependencies,
effects, installation, model/credential requirements and lifecycle ownership.
Its ID is selectable in a component document without another parser branch.
`configuration_role` defaults to H; retained owners explicitly declare S and
Improvement declares I.

```yaml
id: example-note
role: H
implementation: example-note
parameters:
  note: Use the task evidence.
```

`example-note` is a placeholder extension ID. Register its definition before
loading this document. Unknown fields fail through its parameter descriptors,
including when disabled. Parameter defaults belong to the definition once.

Compose extensions with `builtin_catalog().extended(definitions)` and pass that
catalog to `RunApplicationFactory(catalog=...)` or
`load_system_config(path, catalog=...)`. The CLI does not scan Python packages or
execute import paths supplied in YAML. The [offline extension](../../../examples/extensions/README.md)
demonstrates executable registration and fake-Provider assembly.

## Expose an additional configuration surface

Use `configuration_surfaces` when an owner exposes a distinct prompt, guidance,
execution or I setting surface. A `ConfigurationSurface` declares:

| Field | Contract |
|---|---|
| `id`, `role` | Stable component identity and H/S/I role |
| `binding`, `key` | Registered projection into prompt, artifact, configuration or settings |
| `normalize` | Pure field/default validation; no clients, files or model calls |
| `encode`, `decode` | Exact text projection when applicable |
| `edit_options` | Optional field-grant normalization into the owner's candidate adapter |
| `restore` | Restore exact artifact-backed settings when applicable |
| `default`, `reference` | Optional pure derived defaults and canonical built-in text identities |
| `standalone` | Surface prepared without enabling a separate installer; default false |

A surface does not install its owner twice. The shared Tool catalog policy is prepared after tool installation;
individual owners retain schemas, usage resources, implementation and permissions.
An explicit surface and a frozen artifact must describe the same effective value.
Candidate bundles preserve exact artifact bytes as well as readable values.

Model-role dependencies use `model_role_parameters` with `ModelRoleRequirement`
values. Declare the parameter, purpose, condition, explicit fallback and lazy
construction in one owner definition. They bind catalog aliases or `{inherit: executor}` references in `models.roles`; they
are not credentials and cannot appear in component parameter documents. See
[auxiliary model admission](README.md#declare-auxiliary-model-dependencies).
Declared fallback slots are normalized before manifest recording even when their
owners are disabled; this does not construct auxiliary Providers. Ordinary saves
retain these slots so developers can assign a model without discovering hidden fields.
Keep Provider-specific validation in Providers and component-specific validation
in the owning module.

## Declare editing separately

Configuration support does not imply candidate editing. Every new selectable
algorithm must ship a meaningful Improvement surface through its owning module's
public registration entry, normally `improvement.py`. Design this surface with the
algorithm, rather than adding it after runtime implementation. See
[Lab design rules](../README.md#design-for-improvement).

A mechanism uses `configuration_edit`; a separate surface can use `edit_options`.
Both resolve
the [experiment's field grants](../../experiments/CONFIGURATION.md#grant-component-changes)
through the owner. The corresponding target must validate each candidate and
actually apply it in a supported runner.

The owner declares mutable prompts/content and parameter fields, protected
invariants, H/S/I identity, state isolation and the candidate lifecycle. Reuse
`MechanismDefinition`, `ConfigurationSurface` and existing target/execution ports;
the module entry is a composition boundary, not another global registry. Place
selectable implementations under the owner's `methods/`, with module-level
registration and shared services outside it.

| Support | Required evidence |
|---|---|
| Configurable | Strict fields/defaults, dependency checks and successful ordinary assembly |
| Editable | Owner adapter, authorized fields/bounds, rejected forbidden changes |
| Runnable candidate | Changed values observed in actual isolated execution and identity |
| Activatable | Owner binding, independent verification and Application lifecycle support |

Unsupported operations must report a reason before model work. Parameter
visibility alone is insufficient. Existing jobs preserve component IDs, owners,
roles and schemas; adding/removing components is not an available candidate edit.

## Declare state and resources

Stateful components must define initial content, reset/update rules, trial sharing,
snapshot requirements and recovery. Reuse registered retained text and snapshot
sources where applicable. An uncapturable external dependency must block an
experiment instead of pretending to be reproducible.

Register owned resources immediately with `context.own`; clean up failed
construction, startup and cancellation. Declarations do not provide OS isolation,
arbitrary source deployment or automatic rollback.

## Verify the registration

Cover ordinary configuration, disabled behavior, invalid fields, dependency
conflicts, construction/startup failure and cleanup. For editing, show that a
changed value reaches the runner and manifest while the source stays unchanged.
Use fake Providers and temporary workspaces. Real service checks require an
explicit integration run. See [Architecture tests](../../../tests/architecture/README.md)
and [Contributing](../../../CONTRIBUTING.md).

`configuration_snapshot(parameters, workspace)` declares bounded local resource
capture for configuration export. It returns the owner's existing `StateSnapshot`;
`configuration_resources` merges files and rejects conflicting writers. Skill,
file-memory and local-knowledge owners reuse their ordinary state snapshot rules.
The materializer copies only supplied registered files under `resources/` and
records their workspace paths and hashes. Live services remain external
requirements. This callback is separate from pure parameter normalization and runs
only when explicitly freezing/exporting resources.

A surface may declare a pure `default` callback. The shared Tool catalog uses
this to expose its default policy during offline inspection and
materialization, without creating a runtime or opening a service.


## Expose parameter candidates

Declare `MechanismDefinition.parameter_paths` to map installer parameter names to
public `instructions.*`, `settings.*` or `content.*` paths. The ordinary loader,
inspection, candidate export and activation use the same codec in `parameters.py`.
`editable_parameters` defaults scalar descriptor paths to `settings.<name>`;
owners map model-facing prompts and retained content explicitly. Every editable
field needs a nonempty description, type, current/default value and constraints.
Optimization descriptions and experiment grants use the exact full
`parameters.<category>.<name>` path. Internal installer names are not a second
public configuration format.


[Parameter adapters](../improvement/components/README.md#edit-owner-parameters)
reuse ordinary normalization and assembly. Built-in Bash, layered compaction, working memory, Web and
IPython owners declare explicit editable parameter whitelists. Discovery still
constructs no clients. Their targets require `configuration-materialization`;
unsupported runners reject the edit. I editor/evaluator prompts use fixed-I comparison instead
of ordinary task scores. Evidence response page size and independent phase times remain fixed experiment settings. Authorize fields
and numeric bounds through the existing experiment grants; model bindings and
secret values are not editable parameters.

`normalize_configuration_binding` is the public pure projection used for H identity.
It applies the owning descriptor's normalization before hashing, so a valid JSON
number and its assembled numeric value cannot produce different candidate identities.
Run injects this projection into version construction; activation still validates
the actually assembled runtime.

## Enforce algorithm readiness

`LabCatalog.require_optimization()` runs before Run constructs runtime services.
Every algorithm needs an executable component/parameter declaration. Tools
share the Tool catalog policy while keeping individual operation contracts fixed. Infrastructure connectors declare a concrete
`optimization_exemption` explaining their protected responsibility. This is not
permission to expose an algorithm without an optimization surface. Assembly
verifies that declared targets actually exist; component admission also checks
timing, boundary and runner capabilities through the
[optimization protocol](../../improvement/contracts/README.md#declare-optimization-surfaces).
Information retrieval limits, Skill catalog size and programmatic offload
thresholds have owner-controlled parameter adapters. Their shared configuration
candidates require configuration materialization; incompatible or missing backends
reject unsupported parameter changes before model work.

Owner declarations set `default_selected` on component and optimization metadata.
Tool parameter owners set it false: discovery still reports availability, while
automatic experiment/chat selection excludes them. Explicit grants remain valid.
Assembly checks that declarative and executable defaults agree.

## Register one default parameter document

`MechanismDefinition.default_resource` and `ConfigurationSurface.default_resource`
select an explicit `(package, YAML resource name)` owned by the registration.
The document uses the public component envelope with its fixed H/S/I `role`.
Keep each parameter's default value there once. Constructor factories and
parameter descriptors derive those values; schema types and constraints stay in
Python. Model aliases remain system roles, outside parameter documents.
Owners without parameters can use an empty derived document without a YAML file.

[defaults.py](defaults.py) resolves registered defaults and records package
receipts. It verifies component identity and role, and requires every non-model
mechanism parameter exactly once. Catalog refreshes descriptor defaults from the
owner resource; it neither executes installers nor creates Providers.
Configuration parsing never imports a package named by user YAML.

Normal saving preserves source intent. `component_profile(..., freeze=True)` and
`materialize_system` expand complete parameters for isolated execution. Candidate
`parameters.yaml` files retain protected identity and role. String and numeric
changes use the same typed owner validation and existing grants. A single
canonical document supplies each version; text projections and artifact bindings
are derived execution representations, not independent editing locations.

When deriving a new mechanism from an existing definition, register its own
`default_resource` or explicitly clear that field and supply descriptor defaults.
A resource declaring another component ID or role is rejected; cloning a Python
dataclass does not transfer ownership of the original component document.
