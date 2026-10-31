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
| [runtime.py](runtime.py) | Visible active component descriptions, registration-owned categories and tool names; separate experimental-mechanism IDs |

RuntimeHandle receives improvement, candidate and task-material services through
independent fields. Task materials and candidate review remain available without
an improver. Workflow views carry component choices, execution strategies and
parameter metadata. Adapters do not choose algorithms or acceptance policies.

Runtime descriptions cover visible assembled components, including capability-only
tools and execution environments. They honor each registration's configuration
category and exclude hidden internal components. The experimental ID collection
keeps its original scope. These read-only descriptions drive
[`/lab`](../../interactive/terminal/README.md#inspect-the-active-harness) without
giving the command access to Catalog or a configuration draft. General parameter
maps, credentials and algorithm objects do not enter this overview.

`describe_execution_environment` translates Catalog's installed
`ExecutionEnvironmentDescription` into `InteractiveExecutionEnvironment`. It
passes only label, directory and optional server, separately from the local
workspace. No concrete backend inspection, secret access or network query is
needed. An absent description remains absent; a malformed published view fails
preparation explicitly. Welcome, `/lab` and `/status` read the resulting active
status snapshot.

Confirmed workflow submissions use Application's existing lifecycle. History
retains completed, failed, empty and cancelled work. Independent verification
remains an injected capability; ordinary search does not imply verification.
Benchmark execution is provided by the external [Eval CLI](../../../fruitfly_eval/README.md).

```bash
.venv/bin/python -m unittest tests.run.test_task_prompt_catalog tests.run.test_improvement_versions tests.workflows.test_improvement_history -v
```

These checks use fake Providers and temporary state without container/model access.
