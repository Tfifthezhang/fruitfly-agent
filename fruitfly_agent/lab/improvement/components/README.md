# Components

[Up: Improvement](../README.md)

Own legal candidate changes and executable publication bindings, independently
of editing, scoring and execution backends.

| Entry | Behavior |
|---|---|
| `registry.py` | Distinct ownership, complete snapshots, schema validation and nonconflicting exports |
| `text.py` | Reuse object-owned H/S/I instruction adapters and prompt/artifact bindings |
| `files.py` | Explicit multi-file component validation; no implied execution support |
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
