# Execution Definitions

[Up: Improvement](../README.md)

Select execution through registration metadata. Run consumes this public capability;
frontends receive plain views and do not import a runner implementation.

## Register an execution definition

`ExecutionRegistry.register(ExecutionDefinition(...))` registers an ID, label,
implementation identity, supported H/S/I roles, capabilities, material discovery,
preparation, construction, parameter declarations and cost notice. Discovery reads
metadata/materials without constructing Providers or starting model work.

| Entry | Responsibility |
|---|---|
| [__init__.py](__init__.py): `ExecutionRegistry` | Explicit registration and lookup; duplicate IDs fail |
| `ExecutionContext` | Borrowed task/model/component/artifact capabilities; no Application or Factory |
| [files.py](files.py) | Native file materials and optional task-package verification |
| [Experiment contracts](../contracts/experiments.py) | Requests, parameter declarations, prepared material and stage ports |
| [Editor experiments](../improver/README.md) | Registered fixed-depth I comparison |

Preparation validates the exact component scope, typed parameters, source hashes
and minimum allocation. `PreparedExecution` keeps private material out of editor
requests. Its source query is checked again before execution. File inputs are
frozen bytes; task packages and experiment sources must still match their preview.

Construction returns `ExecutionPorts`: a runner, optional measurement/verifier/
selector, protected verification allocation, and whether pending experience may be
retained. Factories register owned resources with job services immediately.
Borrowed ports remain caller-owned. Extensions must clean up partial construction.

## Preserve existing embeddings

`WorkflowBindings.runner`, stage factories and injected verifier/measurements remain
supported. `WorkflowBindings.executions` can replace the execution registry;
`stop_policy` replaces only stop decisions. Native `file-task` remains the default.
Definitions opt in to the legacy runner override with `accepts_runner_override`;
its capabilities cannot replace those of unrelated execution definitions.
An unknown execution ID, unknown parameter, incompatible component, missing scorer
or insufficient verification allocation fails before model work.

The default file environment supplies isolated in-memory read/write/edit files.
It does not inherit Bash, SSH, network tools, live Session or production files.
Its declaration supports H/S only. External environments require a registered
runner with truthful capabilities, state isolation and attributable receipts.
Registration is not an OS sandbox or permission to deploy code.

## Check offline

```bash
.venv/bin/python -m unittest tests.lab.test_improver tests.workflows.test_improvement_pipeline tests.architecture.test_boundaries
```

No secrets or environment variables are introduced. Real execution calls the
configured models and may incur charges.
