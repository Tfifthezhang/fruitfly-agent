# Improvement Methods

[Up: Improvement](../README.md)

Keep optimization decisions in method packages. Share target validation, trials, budgets, evidence and host lifecycle through the parent framework.

## Declare a method

| Description | Contract |
|---|---|
| System position | Existing Catalog `MechanismContribution(layer, family)`; methods declare `improvement` |
| Modification scope | `MethodDefinition.roles`, `schemas`, and a registered concrete target |
| Execution | A method's search contract and required injected capabilities |

[__init__.py](__init__.py) defines `MethodDefinition`. Attach it to `MechanismDefinition.improvement`. `MethodUsage` states triggering, materials, feedback, candidate generation, acceptance and activation; the shared preview presents these fields. `bind(binding)` constructs a host for one job without starting research. Native text methods use `binding.text_host(strategy, label=...)`. [Runtime selection](../runtime/README.md) checks support and creates the chosen host on demand. No configuration switch is required. The optional `prepare_targets(state, context)` callback registers lightweight targets and consumes declared artifacts without allocating a search strategy or model client. Confirmed job preferences are independent of parent I identity.

A method may support multiple roles or formats, but each executable combination needs target, trial, comparison and adoption capabilities. Support declarations do not install those capabilities. Existing embedding hosts without metadata can continue using their configured text host.

## Keep decisions with their method

Generating practice tasks is choosing trial inputs. Reflection is computation over evidence. Patch merging and bounded edits produce candidate changes. Archives and rejected edits are method state. These are not mandatory framework stages or additional global classification axes. Extract a component only when real consumers need to replace or share it.

Methods may use optional controllers to organize repeated trials. Fixed comparison tasks and confirmation answers remain outside material-generation authority. Keep initial state, reset/update rules, budgets, cancellation and recovery behavior explicit.

| Installed method | Scope |
|---|---|
| [OPRO](opro/README.md) | H text targets; scored-history proposal generation and bounded search |
| [Tree search](tree_search/README.md) | H text discovery with recorded branches and a replaceable I policy |
| [DreamRSI](dream_rsi/README.md) | I policy refinement through replay, paired search and independent holdout confirmation |

Workflow-code generation, Skill-body optimization and arbitrary optimizer code replacement remain unsupported. DreamRSI changes a bounded declarative policy artifact, not Python source. No placeholder method is advertised in the interaction menu.

Each method package owns its definition, implementation and research attribution. See [Extend search](../README.md#extend-search). Methods use injected dependencies and no shared secrets or environment variables. Listing a method does not call a model; running it may incur the effects declared by its definition.

```bash
.venv/bin/python -m unittest tests.lab.test_search tests.lab.test_improvement_selection tests.workflows.test_improvement_methods
```
