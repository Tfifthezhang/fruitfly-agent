# Host Adapters

[Up: Run](../README.md)

Translate public host and Lab results into Interactive contracts. Adapters receive necessary queries and operations, not Factory internals or algorithm implementations.

| File / entry | Responsibility |
|---|---|
| [improvement.py](improvement.py): `RunImprovementService` | Search preview, execution, and progress views |
| [candidates.py](candidates.py): `RunCandidateService` | Candidate review, reports, and preparation |
| [task_packs.py](task_packs.py): `RunTaskPackService` | Task material views and correction persistence |
| [configuration.py](configuration.py): `candidate_prompt_choices` | Prompt labels using injected record and text readers |
| [runtime.py](runtime.py): `describe_runtime` | Mechanism/tool descriptions for Interactive sessions |
| [evaluation.py](evaluation.py): `RunEvaluationController` | Optional benchmark task catalog and confirmed Application improvement dispatch |

RuntimeHandle receives these three adapters through independent fields. Task materials and candidate review remain available without enabling an improver.

Candidate review displays independent confirmation evidence when supplied by the generic search host. Ordinary search still reports that independent verification was not provided. The adapter does not select failure processors, scoring policies or adoption thresholds.

Configuration and runtime preparation use presentation callbacks instead of reading candidate storage or private state. Eval stays outside the production import graph. The bridge supports launching outside the checkout working directory.

Public [Run](../README.md) entries provide concrete bindings. Eval can incur model, network, container, and benchmark costs. The bridge passes the host environment to Eval, omits secrets from request JSON, and deletes temporary request files after completion or failure.

```bash
.venv/bin/python -m unittest tests.run.test_eval_bridge tests.run.test_task_prompt_catalog tests.run.test_improvement_versions tests.workflows.test_improvement_activity -v
```

Offline checks use blocked preflight and local fake processes.

The improvement bridge prepares bounded original task sets before running isolated official trials, using one attempt and concurrency one. Task material downloads have a 900-second process deadline and remain inside the whole improvement deadline. Fixed task selection and verifiers belong to [Eval](../../../eval/benchmarks/TASKS.md), outside the runtime import graph. Ordinary standalone evaluation retains its separate execution options.

[benchmark_trials.py](benchmark_trials.py) runs the optional single-task Eval subprocess through `BenchmarkTrialClient`, verifies owned evidence paths and content hashes, and reads actual invocation receipts. Deadlines/cancellation terminate the process group and drain both pipes. Raw stdout and decoded stderr stream through the same observation contract as task events; observer failures do not abort task work. It receives frozen execution capabilities and imports no Eval code. `RunImprovementService.register_benchmark` routes a one-use preview through the existing Application improvement lifecycle. See [Original task experiments](../../lab/improvement/experiments/README.md).
