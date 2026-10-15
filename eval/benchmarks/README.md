# Benchmark Adapters

[Up: Eval](../README.md)

Describe datasets, resources, preflight, Harbor jobs, and official results. Adapters do not own Agent runtime behavior or task verifiers.

| File | Responsibility |
|---|---|
| [base.py](base.py) | Descriptor and adapter protocol |
| [harbor.py](harbor.py) | Shared runner, progress, logs, and result parsing |
| [terminal_bench.py](terminal_bench.py) | Terminal-Bench 2.0 identity, fixed smoke and five-task starter |
| [swe_bench.py](swe_bench.py) | SWE-bench Verified identity and smoke task |
| [Public tasks](TASKS.md) | Task formats, selected exercises, resources, and interactive execution |

The installed-agent bridge reports project version `0.1`, matching package metadata.

`BenchmarkVariant.task_names` optionally declares a fixed subset of distinct exact registry names. Empty keeps ordinary smoke/full behavior. Selected subsets use exact Harbor filters and a task cap; returned task and attempt counts must match. The catalog includes declared names for inspection. Request/report schema versions remain 2; the new selector is an additional variant, not an experiment format.

Harbor result parsing separates official reward selection, trial status, and aggregate metric formatting. Runner exceptions determine error status; available actual runtime manifests are retained in task records. Error trials contribute no reward, while available usage, cost, and latency remain reportable. Missing measurements remain unknown; a single numeric reward with another name is accepted when no numeric `reward` field is available.

| Contract | Requirement |
|---|---|
| Identity | Unique benchmark ID, dataset/version, adapter version, and exact smoke task |
| Resources | Explicit variants, network surfaces, timeout, and backend constraints |
| Results | Official rewards, missing data, errors, and actual runtime metadata |
| Progress | Job/Agent/trial events; no precise image preparation percentage |
| Installation | Existing Python/venv preferred; bounded fallback setup with preserved logs |
| Retries | Connection-only, before job creation; bounded attempts with all logs retained |

Register in [Catalog](../catalog.py). Full setup, diagnostics, and extension procedures belong to [Evaluation guide](../DEVELOPER_GUIDE.md). `FRUITFLY_EVAL_PACKAGE` selects explicit source or wheel installation material; see [Eval](../README.md#select-installation-material). Offline tests need no Docker; real jobs need the optional Harbor installation, Docker/Compose, registries, and model access.

```bash
.venv/bin/python -m unittest tests.eval.test_catalog tests.eval.test_harbor -v
```
