# Offline Extension Example

[Up: Examples](../README.md)

Register a context mechanism and use it through Run and Application without model access.

```bash
.venv/bin/python -m examples.extensions.offline_guidance
```

Expected output: `Offline response: example-guidance is active.` No catalog file, keys, Docker, or network needed. Configuration and Session files live in a temporary workspace and are removed on exit.

| Part of [offline_guidance.py](offline_guidance.py) | Responsibility |
|---|---|
| `ExampleGuidance.transform` | Add guidance to a request projection. |
| Installer | Return an `AssemblyState` with the context stage. |
| `example_definition()` | Declare identity, contribution, distinguishing description, and implementation/guide paths. |
| Extended Catalog / profile | Register and select the mechanism. |
| Factory / Application | Assemble, start, submit, and close. |
| Fixed Provider | Assert guidance reaches the request and return a fixed response. |

The mechanism needs no Core, Run, or terminal branch. Put real implementations in Lab or an extension package and inject their Catalog explicitly. Replacing the fixed Provider with a live adapter requires model configuration and may incur charges.

| Reference | Purpose |
|---|---|
| [Lab](../../fruitfly_agent/lab/README.md#develop-an-algorithm) | Extension points and requirements |
| [Catalog](../../fruitfly_agent/lab/catalog/README.md) | Parameters, ownership, and identity |
| [Run](../../fruitfly_agent/run/README.md) | Assembly and recovery |

```bash
.venv/bin/python -m unittest tests.workflows.test_offline_example -v
```

This verifies integration, not model compliance or algorithm gains.

## Load an optimizable developer extension

`developer_guidance.py` exports `register(api)` for the
[developer SDK](../../fruitfly_agent/extensions/README.md). It registers
`developer-guidance-owner` and an H text surface named `developer-guidance`.
Enable the owner through ordinary component configuration, then grant
`developer-guidance.parameters.instructions.usage` through the existing experiment edit map.
Its artifact-backed candidate uses the same installation path on activation.
The offline integration test executes real Agent requests with a fake Provider,
compares candidate guidance, activates two generations and checks the final prompt.
Synthetic verification establishes binding, not model quality.

```bash
.venv/bin/python -m fruitfly_agent --extension examples/extensions/developer_guidance.py --help
.venv/bin/python -m unittest tests.workflows.test_developer_extensions
```

`--help` loads no code and requests no model. Actual Agent commands require a
configured Provider and may incur cost. Source declarations in the system profile
also work in native experiments. Container source staging is unsupported.
