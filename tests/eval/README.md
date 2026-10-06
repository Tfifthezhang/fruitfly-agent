# Eval Tests

[Up: Tests](../README.md)

Verify optional evaluation plans, Harbor mapping, artifacts, and reports offline.

| Files | Protects |
|---|---|
| `test_catalog.py / test_planning.py` | Availability, studies, and frozen conditions |
| `test_harbor.py` | Commands, reported project version, setup, complete logs/events, registry retry boundaries, and parsing |
| `test_cli.py` | CLI and saved reports |
| `../support/harbor.py` | Isolated optional SDK substitute |

No downloads, Docker jobs, or real models. Synthetic rewards validate report semantics, not capability. Request format baselines belong to Contracts.

```bash
.venv/bin/python -m unittest discover -s tests/eval -t . -v
```
