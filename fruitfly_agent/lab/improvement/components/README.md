# Components

[Up: Improvement](../README.md)

Own legal candidate changes and executable publication bindings, independently
of editing, scoring and execution backends.

| Entry | Behavior |
|---|---|
| [Runtime registry](../../../improvement/components/README.md) | Distinct ownership, complete snapshots, schema validation and nonconflicting exports |
| `text.py` | One typed `parameters.yaml` view over object-owned H/S/I execution codecs |
| `files.py` | Explicit multi-file component validation; no implied execution support |
| [Catalog parameter adapter](../../catalog/adapters/parameters.py) | Owner-declared mechanism parameter grants and shared configuration materialization |
| `changes.py` | Add/replace/remove UTF-8 files with parent/content preconditions |

`ChangeSet` consumes immutable artifacts and returns a new document. It does not
write production files, compile code or grant activation. Construction and activation remain explicit host capabilities.
`FileComponentAdapter` requires an owner-supplied `OptimizationSpec`; registration
does not imply a construction or deployment backend. A file registration alone
cannot make source code runnable or publishable. Unsupported exports fail before
external execution. The registry cannot silently change component ownership.

H/S text owners and I editor instructions retain their existing activation paths.
I comparisons require a runner supporting downstream improvement, not an ordinary
task score. Mixed changes require the runner's actual capabilities.

```bash
.venv/bin/python -m unittest tests.lab.test_evolution_policies tests.workflows.test_editor_evolution tests.workflows.test_decoupling
```

## Match edit scope to the configured harness

[Catalog](../../catalog/README.md#resolve-one-harness-inventory) declares available
H/S/I components from active owners. Execution capabilities and experiment
permission further restrict them. Inactive state owners do not create S targets.
A selected component unsupported by any task collection fails before execution.
Tool parameters remain available for explicit grants but are excluded from
automatic edit scope. Native tool descriptions share their owner targets and require explicit selection.

`ComponentRegistry.configure` validates component-owned `component_options` and
enforces them again on each candidate. `RunPlan` freezes these options into
comparison conditions. The editor receives only the declared writable component
IDs; other registered baseline components must remain unchanged.

Bindings include `prompt`, `artifact` and `configuration`. Configuration bindings
name a supported declarative section; they cannot write arbitrary profile fields.
Host execution conditions remain fixed and recorded; they have no candidate binding.


## Edit owner parameters

`editable_parameters` wraps an owning Catalog definition with an explicit field
whitelist, strict complete typed parameter snapshot, numeric bounds and a configuration
binding. Bash, layered compaction, working memory, Web search/fetch and IPython declare supported parameter
fields. Credentials, model roles and undeclared fields remain fixed. Grants use
`parameters.<category>.<field>`; enabling an owner does not authorize editing it.

Changed values require a registered backend with `configuration-materialization`.
Tool/Skill catalogs and reduction methods use their ordinary owner installers; Bash,
Web and IPython also need their actual tool/backend capabilities. Tool parameters are explicit opt-in targets. Candidate staging,
ordinary assembly and verified activation consume the same component configuration.
Unsupported backends fail explicitly. See [Catalog admission](../../catalog/CONFIGURATION.md).


Web parameter adapters do not remove the live-service snapshot requirement.
The ordinary Run host rejects an experiment when a selected live dependency has
no frozen response source. Such a component needs an explicitly supplied
reproducible service/backend before an end-to-end comparison can run; a visible
adapter alone is not runnable support. Catalog reports backend capabilities
separately from grants. Existing external-dependency guards remain enforced.

Owners may pass `available_fields` to `editable_parameters` to restrict the
whitelist using normalized active parameters. Discovery validation and the
installed target enforce the same subset. Layered compaction uses this to reject
summary grants in deterministic mode while preserving complete protected
configuration in candidate snapshots.

## Edit typed candidate files

The shared adapter exposes one `parameters.yaml` per component. It contains the
protected ID, implementation and H/S/I role plus typed parameter values. Text,
integer, number and choice edits share owner validation and grant enforcement.
A candidate cannot change role, model bindings, activation metadata or protected
fields. Owner codecs translate the document into the existing execution binding;
no second prompt or numeric publication pipeline is created.

Default definitions remain in Lab. Editors write isolated candidate workspaces.
Validated content enters immutable artifacts; adoption changes the selected
version after independent verification. Source defaults are not edited by trials.
