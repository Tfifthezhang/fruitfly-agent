# Improvement Runtime

[Up: Runtime architecture](../README.md)

Execute independent research stages through injected implementations. One activity
retains its inputs, configuration identity, intent and outputs; it never schedules
another stage or runs an automatic search loop. Scores are optional observations.

| Module | Responsibility |
|---|---|
| [Contracts](contracts/README.md) | Immutable inputs, candidates, receipts and research bundles |
| [Stages](stages/README.md) | Single-activity lifecycle, clocks, resources and recovery |
| [Execution](execution/README.md) | Batch scheduling, leaf execution and immutable facts |
| [Components](components/README.md) | General optimization registration and admission |
| [Evidence](evidence/README.md) | Receipts and reporting contracts |
| [Extensions](extensions/README.md) | Injected lifecycle observation and bounded context |

Concrete roles belong to [Lab](../lab/improvement/README.md). Configuration,
Providers and persistence belong to the [Run host](../run/improvement/README.md).
Benchmarks remain optional [external consumers](../../fruitfly_eval/improvement/README.md).
The runtime imports only Core, its own contracts and the standard library.

`api.py` exposes `ResearchController`, `StageInputs`, `ResearchProposalRequest`
and `StageServices`. Configuration changes do not invalidate retained input
artifacts. An unresolved external request requires reconciliation or explicit
retry; another stage may independently consume already retained outputs.

```bash
.venv/bin/python -m unittest tests.improvement.test_stage_contracts tests.improvement.test_research_recovery tests.improvement.test_stage_timing
```
