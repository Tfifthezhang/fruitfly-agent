# Host Adapters

[Up: Run](../README.md)

Translate public host and Lab results into Interactive contracts. Adapters receive
explicit queries and operations, not Factory internals or algorithm implementations.

| File / entry | Responsibility |
|---|---|
| [improvement.py](improvement.py): `RunImprovementService` | Workflow previews, execution, progress and persisted history |
| [improvement_results.py](improvement_results.py) | Completion, comparison, usage and evidence sections |
| [candidates.py](candidates.py) | Candidate review and isolated preparation |
| [task_packs.py](task_packs.py) | Task material views and corrections |
| [configuration.py](configuration.py) | Prompt labels using injected readers |
| [runtime.py](runtime.py) | Mechanism and tool descriptions |

RuntimeHandle receives improvement, candidate and task-material services through
independent fields. Task materials and candidate review remain available without
an improver. Method views carry registered descriptions, parameter metadata and
configuration locations. Adapters do not choose algorithms or acceptance policies.

Confirmed workflow submissions use Application's existing lifecycle. History
retains completed, failed, empty and cancelled work. Independent verification
remains an injected capability; ordinary search does not imply verification.
Benchmark execution is provided by the external [Eval CLI](../../../eval/README.md).

```bash
.venv/bin/python -m unittest tests.run.test_task_prompt_catalog tests.run.test_improvement_versions tests.workflows.test_improvement_activity -v
```

These checks use fake Providers and temporary state without container/model access.
