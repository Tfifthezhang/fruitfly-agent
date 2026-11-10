# Write Component Configuration

[Up: Runtime specification](README.md)

Select H/S/I component documents using the single system configuration format. Daily and default files
use the same schema. A component is configurable only when its implementation is
registered. Configuration does not grant experiment modification or adoption.

## Select documents

```yaml
default_profile: baseline
profiles:
  baseline:
    models:
      catalog: models.yaml
      roles:
        executor: offline
    H:
      base_prompt: {default: true}
      layered-compaction: {default: true}
      local-env: {default: true}
      read-tool: {default: true}
    S: {}
    I: {}
```

`offline` is a placeholder catalog alias. It must name an entry in the referenced
model catalog. The API model ID belongs inside that entry. Aliases are case-sensitive.

## Write a component

```yaml
id: layered-compaction
role: H
implementation: layered-compaction
enabled: true
parameters:
  settings:
    tail_tokens: 4096
```

The component ID and role must match its position and registered definition.
File paths resolve from the declaring file. A reference selects exactly one of
`{default: true}`, `{file: path}` or `{inline: document}`. Default references
optionally accept `enabled: false`; other keys and non-boolean flags fail.
Registered defaults resolve through Catalog, not an import path from YAML. Unknown
fields and duplicate YAML keys fail. Moving a file does not change its role.

Use a `base_prompt` document with `parameters.instructions.system: |` for inline instructions.
There is no mandatory separate prompt text file. Tool parameters come from the
owning [Catalog definition](../lab/catalog/README.md); tool-call arguments are not
automatically component configuration fields.

## Keep ownership explicit

| Role | Content | Related guide |
|---|---|---|
| H | Operational prompts, tools, context and memory/Skill loading policies | [Runtime architecture](../README.md) |
| S | Registered memory and Skill libraries, or independent retained content | [Algorithm targets](../lab/improvement/targets/README.md) |
| I | Strategies and prompts for editing/evaluating improvements | [Improvement](../lab/improvement/README.md) |

The pure `runtime_spec.load_harness_config` reads explicit documents, retains
unresolved default references and records file hashes. `lab.catalog.load_system_config` also validates registered owners and
projects values for runtime assembly. Run's public loader uses this registered
path. Neither loader constructs Providers or writes artifacts.

See [Run configuration](../run/configuration/README.md) for application and
[Experiments](../experiments/README.md) for modification authorization. Configuration
has no version marker or alternative flat profile reader.

## Bind models once

`profiles.<id>.models.roles` selects model catalog aliases or explicit executor
inheritance. Templates and generated configuration retain a position for every
registered role that defaults to executor. Configure the task model once:

```yaml
models:
  catalog: models.yaml
  roles:
    executor: main
    editor: {inherit: executor}
    assessor: {inherit: executor}
    working_memory: {inherit: executor}
    context_query: {inherit: executor}
    context_summary: {inherit: executor}
    memory_maintenance: {inherit: executor}
```

`main` is a placeholder catalog alias. Replace an inherited value with another
catalog alias to use an independent model, for example `working_memory: small`.
A string always names a catalog entry, including the string `executor`;
`{inherit: executor}` explicitly follows the current executor after model changes.
Unknown inheritance fields, other reference targets, null/empty bindings and
executor self-reference are rejected. Omitted auxiliary roles use their registered
executor fallback. Owners may explicitly disable fallback for a strict requirement.

Inheritance remains symbolic through configuration saves, candidate materialization
and container staging. Providers bind after the executor is selected. Conditional
roles only call models when their mechanism needs them. Unused I services are lazy
and require no separate clients or keys during daily startup. Actual calls retain
their role and resolved model identity. Model roles are outside ordinary edit grants.

## Describe supported H/S/I content

| Document | Typical parameters | Parameter owner |
|---|---|---|
| `base_prompt` (H) | `instructions.system` | [Base prompt](../lab/base_prompt/README.md) |
| Tool/environment/context mechanism (H) | Its registered descriptors | [Catalog](../lab/catalog/CONFIGURATION.md) |
| `file-memory`, `skills` (H) | Reading/loading instructions and declared settings | [Augmentation](../lab/context_manager/augmentation/README.md) |
| `memory-library`, `skill-library` (S) | `content.documents`; strict attributed JSON entries | [Memory](../lab/context_manager/augmentation/memory/methods/file_memory/README.md), [Skills](../lab/context_manager/augmentation/skills/README.md) |
| `improvement-editor` (I) | `instructions.{system,propose,reflect}` | [Editor](../lab/improvement/editor/README.md) |
| `improvement-evaluator` (I) | `instructions.criteria`, `instructions.assess`, `instructions.compare` | [Assessment](../lab/improvement/assessment/README.md) |

Search scheduling, evidence page size and independent phase times belong to the
fixed [experiment configuration](../experiments/CONFIGURATION.md). They do not
become editable I components. Facts collection preserves raw observations for the shared model evaluator.

A tool's complete description is derived from its method default document; a separate guidance
file is needed only for an explicit value. To configure S, select its owner under
S alongside its enabled H loader and supply initial content. Content surfaces do not enable a loader implicitly. Each trial receives its declared frozen initial state.
Editing retained text does not imply automatic learning or trained weights.

## Preserve exact resources

Generated bundles may place an `artifacts` mapping in an owning component document.
It maps declared artifact slots to exact text. This preserves adopted instructions,
evaluator prompts and retained content without depending on the source artifact store.
The owner must declare and consume each slot; unknown slots fail. For an explicit
surface, the artifact and readable parameters must describe the same value.
Normal authoring should use parameters and let candidate/export code create these
exact bindings. Secret values never belong in either representation.

The editor's detached workspace uses `parameters.yaml` with `id`, `role`,
`implementation` and typed `parameters`. Identity, role, implementation, model
bindings and protected fields cannot be changed. String and numeric fields use
the same owner adapter and grant paths. [Experiment field grants](../experiments/CONFIGURATION.md#inspect-configuration-before-models)
authorize changes; the owner codec derives the existing execution binding.
A file editing capability alone does not grant execution or adoption.

## Preserve default intent

Default values live in registered owner YAML resources. Types, descriptions and
constraints remain in the owner declaration. No working-directory components
hierarchy is required. Normal saves keep default/file references when unchanged;
changed components become explicit documents. Explicit text equal to the default
remains explicit. There is no per-field inheritance or automatic merge language.

Candidate/export materialization writes complete effective values, including
numeric defaults, I instructions and protected owner settings. Its output uses
the same component format and contains no unresolved default references.
Adoption fixes each changed component's parameter version. Other components keep
their original references. Package-source receipts reject stale default expansion;
hosts retain configuration transactions and parent-version checks.

## Inspect and extend

```bash
.venv/bin/python -m fruitfly_agent.run.configuration.inspection --config .fruitfly/default-config.yaml
```

The command reads local declarations without model requests. Run the experiment
check separately to validate a selected backend and modification grant. A
component file being valid does not imply every runner can execute or edit it.
Use [Catalog registration](../lab/catalog/CONFIGURATION.md) to add a component,
not a special case in the parser. See [configuration examples](../../examples/configuration/README.md)
for the matching generated tree.

Exports include `snapshot.json` with source document hashes, normalized system
identity, declared implementation IDs, component content hashes and the model
catalog hash. These IDs do not snapshot implementation source or prove model
quality. Owner-declared initial resource files are copied to `resources/`, with
workspace-relative paths recorded in the snapshot. Explicit export previews
those files before writing. Keep that working-directory layout for resource-backed
components; services and runtime-specific dependencies still need preparation.

## Declare developer extensions

A system profile may contain `extensions: ["../extension.py", "entrypoint:NAME"]`
beside `models`, H, S and I. Entries are explicit nonempty source strings; duplicate
sources fail. File paths resolve relative to the declaring system file. This
field selects installed developer code, not a model-editable algorithm field.
It survives materialization and participates in profile identity. Run owns loading;
the pure specification parser never executes extension code. See
[Developer Extensions](../extensions/README.md) and
[Run hosting](../run/extensions/README.md). No configuration version is added.

## Select a delegated model

`models.roles.subagent: {inherit: executor}` follows the current main model;
`models.roles.subagent: secondary-model` pins an existing catalog alias. The alias
is a placeholder until registered. This uses the same role grammar and model menu
as other roles. [Subagent](../lab/agents/subagent/README.md) owns its one H toggle,
settings, execution limits and tools. The component is disabled in the default
profile; its model position remains available for configuration.
