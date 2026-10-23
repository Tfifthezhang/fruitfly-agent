# Benchmark Adapters

[Up: Eval](../README.md)

Declare task sets and consume official benchmark results. Agent execution remains
native; Harbor owns task environments and verification.

| File | Responsibility |
|---|---|
| [base.py](base.py) | Runner protocol, descriptors, exact task subsets and GPU preflight metadata |
| [harbor.py](harbor.py) | Shared preflight, commands, result coverage and Harbor job dispatch |
| [terminal_bench.py](terminal_bench.py) | Terminal-Bench 2.1 dataset and smoke/starter tasks |
| [terminal_bench_4.py](terminal_bench_4.py) | Terminal-Bench 4.0.0 pinned dataset and CPU smoke task |
| [swe_bench.py](swe_bench.py) | SWE-bench Verified dataset and smoke task |
| [TASKS.md](TASKS.md) | Official task format and selection |

## Add a Harbor dataset

Subclass `HarborBenchmarkAdapter` and set `descriptor = harbor_descriptor(...)`.
Supply benchmark ID, label, description, version, dataset and exact smoke task.
Optional `BenchmarkVariant` subsets supply distinct exact task names. The common
declaration supplies measurement names, network surfaces, isolation and full-run
variants. A variant's `requires_gpu` controls resource preflight without matching
its name. New datasets require no changes to installation, native CLI startup,
credentials, trajectories, subprocess handling or result parsing.
Use `org/dataset@version` to pin a Hub dataset revision. Resolution passes the
name and version through Harbor's public dataset configuration. Shared versus
separate verification and step overrides come from the task, not the benchmark ID.

Preparation freezes exact task paths before Harbor starts. Returned names and
attempt counts must match the frozen set for every variant, including full runs;
missing, unexpected or duplicated attempts fail validation. Full variants freeze
the dataset's complete resolved task set. Host links, runtime/cache preparation
and environment probes belong to the [shared Harbor package](../harbor/README.md).
The official numerical `reward` is preferred; one other numerical reward can be
used when unambiguous. Errors remain separate from scored task failures.

For a different runner, implement `BenchmarkAdapter.preflight` and `run` and
register it in [Catalog](../catalog.py). The [evaluation guide](../DEVELOPER_GUIDE.md#add-a-benchmark)
describes the request/result boundary. [Runner](../runner.py),
[runtime staging](../runtime.py) and [results](../results.py) own shared behavior.

```bash
.venv/bin/python -m unittest tests.eval.test_catalog tests.eval.test_harbor tests.eval.test_task_batches -v
```

These checks are offline. Real execution requires Harbor, task access, Docker,
Agent installation dependencies and model connectivity.
