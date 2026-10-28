# Execution Workflows

[Up: Lab](../README.md)

Execute bounded sequences of model stages through Core's existing follow-up callback. Workflow definitions are H artifacts; searching them belongs to the [component workflow](../improvement/README.md).

## Enable a workflow

Select an H component with ID/implementation `execution-workflow` and configure
`parameters.steps`. Its default is one solve-and-answer step. An experiment grant
with `fields: [parameters.steps]` permits alternatives. Construction and discovery
make no model calls. See the [component format](../../runtime_spec/COMPONENTS.md).

```yaml
id: execution-workflow
role: H
implementation: execution-workflow
parameters:
  steps: [Solve the user task., Check the reasoning and return only the final answer.]
```

The immutable target artifact uses JSON with the same `steps` array.

| Contract | Behavior |
|---|---|
| `parse_workflow(text)` | Exactly one `steps` array; 1–6 nonempty strings, at most 2000 characters each |
| `apply_workflow(config, text)` | First instruction in an owned system block; remaining instructions as follow-up messages |
| `WorkflowTarget` | `execution-workflow`, H, schema `execution-workflow-v1` |
| Production execution | Fresh stage count for each user run; normal tools, permissions and cancellation remain active |
| Native trials | Fresh Core loop with isolated read/write/edit files; every stage uses the root budgeted Provider; only the final answer is scored |
| Adoption | Exact immutable artifact loaded into a new session; H changes, I and S remain fixed |

An existing follow-up controller is a construction conflict. The configured turn limit must cover every step. Definitions contain instructions, not executable Python, conditions, parallel branches or model allocations. Model execution is stochastic; stage labels do not prove independent verification. Recovery reloads the artifact and normal conversation; interrupted model work is not automatically replayed. Calls may incur charges.

The module's [public entry](__init__.py) owns validation, execution, target and registration. No module-specific environment variables.

```bash
.venv/bin/python -m unittest tests.lab.test_retained_targets tests.workflows.test_improvement_pipeline
```
