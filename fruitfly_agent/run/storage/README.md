# Workspace Storage

[Up: Run](../README.md)

Persist immutable text, candidate records, and readable outputs. Storage validates contents and record formats; it does not judge quality, construct runtimes, or activate Application.

| File / entry | Responsibility |
|---|---|
| [artifacts.py](artifacts.py): `DataArtifactStore` | Store and verify UTF-8 text under SHA-256 identities |
| [prompts.py](prompts.py): `resolve_base_prompt` | Resolve built-in or stored prompt contents without assembly |
| [candidates.py](candidates.py): `CandidateRecord`, `CandidateStore` | Create, read, update, replace, and delete records |
| [results.py](results.py): `save_task_result` | Export latest complete task/configuration/profile/target results |
| [retention.py](retention.py): `compact_candidates` | Protect references before deleting obsolete owned records and contents |

`replace_record` replaces an existing validated record. `delete` removes a record; callers must apply retention rules first. Candidate business rules belong to the [improvement host](../improvement/README.md).

| Data | Location |
|---|---|
| Immutable text | `.fruitfly/artifacts/` |
| Candidates | `.fruitfly/optimization/candidates/` |
| Readable results | `.fruitfly/optimization/task-results/` |

Formats and locations remain unchanged. Exports are not runtime inputs. Malformed or suspicious references stop cleanup; arbitrary unowned artifacts are not swept. Keep secrets out of stored text and reports. No model calls or module-specific environment variables.

```bash
.venv/bin/python -m unittest tests.lab.test_base_prompt tests.run.test_optimization_versions tests.run.test_task_prompt_catalog -v
```
