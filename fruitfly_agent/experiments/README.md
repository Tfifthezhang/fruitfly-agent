# Experiments

[Up: Runtime architecture](../README.md)

Use fixed Eval and independent Improvement stages outside chat. One editable
research document describes historical inputs, current configuration and the next
operation. No Improvement command runs an automatic search or a multi-stage loop.

## Start a staged study

Copy the [research example](../../examples/experiments/research-stage.example.yaml)
and replace placeholder paths. System H/S/I and models retain their ordinary
configuration formats. Importing old records requires no prepared benchmark or
model credential.

```bash
fruitfly-agent-lab improvement show --config experiment.yaml
fruitfly-agent-lab improvement check --config experiment.yaml
# Executes only next.stage. Model/task phases may incur charges.
fruitfly-agent-lab improvement step --config experiment.yaml
```

Set `next.stage` to `import`, `organize`, `assess`, `propose`, `execute`, `compare`
or `eval`. Named inputs resolve explicit branch references; neither scores nor
a global latest output chooses the next operation. A stage never reruns a missing
prerequisite. Editing this file changes the next invocation without changing
historical configuration snapshots or previously exported candidates.

See [configuration](CONFIGURATION.md) and the detailed
[Improvement developer guide](../lab/improvement/DEVELOPER_GUIDE.md).

## Initialize system and benchmark inputs

```bash
fruitfly-agent-lab init
fruitfly-agent-lab --cwd /path/to/workspace init --source task-set --benchmark terminal-bench-4
```

Initialization performs no download, container start or model request. Configure
the shared models, secret environment and host before benchmark preparation.
Paths resolve from their declaring files; explicit missing files, unknown fields
and duplicate keys fail. Existing configs are never silently overwritten.
See [examples](../../examples/experiments/README.md) and
[remote setup](../../examples/experiments/TB4_SERVER.md).

## Keep fixed Eval independent

`eval catalog`, `prepare`, `check`, `run`, `list`, `report` and `stop` retain their
fixed-configuration responsibility. A research document with `next.stage: eval`
registers the result batch in the same study and stops there. Eval is optional:
removing it leaves generic research stages and injected task executors usable.
The composition entry wires adapters; Runtime and Lab never import Experiments.

Task-set preparation supports `eval prepare --tasks-only` followed by
`eval prepare`. Preparation may download/build/start containers; it does not
perform task model requests. Fixed execution requires an explicit request.

## Retain portable stage outputs

Every invocation retains `runs/<id>/configuration/`, inputs, outputs and reports.
Bundles retain immutable producer/configuration references and transitive
artifacts. Complete candidate exports use the normal Catalog materializer.
`references.json` resolves names inside the explicitly selected branch.
Generated `observed` content shows recent activity but never controls execution.

Advanced explicit input commands accept `--study`, `--output-root` and bundle paths.
The main research file supplies these values for normal use. `improvement inspect`
and `resume` inspect durable activity state; they do not replay external work.
Different configuration is reported, not used as a continuation gate.

## Files and offline checks

| File | Responsibility |
|---|---|
| `cli.py`, `menu.py` | Thin operation selection and argument parsing |
| `configuration.py`, `comparison.py` | Project common owner-validated configuration |
| `operations/step.py` | Bind the main file to one explicit stage |
| `operations/research.py` | Inject independent role/backend services and publish results |
| `operations/evaluate.py` | Optional fixed Eval adapter |
| `composition.py`, `validation.py` | Runtime/source construction and offline admission |
| `records.py` | Fixed Eval indexes and scoped stop |
| `scaffolding.py`, `templates/` | Private workspace templates |

```bash
.venv/bin/python -m unittest discover -s tests/experiments -t .
```

Offline tests use fake Providers and executors. They do not establish benchmark
quality or external connectivity. Generic materials require a registered executor;
a file instruction alone does not install a task runner.
