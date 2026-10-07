# Offline Workflows

[Up: Tests](../README.md)

Exercise actual Application, Run assembly, and terminal paths with offline models.

| Files | Protects |
|---|---|
| `test_decoupling.py / test_offline_example.py` | Public extensions and interchangeable optimizers/targets |
| `test_optimization.py / test_evolution.py` | Preview, adoption, explicit policy, and interrupted activation reconciliation |
| `test_task_packs.py / test_coding_optimization.py / test_unified_packs.py` | Discovery, frozen tasks, corrections, and scoring |
| `test_optimization_activity.py` | Real local search activity mapped to frontend progress |
| `test_optional_eval.py` | Normal CLI and offline conversation with Eval imports prohibited |
| `test_resume_history.py` | Persisted startup/picker/path recovery, visible history, unchanged context, and cancellation/failure |

Verify usable integration, not model quality. New algorithms should reuse generic production paths.

```bash
.venv/bin/python -m unittest discover -s tests/workflows -t . -v
```
