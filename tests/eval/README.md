# Eval Tests

[Up: Tests](../README.md)

Verify single-configuration requests, Harbor mapping, artifacts, and reports offline.

| Files | Protects |
|---|---|
| `test_catalog.py / test_execution.py` | Availability, execution, failure handling, and reports |
| `test_harbor.py` | Commands, reported project version, setup, complete logs/events, registry retry boundaries, and parsing |
| `test_task_batches.py` | Exact subset filters, task caps, official task/attempt coverage, and catalog declarations |
| `test_cli.py` | Evaluation-only CLI and saved reports |
| `test_runtime.py` | Default/explicit selection, snapshots, model/credential dependencies, remote-environment rejection, artifact integrity and installation identities |
| `test_trajectory.py` | ATIF tools/observations, zero and unknown usage, malformed-session rejection |
| `../support/harbor.py` | Isolated optional SDK substitute |

No downloads, Docker jobs, or real models. Synthetic rewards validate report semantics, not capability. Request format baselines belong to Contracts.

```bash
.venv/bin/python -m unittest discover -s tests/eval -t . -v
```
