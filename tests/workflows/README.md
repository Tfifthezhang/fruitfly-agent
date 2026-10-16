# Offline Workflows

[Up: Tests](../README.md)

Exercise actual Application, Run assembly, and terminal paths with offline models.

| Files | Protects |
|---|---|
| `test_dream_rsi.py` | Prefix-only replay, objective, I policy confirmation, activation and recovery |
| `test_terminal_interrupt.py` | Actual Ctrl+C/SIGINT, quiet-run continuation, clean exit, and terminal restoration in ANSI and non-ANSI terminals |
| `test_decoupling.py / test_offline_example.py` | Public extensions and interchangeable improvers/targets |
| `test_improvement.py / test_evolution.py` | Preview, adoption, explicit policy, and interrupted activation reconciliation |
| `test_automatic_improvement.py` | Separate learning material, original scoring, holdout confirmation, terminal preview and explicit adoption |
| `test_task_packs.py / test_coding_improvement.py / test_unified_packs.py` | Discovery, frozen tasks, corrections, and scoring |
| `test_improvement_methods.py` | Temporary method/target binding, stale method rejection, unchanged defaults, activation and recovery |
| `test_improvement_activity.py` | Real local search activity mapped to frontend progress |
| `test_optional_eval.py` | Normal CLI and offline conversation with Eval imports prohibited |
| `test_resume_history.py` | Persisted startup/picker/path recovery, visible history, unchanged context, and cancellation/failure |

Verify usable integration, not model quality. New algorithms should reuse generic production paths.

```bash
.venv/bin/python -m unittest discover -s tests/workflows -t . -v
```

Terminal interrupt workflows also exercise permission Enter/numeric/arrow selection, Esc denial, Ctrl+C cancellation, and session approval in ANSI and non-ANSI PTYs.
