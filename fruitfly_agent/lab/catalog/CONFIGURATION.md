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
| Search and next-seed policy | Improvement strategy/exploration registries |
| Completed assessor | Assessment registry |
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

A surface does not install its owner twice. Tool guidance uses the tool's owner;
the owner remains responsible for tool schema, implementation and permissions.
An explicit surface and a frozen artifact must describe the same effective value.
Candidate bundles preserve exact artifact bytes as well as readable values.

Model-role parameter mappings are declared with `model_role_parameters`.
They bind aliases selected in the config's `models.roles`; they are not credentials.
Keep Provider-specific validation in Providers and component-specific validation
in the owning module.

## Declare editing separately

Configuration support does not imply candidate editing. A mechanism may provide
`configuration_edit`; a separate surface may provide `edit_options`. Both resolve
the [experiment's field grants](../../experiments/CONFIGURATION.md#grant-component-changes)
through the owner. The corresponding target must validate each candidate and
actually apply it in a supported runner.

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

A surface may declare a pure `default` callback. Built-in file/shell tools use
this to expose their actual default description during offline inspection and
materialization, without creating a runtime or opening a service.
