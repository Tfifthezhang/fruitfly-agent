# Bind independent research stages

[Up: Improvement](../README.md)

This package binds one requested research activity to injected Lab services.
It does not schedule another activity, create a second Agent loop or automatically
execute missing prerequisites. Runtime timing, durable intent and recovery belong
to [Improvement stages](../../../improvement/stages/README.md).

## Select and validate an activity

`stage_definitions()` declares controls, input slots, role attribution and external
effects for configuration and discovery. `StageContext` supplies prepared services.
`builtin_stage_handlers(context)` binds handlers by stage and implementation ID.
`invoke_named` validates `StageInputs` and checks that the named resources exactly
match the declared activity grant before invoking a handler.

| File | Behavior |
|---|---|
| `registry.py` | Shared stage declarations, context and handler binding |
| `group.py` | Compose one frozen feedback batch |
| `organize.py` | Invoke the independent reading role on supplied records |
| `assess.py` | Assess supplied execution evidence |
| `propose.py` | Propose through the selected editor with explicit grants |
| `execute.py` | Invoke an injected executor and publish a research batch |
| `compare.py` | Compare supplied batches deterministically by default; model judgment is explicit |
| `context.py` | Project explicitly supplied readable stage context |
| `extensions.py` | Bind extension hooks through the existing runtime contracts |
| `control.py` | Declare execution controls independently of stage scheduling |

Import and fixed Eval are declared in the shared vocabulary but implemented by
the outer host/source adapters. They are not extra handlers in this package.
Execution rejects a missing executor. Measured comparison requires exactly two
batches with attributed plans and measurements, or an explicit pair policy; it
does not construct an assessor. Model comparison uses
the supplied assessor capability. Comparison does not activate a candidate.

## Supply evidence and continue

[Evidence](../evidence/README.md) owns paging, queries, source spans and supply
receipts. [Selection](../evidence_selection/README.md) owns material plans.
The Organizer is optional; Propose and Assess can consume retained batches
without automatically invoking it. Explicit inputs and stage settings determine
what each invocation can read or change.

Use the [developer guide](../DEVELOPER_GUIDE.md) for executable stage recipes,
output bundles and continuation. Offline checks:

```bash
.venv/bin/python -m unittest tests.experiments.test_stage_cli tests.lab.test_measured_comparison tests.lab.test_research_grouping tests.improvement.test_research_service
```

Fake Providers verify binding and rejection behavior, not model quality.
