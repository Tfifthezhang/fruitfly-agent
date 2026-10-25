# Lab Tests

[Up: Tests](../README.md)

Verify algorithms and components through Core contracts and Catalog assembly.

| Files | Protects |
|---|---|
| `test_harness_inventory.py` | Owner-derived H/S/I availability, generic extension metadata, backend checks and field permissions |
| `test_builtin_tools.py` | Character counts, file contents, output truncation, and shell failure reporting |
| `test_ssh_env.py` | Remote paths, secret injection boundaries, SSH lifecycle, permissions and supervised cancellation without network |
| `test_web_tools.py` | Offline search/fetch adapters, extraction, pagination, HTTP deadlines, retries, cache and cancellation |
| `test_web_services.py` | Service injection, registry extension, credential metadata and known/unknown final URLs |
| `test_catalog.py / test_base_prompt.py` | Registered identities, actionable rejection errors, and validation of disabled selections |
| `test_failure_processing.py / test_automatic_improvement.py` | Derived exercises, provenance, original-task gates, independent confirmation, and isolated task execution |
| `test_skill_catalog.py / test_algorithm_contracts.py` | Bounded guidance, transformer forms, signals, and cancellation |
| `test_reduction_safety.py / test_summarizing_compaction.py` | Valid summaries, tool associations, overflow, external references, and commits |
| `test_task_packs.py / test_pack_format.py / test_coding_tasks.py` | Task material, catalog discovery and dangling-link rejection, policy, and restricted scoring |
| `test_rsi.py / test_rlm.py` | Host-driven evolution and local IPython/artifact behavior |
| `test_improvement_pipeline.py / test_improver.py` | Stage contracts, result retention, stopping, hierarchical budgets and frozen editor fields |
| `test_task_sets.py / test_task_set_search.py` | Frozen task identity, deterministic coverage, common full-set selection and incomplete candidates |
| `test_batch_scheduler.py / test_joint_assessment.py` | Bounded task parallelism, cancellation, explicit objective aggregation and missing-result rejection |
| `test_completed_improvement.py` | Zero-reward official selection versus exploration seed, granted facts, independent judgments, failure fallback and stopping |
| `test_algorithm_audit.py` | Edit spans, rendered budgets, and environment regressions |

Use temporary materials, fake Providers, and injected HTTP callbacks. RLM tests start local IPython processes; none prove real model gains.

```bash
.venv/bin/python -m unittest discover -s tests/lab -t . -v
```

Environment tests include protected credentials, ordinary algorithm state, external approvals, symlink retargeting, and explicit child environments. No real credentials or network requests are used.

`test_online_improvement.py` checks event ordering, scoped control, unknown usage,
independent read-only inspection and assessment failure. `test_evolution_policies.py`
checks stopping, rejection continuation, scorer separation, private feedback and
versioned file changes with no real model requests.

`test_evolution_recovery_budget.py` verifies root allowance restoration, changed
limit rejection and conservative handling of unknown paid phases after restart.
