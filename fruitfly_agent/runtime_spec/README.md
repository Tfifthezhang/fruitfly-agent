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
| `model_roles.py` | Strict alias/inheritance grammar and pure late binding |
| `profiles.py` | `HarnessProfile`, `HarnessConfig`, `load_harness_config`, `save_harness_config` |
| `components.py` | Serializable H/S/I instance envelopes and explicit references |
| `documents.py` | Strict YAML parsing, explicit references, bounded owner-resource reads and file/package receipts |
| `selections.py` | `MechanismSelection`; Catalog validates registered IDs and dependencies |
| `execution.py` | Validation, effective defaults, Core keyword projection and configuration bindings |
| `references.py` | One baseline path/profile; conflicting explicit references fail |

Run and Catalog use the same profile and selection types. Run's loader delegates
registered projection to Catalog; the pure specification loader constructs no
clients or artifacts. All system files use one H/S/I component format without a
version marker. There is one runtime assembler.

## Record host execution conditions

`execution.py` validates typed host values and projects Core defaults for assembly
and receipts. Execution limits and concurrency have no YAML component or
optimization surface. Programmatic hosts may supply conditions; ordinary config,
experiments and generated candidates all select registered H/S/I documents.
Invalid types, unknown fields and duplicate candidate JSON fields fail.

Model limits belong to the model catalog. Permissions are injected host
capabilities. Callbacks, live state and credentials cannot be supplied as execution
parameters. Effective runtime values remain part of recorded identity; historical
records retain their validated values. [Catalog](../lab/catalog/README.md) owns
mechanism availability and [Eval](../../fruitfly_eval/README.md) stages the same
component configuration.

Offline checks: `tests.run.test_runtime_spec`, `tests.eval.test_runtime`.

## Inventory declared package resources

[resources.py](resources.py) expands build-declared resource patterns with path,
secret-state and symlink checks. Run source snapshots and Eval installation
material share this inventory. Registered owner YAML joins hashing and copying;
frozen imports require those resources and never fall back to the checkout.
