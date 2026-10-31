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
      execution-policy: {file: components/H/execution.yaml}
    S: {}
    I: {}
```

`offline` is a placeholder catalog alias. It must name an entry in the referenced
model catalog. The API model ID belongs inside that entry. Aliases are case-sensitive.

## Write a component

```yaml
id: execution-policy
role: H
implementation: execution-policy
enabled: true
parameters:
  settings:
    max_tool_calls_per_turn: 128
```

The component ID and role must match its position and registered definition.
Paths resolve from the declaring file. `{inline: ...}` may contain the complete
component document instead of `{file: ...}`; exactly one is required. Unknown
fields and duplicate YAML keys fail. Moving a file does not change its role.

Use a `base_prompt` document with `parameters.instructions.system: |` for inline instructions.
There is no mandatory separate prompt text file. Tool parameters come from the
owning [Catalog definition](../lab/catalog/README.md); tool-call arguments are not
automatically component configuration fields.

## Keep ownership explicit

| Role | Content | Related guide |
|---|---|---|
| H | Prompt, tools, guidance, context and execution settings | [Runtime architecture](../README.md) |
| S | Registered retained Skill content | [Algorithm targets](../lab/improvement/targets/README.md) |
| I | Editor and evaluator prompts | [Improvement](../lab/improvement/README.md) |

The pure `runtime_spec.load_harness_config` reads documents and records source
hashes. `lab.catalog.load_system_config` also validates registered owners and
projects values for runtime assembly. Run's public loader uses this registered
path. Neither loader constructs Providers or writes artifacts.

See [Run configuration](../run/configuration/README.md) for application and
[Experiments](../experiments/README.md) for modification authorization. Configuration
has no version marker or alternative flat profile reader.

## Bind models once

`profiles.<id>.models.roles` maps role names to aliases in `models.catalog`.
The executor is the task model; editor and assessor select separate services.
Missing editor/assessor choices inherit the executor. Unused I services are lazy
and do not construct auxiliary clients during daily startup. Actual calls still
contribute observed usage. Model roles are outside ordinary edit grants.

## Describe supported H/S/I content

| Document | Typical parameters | Parameter owner |
|---|---|---|
| `base_prompt` (H) | `instructions.system` | [Base prompt](../lab/base_prompt/README.md) |
| `execution-policy` (H) | `settings`: daily optional tool/turn limits, recovery and tool execution | [Execution policy](../lab/execution_policy/README.md) |
| Tool/environment/context mechanism (H) | Its registered descriptors | [Catalog](../lab/catalog/CONFIGURATION.md) |
| `tool-guidance.<tool>` (H) | `instructions.usage`; enabled tool must exist | [Tools](../lab/tools/README.md) |
| `skill-document` (S) | `content.body`, `settings.max_chars`, optional `settings.source_path` | [Retained targets](../lab/improvement/targets/README.md) |
| `improvement-editor` (I) | `instructions.{system,propose,invariant,domain,compose,reflect}` | [Editor](../lab/improvement/editor/README.md) |
| `improvement-evaluator` (I) | `instructions.criteria`, `instructions.assess`, `instructions.compare` | [Assessment](../lab/improvement/assessment/README.md) |

Search scheduling, evidence page size and independent phase times belong to the
fixed [experiment configuration](../experiments/CONFIGURATION.md). They do not
become editable I components. Facts collection preserves raw observations for the shared model evaluator.

A tool's default guidance is derived from the registered tool; a separate guidance
file is needed only for an explicit value. To configure S, select its owner under
S and supply initial text. Each trial receives its declared frozen initial state.
Editing retained text does not imply automatic learning or trained weights.

## Preserve exact resources

Generated bundles may place an `artifacts` mapping in an owning component document.
It maps declared artifact slots to exact text. This preserves adopted instructions,
evaluator prompts and retained content without depending on the source artifact store.
The owner must declare and consume each slot; unknown slots fail. For an explicit
surface, the artifact and readable parameters must describe the same value.
Normal authoring should use parameters and let candidate/export code create these
exact bindings. Secret values never belong in either representation.

The editor's detached workspace may use internal `instructions.txt` files for
text or JSON payloads. Those files are generated by component adapters; they are
not additional authored configuration. [Experiment field grants](../experiments/CONFIGURATION.md#grant-component-changes)
map public component fields to the corresponding owner-validated payloads.

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
