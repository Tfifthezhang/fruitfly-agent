# Improvement Methods

[Up: Improvement](../README.md)

Keep optimization decisions in method packages. Share target validation, trials, budgets, evidence and host lifecycle through the parent framework.

## Declare a method

| Description | Contract |
|---|---|
| System position | Existing Catalog `MechanismContribution(layer, family)`; methods declare `improvement` |
| Modification scope | `MethodDefinition.roles`, `schemas`, and a registered concrete target |
| Execution | A method's search contract and required injected capabilities |

[__init__.py](__init__.py) defines `MethodDefinition`. Attach it to `MechanismDefinition.improvement`. Methods declare `budget_parameters` and `material_parameters` by name so frontends place fields under Budget and Task. Target shows the registration-owned description and implementation/guide paths. Other tuning fields remain in YAML or programmatic previews; the frontend recognizes no concrete algorithm fields. Discovery exposes current defaults, required materials and supported task sources. `MethodUsage` states triggering, materials, feedback, candidate generation, acceptance and activation; the shared preview presents these fields. `bind(binding)` constructs a host for one job without starting research. Native text methods use `binding.text_host(strategy, label=...)`. [Runtime selection](../runtime/README.md) checks support and creates the chosen host on demand. No configuration switch is required. The optional `prepare_targets(state, context)` callback registers lightweight targets and consumes declared artifacts without allocating a search strategy or model client. Confirmed job preferences are independent of parent I identity.

A method may support multiple roles or formats, but each executable combination needs target, trial, comparison and adoption capabilities. Support declarations do not install those capabilities. Existing embedding hosts without metadata can continue using their configured text host.

Declare `direction_help` only when the frontend should expose optional natural-language search guidance. An empty declaration exposes evaluation/acceptance information instead. This field does not define the scoring objective. Task policies and method-owned comparison rules remain authoritative. Parameter descriptors supply descriptions, types, choices and bounds for visible material and budget inputs. Internal tuning and JSON overrides are absent from the terminal. Discovery returns only methods compatible with the target role/schema; missing runtime capabilities produce unavailable matching options.

## Keep decisions with their method

Generating practice tasks is choosing trial inputs. Reflection is computation over evidence. Patch merging and bounded edits produce candidate changes. Archives and rejected edits are method state. These are not mandatory framework stages or additional global classification axes. Extract a component only when real consumers need to replace or share it.

Methods may use optional controllers to organize repeated trials. Fixed comparison tasks and confirmation answers remain outside material-generation authority. Keep initial state, reset/update rules, budgets, cancellation and recovery behavior explicit.

| Installed method | Scope |
|---|---|
| [OPRO](opro/README.md) | H text targets; scored-history proposal generation and bounded search |
| [Tree search](tree_search/README.md) | H text discovery with recorded branches and a replaceable I policy |
| [DreamRSI](dream_rsi/README.md) | I policy refinement through replay, paired search and independent holdout confirmation |
| [Workflow search](workflow_search/README.md) | H sequential workflow design, reflection, repair and measured design archive |
| [Skill document optimization](skill_edit/README.md) | S Skill-body editing with bounded changes, minibatch feedback and validation gates |
| [Exploratory memory learning](memory_exploration/README.md) | S memory consolidation from broad then focused authorized practice |

The three workflow/document methods require enabled object targets and independent holdout. Their shared host confirms one selection winner and stops on any independent per-case regression. [evidence.py](evidence.py) projects training receipts without selection feedback. Workflow-code generation, general multi-file Skill editing and arbitrary optimizer code replacement remain unsupported. DreamRSI changes a bounded declarative policy artifact, not Python source. No placeholder method is advertised in the interaction menu.

Each method package owns its definition, implementation and research attribution. See [Extend search](../README.md#extend-search). Methods use injected dependencies and no shared secrets or environment variables. Listing a method does not call a model; running it may incur the effects declared by its definition.

```bash
.venv/bin/python -m unittest tests.lab.test_search tests.lab.test_improvement_selection tests.workflows.test_improvement_methods
```
