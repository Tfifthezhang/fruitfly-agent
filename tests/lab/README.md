# Lab Tests

[Up: Tests](../README.md)

Verify algorithms and components through Core contracts and Catalog assembly.

| Files | Protects |
|---|---|
| `test_builtin_tools.py` | Character counts, file contents, output truncation, and shell failure reporting |
| `test_catalog.py / test_base_prompt.py` | Registered identities, actionable rejection errors, and validation of disabled selections |
| `test_search.py` | Frozen problems, evaluator, OPRO, journal, budgets, and optional private tool Agent |
| `test_skill_catalog.py / test_algorithm_contracts.py` | Bounded guidance, transformer forms, signals, and cancellation |
| `test_reduction_safety.py / test_summarizing_compaction.py` | Valid summaries, tool associations, overflow, external references, and commits |
| `test_task_packs.py / test_pack_format.py / test_coding_tasks.py` | Task material, catalog discovery and dangling-link rejection, policy, and restricted scoring |
| `test_rsi.py / test_rlm.py` | Host-driven evolution and local IPython/artifact behavior |
| `test_algorithm_audit.py` | Edit spans, rendered budgets, and environment regressions |

Use temporary materials, fake Providers, and injected HTTP callbacks. RLM tests start local IPython processes; none prove real model gains.

```bash
.venv/bin/python -m unittest discover -s tests/lab -t . -v
```
