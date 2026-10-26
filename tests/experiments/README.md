# Experiment Tests

[Up: Tests](../README.md)

Validate file defaults, model roles, independent entry commands and owned lifecycle
without network, real models, downloads or Docker.

| File | Coverage |
|---|---|
| `test_scaffolding.py` | Fresh native initialization/check, optional benchmark templates, collision and partial-write handling, private-file preservation and public template consistency |
| `test_harness_validation.py` | Provider-free component scope checks, state availability and execution field options |
| `test_component_configuration.py` | Shared H/S/I assembly, explicit grants, transitive source guards, offline inspection and explicit export |
| `test_configuration.py` | Strict fields, path origins, overrides, missing material and Provider-free checks |
| `test_operations.py` | Actual Application trials, separate model bindings, verified RSI adoption and no replay |
| `test_lifecycle.py` | Menu selection, locked owner, scoped stop and stale records |
| `test_benchmark.py` | Derived host, task-only preparation and fixed-version Eval separation |
| `test_multi_task.py` | Application task-set search, complete leaf evidence, shared selection, explicit budgets and unchanged defaults |
| `test_process_configuration.py` | Completed-assessment/exploration defaults and validation, real composition with fake models, separate official/seed reports |

```bash
.venv/bin/python -m unittest discover -s tests/experiments -t .
```

Shared temporary inputs belong to `tests/support/experiments.py`. Synthetic quality
and fake replies establish orchestration behavior only.
