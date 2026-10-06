# Evaluation Studies

[Up: Eval](../README.md)

Turn a request into fixed comparison conditions. Studies do not own benchmarks, Providers, or scoring.

| File | Conditions |
|---|---|
| [base.py](base.py) | `EvaluationStudy.conditions(request)` contract |
| [current_setup.py](current_setup.py) | Full active configuration |
| [mechanism_comparison.py](mechanism_comparison.py) | Baseline disables one enabled non-capability mechanism; candidate keeps it. |

Comparison rejects a mechanism required by another enabled component. It reads public manifest contributions and dependencies, without importing Run or repeating assembly. Invalid selections raise `ValueError` before execution.

Register studies through Eval's catalog/planning path. Keep task, model, budgets, and scoring fixed except for the declared variable. No module-specific environment variables.

```bash
.venv/bin/python -m unittest tests.eval.test_planning -v
```
