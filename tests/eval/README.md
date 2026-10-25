# Eval Tests

[Up: Tests](../README.md)

Verify single-configuration requests, Harbor mapping, artifacts, and reports offline.

| Files | Protects |
|---|---|
| `test_catalog.py / test_execution.py` | Availability, execution, failure handling, and reports |
| `test_harbor.py` | Commands, reported project version, setup, complete logs/events, registry retry boundaries, and parsing |
| `test_preparation.py` | Machine settings, controller dependency receipts, link/content/image drift, frozen tasks, assets, setup patches and cache boundaries |
| `test_verifier_environments.py` | Public environment extension, role isolation, inherited/step verifier definitions, versioned datasets and exact verifier ownership |
| `test_harbor_lifecycle.py` | Scoped stop, timeout/process/container cleanup, startup cancellation, PID reuse and multiple phase failures |
| `test_task_batches.py` | Shared GPU/resource filtering, Compose services, inventories before startup, exact task/attempt coverage and three catalog selections |
| `test_cli.py` | Evaluation-only CLI and saved reports |
| `test_task_selection.py / test_task_set_source.py` | Exact prepared subsets, separate leaves, quota settlement and private verifier exclusion |
| `test_runtime.py` | Default/explicit selection, snapshots, model/credential dependencies, execution parameter preservation/rejection, remote-environment rejection, artifact integrity and installation identities |
| `test_execution_facts.py` | Terminal diagnostics, legacy unknown facts, collection failure versus absence and excluded private verifier data |
| `test_trajectory.py` | ATIF tools/observations, zero and unknown usage, malformed-session rejection |
| `../support/harbor.py` | Isolated optional SDK substitute |

The real container supervisor process test runs only on Linux with `/proc`.
Other systems exercise ownership doubles and host-process cleanup. Default tests
do not claim actual remote image, verifier cache or model compatibility.

No downloads, Docker jobs, or real models. Synthetic rewards validate report semantics, not capability. Request format baselines belong to Contracts.

```bash
.venv/bin/python -m unittest discover -s tests/eval -t . -v
```

`test_improvement.py` exercises the optional adapter through actual Improvement
ports, frozen preparation doubles, candidate configuration and held quota. It
excludes private verifier files and tests cancellation without Docker or models.

`test_improvement_process.py` checks controller launch, private-log forwarding
and cancellation during process creation with process doubles.
