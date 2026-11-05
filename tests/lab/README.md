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
| `test_mcp_config.py / test_mcp_client.py / test_mcp_tools.py / test_mcp_authorization.py` | Optional SDK isolation, stdio lifecycle, exact schemas, reply retention and separate per-tool grants |
| `test_catalog.py / test_catalog_assembly.py / test_builtin_catalog.py / test_base_prompt.py` | Registered identities, actionable rejection errors, and validation of disabled selections |
| `test_failure_processing.py / test_automatic_improvement.py` | Derived exercises, provenance, original-task gates, independent confirmation, and isolated task execution |
| `test_skill_catalog.py / test_algorithm_contracts.py` | Bounded guidance, transformer forms, signals, and cancellation |
| `test_reduction_safety.py / test_working_memory.py` | Valid memory updates, tool associations, overflow, external references, and commits |
| `test_task_packs.py / test_pack_format.py / test_coding_tasks.py` | Task material, catalog discovery and dangling-link rejection, policy, and restricted scoring |
| `test_rlm.py` | Local IPython and artifact behavior |
| `test_improvement_pipeline.py / test_improver.py` | Stage contracts, result retention, stopping, hierarchical budgets and frozen editor fields |
| `test_improvement_mechanisms.py` | Synchronous faults, invalid results, hook isolation, missing evidence, evidence-index wiring and bounded long sequences |
| `test_improvement_delivery.py` | Declared outputs, missing sidecars, clean-directory validation and unsupported backend admission |
| `test_task_sets.py / test_task_set_search.py` | Frozen task identity, deterministic coverage, common full-set selection and incomplete candidates |
| `test_joint_assessment.py` | Bounded task parallelism, cancellation, explicit objective aggregation and missing-result rejection |
| `test_completed_improvement.py` | Completed comparisons and official selection, granted facts, independent judgments, failure fallback and stopping |
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

[RSI runtime tests](../rsi/README.md) own generation and restart accounting.

`test_improvement_configuration.py` verifies configured I search rounds in real
fake-Provider episodes, exact returned evidence pages, independent assessor
guidance and immutable local allowances. These are wiring tests, not quality gains.


[Improvement runtime tests](../improvement/README.md) own loop fault injection;
`test_editor_execution.py` covers editor execution and interrupted registered task execution;
`test_parameter_candidates.py` checks actual isolated parameter application and
`test_managed_commands.py` checks polling, capacity and cancellation.

`test_working_memory.py` covers incremental coverage, failed updates, bounded
memory, checkpoint persistence and corrupt/missing recovery artifacts.
`test_context_measurement.py` checks precision, image/schema/framing accounting,
Provider scope calibration, exact-count fallback and auxiliary preflight.
`test_context_history.py` checks session-scoped retrieval and pagination.
`test_long_context.py` completes 80 tool batches with repeated reduction and
valid measured requests. These fake episodes establish covered runtime behavior,
not model quality or benchmark gains.

`test_tool_catalog.py` checks demand-loaded usage, protected tool contracts and
isolated policy candidates. `test_execution_registration.py` covers explicit
backend requirements and rejection before model calls. Catalog assembly and
resource-materialization tests cover cleanup and frozen dependencies. `test_context_history.py` checks ordinary
read routing, long-line pagination and session isolation.

`test_layered_compaction.py` covers deterministic previews, archive readback, source
identity and artifact recovery. `test_layered_compaction_failures.py` covers bounded
hybrid inference, rejection, cancellation, retry admission and evidence ledgers.

`test_model_roles` checks declared conditional model admission, explicit fallbacks
and attributed execution. Working-memory safety tests cover threshold gating,
failed-attempt cooldown, successful-prefix retention and total update deadlines.
Managed-command tests cover independent work, isolated listeners and retirement.

`test_evidence_index.py` owns format decoding, source spans, call/result relationships, explicit partial coverage and stale-view invalidation. `test_evidence_coverage.py` owns multidimensional completeness and missing captured-byte detection.
