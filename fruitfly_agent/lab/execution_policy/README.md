# Execution Policy Component

[Up: Lab](../README.md)

Expose declared scalar Core execution parameters as one H component. Runtime
configuration, candidate execution and publication share the
[runtime specification](../../runtime_spec/README.md). No Core loop is modified.

| Entry | Responsibility |
|---|---|
| `ExecutionPolicyTarget` in `__init__.py` | Snapshot effective values as JSON, validate changes and project isolated trials |
| `validate_component_options` | Pure validation of experiment field permissions and bounds |
| Catalog instruction registration | Declare component metadata and prepare the object-owned adapter |

The component ID is `execution-policy`, its schema is `execution-policy-v1`, and
its publication binding is `configuration / execution`. An execution backend must
declare `execution-config`. No arbitrary YAML file or Python callback is editable.

## Permit selected changes

Add the component explicitly in the experiment configuration:

```yaml
improvement:
  components: [base_prompt, execution-policy]
  component_options:
    execution-policy:
      editable_fields: [max_tool_calls_per_turn]
      bounds:
        max_tool_calls_per_turn: {minimum: 64, maximum: 512}
```

Without options, all declared fields are editable except fields owned by another
enabled mechanism. Nested fields use dotted names such as
`tool_execution.max_parallel`. Options for unselected, absent or unsupported
components fail. A fixed field cannot change, and every proposal must also satisfy
the base parameter schema. The initial value must fit the declared bounds.

Mechanisms declare `execution_fields` when they control scalar settings. Shared
fields cannot have competing mechanism owners. The policy does not edit these
fields or rewrite their controlling algorithms. Mechanism enablement, model
selection, permissions, experiment budgets and grading remain fixed.

Candidates are constructed in isolation. Run records full effective execution
settings in manifest schema 7 and H identity. Native trials also save
`runtime-execution.json`. Existing verification and activation guards still apply;
development selection does not grant persistent adoption.

## Verify offline

```bash
.venv/bin/python -m unittest tests.lab.test_harness_inventory tests.workflows.test_execution_policy tests.run.test_execution_limits
```

Synthetic verification tests demonstrate construction, isolation and H-only
activation. They establish no quality improvement or real model compatibility.
