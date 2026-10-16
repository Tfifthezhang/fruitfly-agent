# Improvement Trials

[Up: Improvement](../README.md)

Execute tasks against isolated candidate runtimes and return evidence to the optimization method.

| Entry | Responsibility |
|---|---|
| [__init__.py](__init__.py): `TrialExecutor`, `TrialOutcome` | Injected single-task execution and finite scored outcomes |
| `BatchObservation`, `BatchEvaluation` | Per-case evidence and aggregate results |
| [execution.py](execution.py): `PreparedTrial` | Fresh configuration, verifier and lifecycle callbacks |
| `IsolatedHarnessExecutor` | Start, execute, verify and close task-owned resources |

The preparer owns state reset, tools and resources. All model calls retain the supplied budgeted Provider/model; production Sessions are rejected. Cleanup runs after startup, execution or verification failure. Preparation must clean partial construction before raising.

This in-process boundary is not an OS sandbox. General generated workflow code and mutable external environments require an explicit executor. [Task policies](../tasks/README.md) define scoring; [Experiments](../experiments/README.md) adapt full original tasks. Neither may determine normal runtime interfaces.

No model calls occur during construction. Invoking a real executor may use models, tools or external environments. Default checks use fake capabilities.

```bash
.venv/bin/python -m unittest tests.lab.test_experiment_contracts tests.workflows.test_automatic_improvement tests.workflows.test_benchmark_improvement
```
