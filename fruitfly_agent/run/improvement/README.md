# Improvement Host

[Up: Run](../README.md)

Host optimization jobs and candidate operations through injected capabilities. Algorithms and the RSI state machine remain in Lab; Application owns runtime lifecycle.

| File / entry | Responsibility |
|---|---|
| [search_jobs.py](search_jobs.py): `RunSearchJobs` | Own preview receipts, freeze inputs, invoke generic optimizers, persist proposals |
| [candidates.py](candidates.py): `RunCandidates` | Scope, review, validate, prepare, and reconcile candidate adoption |
| [evolution.py](evolution.py): `RunEvolutionHost` | Durable jobs, independent verification, adoption, active-version checks |
| [startup_versions.py](startup_versions.py): `RunStartupVersions` | Opaque startup choices and temporary or remembered selections |

Services receive explicit storage interfaces, queries, configuration operations, and preparation callbacks. They do not receive a Factory or access another module's private fields. Search and startup services own their receipts. The Factory owns active bindings and invalidates search receipts on activation.

Saving a future default differs from switching the active runtime. Candidate and startup adoption use [activation hooks](../runtime/README.md) around isolated handles. Configuration is rechecked before commit. Partial saved intent is reconciled on later successful startup.

The optional [automatic workflow](../../lab/optimization/automatic/README.md) uses the existing job and candidate contracts. Lab owns failure processing and independent confirmation; Run stores the returned evidence and keeps adoption separate.

Evolution persists in `.fruitfly/evolution/` and requires an injected independent verifier. Unknown proposing/verifying work is not replayed. Interrupted activation is reconciled. One coordinator owns a job; no cross-process transaction. Real search and verification may incur model cost.

See [Lab Optimization](../../lab/optimization/README.md), [Lab RSI](../../lab/rsi/README.md), and [Storage](../storage/README.md). No module-specific environment variables.

```bash
.venv/bin/python -m unittest tests.run.test_host_services tests.workflows.test_optimization tests.workflows.test_evolution tests.workflows.test_decoupling -v
```

Standalone checks use fake capabilities without a Factory; workflow checks exercise real composition offline.

## Host original-task experiments

[experiments.py](experiments.py) hosts explicitly requested benchmark jobs through the optional executor capability. It freezes complete task references, separates training/selection/confirmation, reruns the baseline, invokes the Lab workflow and stores one confirmed proposal. [versions.py](versions.py) binds source-backed H, declared I and registered S snapshots. Candidate adoption rejects stale H/I/S and mismatched prepared execution versions. Source identities do not capture live Python heaps.

The Factory exposes `system_version()`, `benchmark_improvement_available`, `benchmark_task_preview(selection, executor, direction="")`. Direct task selection needs no prior evaluation. Pass the returned one-use token to the normal `Application.optimize` path. The direction is `Improve completion of the frozen original benchmark tasks.` Preview is offline; the selected task download and execution run under one Application job. Execution through Eval uses models, networks and containers. See [Original task experiments](../../lab/optimization/experiments/README.md) for requirements, limits and data locations.
