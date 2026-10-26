# Offline Workflows

[Up: Tests](../README.md)

Exercise actual Application, Run assembly, and terminal paths with offline models.

| Files | Protects |
|---|---|
| `test_execution_policy.py` | Isolated configuration candidates, effective native limits and verified H-only activation |
| `test_terminal_reflow.py` | Actual TTY resize retains completed table output and redraws drafts without another model request |
| `test_terminal_scrollback.py` | Multi-turn long answers and output received during an asynchronous menu remain in native scrollback after return and exit |
| `test_terminal_interrupt.py` | Actual Ctrl+C/SIGINT, quiet-run continuation, clean exit, and terminal restoration in ANSI and non-ANSI terminals |
| `test_decoupling.py / test_offline_example.py` | Public extensions and interchangeable improvers/targets |
| `test_improvement.py / test_evolution.py` | Preview, adoption, explicit policy, and interrupted activation reconciliation |
| `test_improvement_pipeline.py` | Public stages, task evidence, shared budgets, component execution and pending experience review |
| `test_editor_evolution.py` | Actual I prompt loading, two isolated generations, paired private verification, proof reuse and failure/cancellation |
| `test_task_packs.py / test_coding_improvement.py / test_unified_packs.py` | Discovery, frozen tasks, corrections, and scoring |
| `test_optional_eval.py` | Normal CLI and offline conversation with Eval imports prohibited |
| `test_resume_history.py` | Persisted startup/picker/path recovery, visible history, unchanged context, and cancellation/failure |

Verify usable integration, not model quality. New algorithms should reuse generic production paths.

```bash
.venv/bin/python -m unittest discover -s tests/workflows -t . -v
```

Terminal interrupt workflows also exercise permission Enter/numeric/arrow selection, Esc denial, Ctrl+C cancellation, and session approval in ANSI and non-ANSI PTYs.

`test_evolution_scope.py` verifies frozen stop parameters and one root allowance
across successive host jobs. No model service is contacted.

`test_candidate_configuration.py` executes a changed tool allowance through the
native Core loop, exports the complete candidate, reloads it through ordinary
configuration, and verifies unchanged baseline files.
