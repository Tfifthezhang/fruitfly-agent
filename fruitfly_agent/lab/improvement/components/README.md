# Components

[Up: Improvement](../README.md)

Own legal candidate changes and executable publication bindings, independently
of editing, scoring and execution backends.

| Entry | Behavior |
|---|---|
| [Runtime registry](../../../improvement/components/README.md) | Distinct ownership, complete snapshots, schema validation and nonconflicting exports |
| `text.py` | Reuse object-owned H/S/I instruction adapters and prompt/artifact bindings |
| `files.py` | Explicit multi-file component validation; no implied execution support |
| `parameters.py` | Owner-declared mechanism parameter grants and shared configuration materialization |
| `changes.py` | Add/replace/remove UTF-8 files with parent/content preconditions |

`ChangeSet` consumes immutable artifacts and returns a new document. It does not
write production files, compile code or grant activation. `CandidateBuilder`,
`CandidateRuntime` and `ActivationHost` contracts allow embeddings to declare
construction and activation for other component kinds. A file registration alone
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

`ComponentRegistry.configure` validates component-owned `component_options` and
enforces them again on each candidate. `RunPlan` freezes these options into
comparison conditions. The editor receives only the declared writable component
IDs; other registered baseline components must remain unchanged.

Bindings include `prompt`, `artifact` and `configuration`. Configuration bindings
name a supported declarative section; they cannot write arbitrary profile fields.
[Execution policy](../../execution_policy/README.md) uses `configuration / execution`
for isolated trials, Eval staging, H version identity and verified activation.


## Edit owner parameters

`editable_parameters` wraps an owning Catalog definition with an explicit field
whitelist, strict complete JSON snapshot, numeric bounds and a configuration
binding. Bash, compaction, Web search/fetch and IPython declare supported parameter
fields. Credentials, model roles and undeclared fields remain fixed. Grants use
`parameters.<field>`; enabling an owner does not authorize editing it.

Changed values require `configuration-materialization`, supplied by Eval staging.
The native file runner rejects these edits before model work. Candidate staging,
ordinary assembly and verified activation consume the same component configuration.
Unsupported backends fail explicitly. See [Catalog admission](../../catalog/CONFIGURATION.md).


Web parameter adapters do not remove the live-service snapshot requirement.
The ordinary Run host rejects an experiment when a selected live dependency has
no frozen response source. Such a component needs an explicitly supplied
reproducible service/backend before an end-to-end comparison can run; a visible
adapter alone is not runnable support. Catalog reports backend capabilities
separately from grants. Existing external-dependency guards remain enforced.
