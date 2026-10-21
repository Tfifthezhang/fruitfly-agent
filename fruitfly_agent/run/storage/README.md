# Workspace Storage

[Up: Run](../README.md)

Persist immutable text, candidate records, and readable outputs. Storage validates contents and record formats; it does not judge quality, construct runtimes, or activate Application.

| File / entry | Responsibility |
|---|---|
| [artifacts.py](artifacts.py): `DataArtifactStore` | Store and verify immutable text and binary bytes under SHA-256 identities |
| [prompts.py](prompts.py): `resolve_base_prompt` | Resolve built-in or stored prompt contents without assembly |
| [candidates.py](candidates.py): `CandidateRecord`, `CandidateStore` | Create, read, update, replace, and delete records |
| [improvement_runs.py](improvement_runs.py): `ImprovementRunStore` | Atomic experiment summaries and verified journal reads, scoped to configuration/profile |
| [experience.py](experience.py): `ExperienceStore` | Optimistic attributed-library commit and exact S snapshots |
| [results.py](results.py): `save_task_result` | Export latest complete task/configuration/profile/target results |
| [retention.py](retention.py): `compact_candidates` | Protect references before deleting obsolete owned records and contents |

`replace_record` replaces an existing validated record. `delete` removes a record; callers must apply retention rules first. Candidate business rules belong to the [improvement host](../improvement/README.md).

| Data | Location |
|---|---|
| Immutable text | `.fruitfly/artifacts/` |
| Candidates | `.fruitfly/improvement/candidates/` |
| Experiment summaries | `.fruitfly/improvement/runs/`; all submitted outcomes, including no candidate |
| Readable results | `.fruitfly/improvement/task-results/` |

Experiment records use their independent schema version 1. History retains candidate and journal references; referenced candidates remain protected during compaction. Run history is not automatically pruned. A running record left by an interrupted process is not permission to replay work. Exports are not runtime inputs. Malformed or suspicious references stop cleanup; arbitrary unowned artifacts are not swept. Keep secrets out of stored text and reports. No model calls or module-specific environment variables.

```bash
.venv/bin/python -m unittest tests.lab.test_base_prompt tests.run.test_improvement_versions tests.run.test_task_prompt_catalog -v
```

[snapshots.py](snapshots.py) stores verified text trees and materializes fresh directories. [versions.py](versions.py) stores H/I/S and modification manifests with verified referenced contents. Source snapshots include package Python files and declared build inputs, excluding local sessions, secrets and caches. Candidate compaction follows structured artifact references and protects experiment manifests before collecting obsolete prompt text. Hashes describing task/trace identities need not identify stored artifacts.

Content-addressed artifact files use the bare lowercase SHA-256 digest as the filename under `.fruitfly/artifacts/`. External consumers can copy explicitly referenced immutable files after checking their content hash; they must not copy the whole workspace store or infer mutable learning state from it.
