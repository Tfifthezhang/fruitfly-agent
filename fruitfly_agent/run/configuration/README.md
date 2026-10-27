# Harness Configuration

[Up: Run](../README.md)

Store runtime selections independently of model specifications and mechanism definitions. Manage configuration drafts and resolve model choices without constructing Providers or running algorithms. Candidate-backed menus are supplied through presentation callbacks.

Daily `.fruitfly/config.yaml` and experiment `.fruitfly/default-config.yaml` use
one component format. Write model roles and H/S/I references using the
[component guide](../../runtime_spec/COMPONENTS.md). Unknown fields and version
markers are rejected. The public profile types are shared;
Run's loader additionally applies registered Catalog projections.

The following are resolved Python runtime values and APIs. Authored YAML uses
the component grammar linked above; it has no flat `prompt`, `execution`,
`mechanisms` or `artifact_bindings` profile fields.

| Runtime value / API | Meaning |
|---|---|
| `HarnessConfig` | Default profile and profile mapping |
| `HarnessProfile` | Model catalog/profile, prompt, execution limits, artifact bindings, and mechanism selections |
| `execution` | Declared turn/tool/recovery limits and nested tool scheduling; see [shared fields](../../runtime_spec/README.md#configure-execution) |
| `execution.max_tool_calls_per_turn` | Nonnegative integer, default 64; per outer turn, including detached task trials; 0 prevents tool attempts |
| `prompt` | Optional; `assistant-default` or a text artifact ID |
| `artifact_bindings` | Named slots declared by enabled consumers |
| `load_harness_config(path)` | Parse and validate configuration. |
| `save_harness_config(path, config)` | Atomically replace the file. |
| Default location | `.fruitfly/config.yaml` |

The example uses `.fruitfly/models.yaml`, resolved relative to `.fruitfly/config.yaml`. Explicit catalog paths keep precedence over workspace discovery. See the [file selection rules](../../../CONFIGURATION.md#files-and-precedence).

Daily and baseline configs share this model catalog and select aliases separately
through `models.roles`. Installed initialization creates the catalog only when
absent and preserves an existing regular catalog unchanged.

Unknown fields raise `ValueError`. Catalog validates mechanism IDs and parameters. Store key variable names in model specifications and key values in the environment; keep secret values outside YAML. Short prompt text is supported in component block scalars.

## Files and ownership

**Restore default configuration** stages default harness settings in the current
daily profile while retaining its model selection and pending credentials. Save
persists the draft without changing the active runtime; reset discards it.
Application owns explicit application through Session recovery. Defaults are loaded from an
injected workspace path, validated before staging and never edited by this operation.
Missing or invalid defaults leave the draft unchanged. Explicitly selected default
files retain a read-only controller. See the
[configuration reference](../../../CONFIGURATION.md#restore-default-configuration).

Restoration also stages execution limits. These file settings do not add a
terminal parameter form. Unknown execution fields, booleans and negative/fractional
limits are rejected. Model-call and editor budgets are separate settings.

| File | Responsibility |
|---|---|
| [profile.py](profile.py) | Shared profile types and registered loading/saving |
| [inspection.py](inspection.py) | Offline effective values, model aliases and source documents |
| [export.py](export.py) | Explicit selected-profile export to a new complete component bundle |
| [scaffolding.py](scaffolding.py) | Shared installed H/S/I templates for daily and experiment setup |
| [controller.py](controller.py) | Draft selection, edits, save/reset, and public profile operations |
| [operations.py](operations.py) | Narrow binding/profile edit contracts for host consumers |
| [resolution.py](resolution.py) | Workspace/profile discovery and model catalog resolution |
| [views.py](views.py) | Mechanism and prompt menu projections |
| [model_setup.py](model_setup.py) | Stage models and credentials through profile callbacks |
| [mechanism_setup.py](mechanism_setup.py) | Project registered forms, check setup readiness, stage parameters and enable selections |
| [credentials.py](credentials.py) | Shared secret draft, variable validation and comment-preserving secret-file payloads |
| [persistence.py](persistence.py) | Atomic byte writes for configuration operations |

`profile()`, `stage_profile()`, and `changed` expose draft operations without allowing other services to access private fields. Model setup receives these callbacks and a configuration path. It writes only on save, preserves unrelated content, rolls back ordinary failures, and updates the secret environment after success. No model requests occur during configuration.

`RunModelSetup.options()` projects Provider-owned service groups and preset fields;
`defaults(option_id, values)` projects non-secret request/transport defaults for
review. `stage()` uses the same Provider builder, so confirmation and saved values
agree. Vendor rules and presets stay in Providers; this host owns persistence.
The injected Provider registry supplies SDK/protocol choices through `field()`
and validates the selected pair before staging. Registering another pair updates
those choices without a terminal change or a model request.

Mechanism setup consumes generic Catalog metadata and profile/enable callbacks;
it contains no backend-specific branches. It checks required settings and named
credentials in configuration snapshots and before saving. Model and mechanism
forms share `CredentialDraft`; the existing model/configuration save transaction
writes all staged credentials together, rolls back ordinary failures, and updates
the host secret environment only after success. Reset discards the complete
shared draft. Credential values never enter snapshots, review or harness YAML.

Mechanisms with a Catalog credential declaration show each required variable's
set/missing status in their effects. Enabled missing credentials also appear in
snapshot warnings. This is an offline projection; values stay in `CredentialDraft`.
Web tools expose **Set up…** forms for hidden API keys. `form`, `validate_field`
and `validate_credential` accept optional pending non-secret values; credential
requirements use the service and variable selected in that form. Direct fetch
requires no key. Staging and saving reuse the shared credential transaction, with
no backend-specific host branches. Runtime assembly requires declared credentials.

The public `RunConfigurationController` in [Run](../README.md) composes this controller with candidate-backed prompt presentation. The configuration implementation receives an artifact store and optional prompt-choice callback; it does not discover candidate paths or depend on runtime preparation. Default workspace paths and environment precedence are documented in the configuration reference below. Improvement uses separate typed per-job contracts for components, generators, materials and allocations. The hidden `component-improvement` registration supplies shared editor defaults. Object mechanisms own their artifact slots and validation.

| Reference | Purpose |
|---|---|
| [Configuration reference](../../../CONFIGURATION.md) | File locations, environment variables, and selection behavior |
| [Catalog](../../lab/catalog/README.md) | Mechanism declarations and validation |
| [Run](../README.md) | Artifact resolution and actual runtime identity |

```bash
.venv/bin/python -m unittest tests.run.test_profiles.HarnessProfileTest tests.run.test_configuration.HarnessSelectionTest -v
```

## Inspect and export a system

```bash
.venv/bin/python -m fruitfly_agent.run.configuration.inspection --config .fruitfly/default-config.yaml
# Preview only; replace paths with your own source and an absent output directory.
.venv/bin/python -m fruitfly_agent.run.configuration.export --config .fruitfly/config.yaml --output /tmp/fruitfly-config-export
# Write the reviewed selected profile and frozen model/component content.
.venv/bin/python -m fruitfly_agent.run.configuration.export --config .fruitfly/config.yaml --output /tmp/fruitfly-config-export --apply
```

These operations create no Providers or Sessions and make no requests. Inspection
shows catalog aliases separately from API model IDs and does not print credentials.
Export writes a new directory and refuses existing destinations. `--profile`
selects a profile; omitted selects the source default. `--cwd` supplies the source
workspace for persisted artifact lookup when needed. External environment paths,
stateful sources and services retain their owner's requirements; export does not
create a portable container or restore a Session.

Candidate and Eval builders use Catalog's public `materialize_system` and
`bind_component_changes` ports. Generated candidates contain ordinary configs,
frozen catalogs and exact text bindings. File references are retained on ordinary
save when unchanged; changed documents are written inline in the config rather
than overwriting shared component files. Source inputs remain intact.

Follow [the configuration tree](../../../CONFIGURATION.md#navigate-the-configuration-tree)
for syntax, registration and experiment grants; this guide owns persistence and
application behavior.

Daily configuration saves through the same component exporter. Saving
round-trips built-in prompt identity and derived default tool guidance; disabling
a tool removes its active guidance binding. No generated default override changes
the behavior identity of an unchanged component.
