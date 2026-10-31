# Declarative Runtime Specification

[Up: Runtime Architecture](../README.md)

Share serializable harness selections across Run, Lab and Eval. This module
depends only on Core and basic serialization libraries. Core does not depend on
it. It constructs no Providers, tools, Sessions or external resources.

## Read the configuration guides

Start with [configuration responsibilities](../../CONFIGURATION.md). The guide tree is:

- [Component documents](COMPONENTS.md): write H/S/I files and model-role references.
- [Runtime configuration](../run/configuration/README.md): load, save and assemble a selected system.
- [Catalog](../lab/catalog/README.md): declare component parameters and capabilities.
- [Experiments](../experiments/README.md): grant edits and compare frozen candidates.

| File | Public entry points and responsibility |
|---|---|
| `profiles.py` | `HarnessProfile`, `HarnessConfig`, `load_harness_config`, `save_harness_config` |
| `components.py` | Serializable H/S/I instance envelopes and explicit references |
| `documents.py` | Strict duplicate-key rejection, relative references and source hashes |
| `selections.py` | `MechanismSelection`; Catalog validates registered IDs and dependencies |
| `execution.py` | Validation, effective defaults, Core keyword projection and configuration bindings |
| `references.py` | One baseline path/profile; conflicting explicit references fail |

Run and Catalog use the same profile and selection types. Run's loader delegates
registered projection to Catalog; the pure specification loader constructs no
clients or artifacts. All system files use one H/S/I component format without a
version marker. There is one runtime assembler.

## Configure execution

```yaml
id: execution-policy
role: H
implementation: execution-policy
parameters:
  max_tool_calls_per_turn: 256
  max_turns: 32
  max_context_recovery_attempts: 6
  tool_execution:
    max_parallel: 8
    default_execution_mode: parallel
```

Defaults come from the existing Core dataclasses. Turn/tool limits accept
nonnegative integers; recovery attempts and parallelism require positive integers.
The tool mode is `parallel` or `sequential`. Unknown fields, booleans, fractional
limits and duplicate JSON candidate fields fail. Configured values and effective
values remain distinct; configuration does not replace recorded execution facts.

Models and token limits stay in the model catalog. Prompt and mechanism bindings
retain their own owners. Callbacks, permission objects, credentials and live state
cannot be supplied as execution options. Model-call and wall-clock experiment
allowances remain independent fixed comparison conditions.

Run assembles the configuration and [Catalog](../lab/catalog/README.md) checks
component availability. [Execution policy](../lab/execution_policy/README.md)
provides the optional H editing adapter. [Eval](../../fruitfly_eval/README.md) uses the same
profile parser before staging a selected runtime.

```bash
.venv/bin/python -m unittest tests.run.test_runtime_spec tests.eval.test_runtime
```

These checks use temporary files and fake Providers; they make no model requests.
