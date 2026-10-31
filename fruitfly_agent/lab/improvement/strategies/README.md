# Search Strategies

[Up: Improvement](../README.md)

Declare proposal missions, reference count, rounds and optional compositions.
The shared workflow owns evidence validation, execution, assessment, accounting
and stopping. Strategy discovery performs no model or task work.

| Entry | Behavior |
|---|---|
| `simple.py` | One reference, one generic proposal per round, no composition |
| [Harness²](harness2/README.md) | Invariant/domain proposals and evidence-based composition |
| `registry.py` | `SearchSchedule`, versioned `StrategyDefinition`, `StrategyRegistry` |

`builtin_strategies()` registers both. Hosts may supply `WorkflowBindings.strategies`.
Each schedule receives the frozen plan; mission names select declared editor
instructions. Other generators can consume the same requests without model editing.
Search cannot activate components. The experiment CLI defaults to `simple` and
no reflection; existing embedding `RunPlan` defaults retain Harness² and explicit
stored plans without a strategy field read as Harness².

I uses the same strategy interface inside fresh downstream episodes. Its independent
verification remains separate. Phase times and unknown-outcome rules belong to the
shared workflow, not individual strategy counters. Source replacement, arbitrary
graph search and model training are not implemented.

## Choose the next editing seed

`exploration.py` owns a separate `ExplorationRegistry`. Default `incumbent` follows
the officially selected result. Optional `process-guided` uses a comparison-capable
completed assessor to choose an existing completed execution worth investigating.
It makes no decision when another search round will not run.

The decision records the run ID, policy, reason and evidence IDs in the outcome
and journal. The next proposal uses that execution's harness while retaining all
prior evidence. Official measurement/selection and independent verification remain
separate. For example, with three zero-reward executions, the reported winner can
remain the baseline while the next candidate builds on a process-supported seed.
No process preference alone becomes a verified or adopted version.

Optional unavailable comparison retains the incumbent; required comparison ends
search. Fact counters alone do not define a generic quality ordering, so
`process-guided` requires a comparison-capable assessor. Extend through public
registry factories rather than controller branches or benchmark-specific rules.

```bash
.venv/bin/python -m unittest tests.lab.test_search_strategies tests.lab.test_improvement_pipeline
```
