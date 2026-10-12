# Host Adapters

[Up: Run](../README.md)

Translate public host and Lab results into Interactive contracts. Adapters receive necessary queries and operations, not Factory internals or algorithm implementations.

| File / entry | Responsibility |
|---|---|
| [optimization.py](optimization.py): `RunOptimizationService` | Search preview, execution, and progress views |
| [candidates.py](candidates.py): `RunCandidateService` | Candidate review, reports, and preparation |
| [task_packs.py](task_packs.py): `RunTaskPackService` | Task material views and correction persistence |
| [configuration.py](configuration.py): `candidate_prompt_choices` | Prompt labels using injected record and text readers |
| [runtime.py](runtime.py): `describe_runtime` | Mechanism/tool descriptions for Interactive sessions |
| [evaluation.py](evaluation.py): `RunEvaluationController` | Optional Eval subprocess bridge with explicit host context |

RuntimeHandle receives these three adapters through independent fields. Task materials and candidate review remain available without enabling an optimizer.

Configuration and runtime preparation use presentation callbacks instead of reading candidate storage or private state. Eval stays outside the production import graph. The bridge supports launching outside the checkout working directory.

Public [Run](../README.md) entries provide concrete bindings. Eval can incur model, network, container, and benchmark costs. The bridge passes the host environment to Eval, omits secrets from request JSON, and deletes temporary request files after completion or failure.

```bash
.venv/bin/python -m unittest tests.run.test_eval_bridge tests.run.test_task_prompt_catalog tests.run.test_optimization_versions tests.workflows.test_optimization_activity -v
```

Offline checks use blocked preflight and local fake processes.
