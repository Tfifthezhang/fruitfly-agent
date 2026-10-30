# Developer Extensions

[Up: Runtime Architecture](../README.md)

Register algorithms, events, search mechanisms and commands through `ExtensionAPI`.
The SDK composes existing public Catalog, Core, Improvement and Interactive
contracts. It owns no model loop or separate algorithm registry.

## Write an extension

A local Python file exports synchronous `register(api)` and returns `None`.
Registration declares capabilities; it does not start resources or call models.
Use [the executable guidance example](../../examples/extensions/README.md) for an
algorithm whose instructions support isolated trials and persistent activation.

| API | Owning contract |
|---|---|
| `register_mechanism(definition)` | Catalog definition, strict configuration, installer and optimization targets |
| `register_generator(id, factory, **metadata)` | Per-job generator registry |
| `register_strategy(definition)` | Search strategy registry; kernel validates schedule bounds |
| `observe_agent(event, handler, timeout=10)` | Private Core event snapshots, bounded optional callbacks |
| `intercept_agent(event, handler, required=True, timeout=10)` | Active Core handlers; required failures block the operation |
| `observe_improvement(event, handler)` | Job-local immutable Improvement events and stage deadlines |
| `register_command(name, handler, summary='')` | Interactive command/result contract and ordinary terminal rendering |

Event handlers receive `(event, context)`. `ExtensionContext.state` is local to
one runtime or Improvement job. `record` and `own` are injected capabilities;
unavailable capabilities fail explicitly. A retired context rejects later API
operations. The host closes owned resources and creates fresh contexts for
replacement runtimes and nested jobs. Persistent learning content must use an
explicit S owner; the context dictionary is not a durable learning snapshot.
Commands receive the ordinary `InteractiveCommand` and return `CommandResult`,
including frontend-neutral panels where appropriate. Direct terminal access and
a second input reader are not supplied by the SDK.

## Load and replace

Declare explicit sources in [the system profile](../runtime_spec/COMPONENTS.md)
or pass `--extension PATH` / `--extension entrypoint:NAME` for one invocation.
[Run extension hosting](../run/extensions/README.md) owns discovery and loading.
`ExtensionSet.catalog` and `.bindings` feed the same registration paths used by
ordinary runtime, isolated candidates and nested Improvement jobs. Duplicate
contributions fail. Registration is closed after loading.

When extensions are loaded, `/extensions` shows identities and `/reload` constructs
and activates a replacement while idle, retaining conversation history. Remove profile sources and their dependent component selections to disable
their contributions on reload. Unknown remaining selections are rejected. Failed construction or
command conflicts retain the incumbent. Old commands are replaced as one owner
group; obsolete command names are removed. `AgentApplication.replace_factory`
is the generic host-replacement operation.

Local source hashes join the harness inventory and H identity. Changed source
blocks new assembly until explicit reload. Installed entry points use distribution
name/version and declared entry identity; this is not a complete source snapshot.
In-process Python has host permissions and must cooperate with cancellation.
Module import effects cannot be rolled back. Whole-package source freezing,
remote package installation and hard process isolation are not implemented.

```bash
.venv/bin/python -m unittest tests.workflows.test_developer_extensions tests.core.test_operation_supervision
```

## Preserve trial behavior

Agent observers and interceptors are recreated through `ComponentRegistry.trial_setups`
for each native execution. Setup resources own their fresh contexts and are closed
at the trial boundary, including failure and cancellation. Live hook registries,
Session writers and mutable context state are never copied into trials. Runners
must declare `execution-setup`; an unsupported custom runner rejects the declared
setup before execution. Nested native editor episodes use the same registry path.
