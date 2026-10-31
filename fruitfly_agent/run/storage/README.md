# Workspace Storage

[Up: Run](../README.md)

Persist immutable text, candidate records, and readable outputs. Storage validates contents and record formats; it does not judge quality, construct runtimes, or activate Application.

| File / entry | Responsibility |
|---|---|
| [sessions.py](sessions.py): `SessionLeases` | Share one exclusive Session writer during serialized runtime replacement |
| [artifacts.py](artifacts.py): `DataArtifactStore` | Store and verify immutable text and binary bytes under SHA-256 identities |
| [media.py](media.py): `SessionMedia` | Session-granted media resources, recorded origin/size/type and recovery hash validation |
| [prompts.py](prompts.py): `resolve_base_prompt` | Resolve built-in or stored prompt contents without assembly |
| [candidates.py](candidates.py): `CandidateRecord`, `CandidateStore` | Create, read, update, replace, and delete records |
| [improvement_runs.py](improvement_runs.py): `ImprovementRunStore` | Atomic experiment summaries and verified journal reads, scoped to configuration/profile |
| [experience.py](experience.py): `ExperienceStore` | Pending lesson review, optimistic library commit and exact S snapshots |
| [verification.py](verification.py): `VerificationUseStore` | Atomic private-suite claims; unknown work remains consumed |
| [results.py](results.py): `save_task_result` | Export latest complete task/configuration/profile/target results |
| [retention.py](retention.py): `compact_candidates` | Protect references before deleting obsolete owned records and contents |

`SessionLeases.acquire(path, resume=True)` reuses a writer already owned by this pool. Each idempotent release decrements its reference count; the final release closes the writer and unlocks the file. Fresh acquisition retains Core locking and validation. The pool grants no execution authority and has no runtime/configuration dependencies. Application must serialize replacement; it does not permit concurrent writers or sharing across processes.

`replace_record` replaces an existing validated record. `delete` removes a record; callers must apply retention rules first. Candidate business rules belong to the [improvement host](../improvement/README.md).

| Data | Location |
|---|---|
| Immutable text and media | `.fruitfly/artifacts/` |
| Candidates | `.fruitfly/improvement/candidates/` |
| Experiment summaries | `.fruitfly/improvement/runs/`; all submitted outcomes, including no candidate |
| Readable results | `.fruitfly/improvement/task-results/` |

Experiment records use their independent schema version 1. History retains candidate and journal references; referenced candidates remain protected during compaction. Run history is not automatically pruned. A running record left by an interrupted process is not permission to replay work. Exports are not runtime inputs. Malformed or suspicious references stop cleanup; arbitrary unowned artifacts are not swept. Keep secrets out of stored text and reports. No model calls or module-specific environment variables.

```bash
.venv/bin/python -m unittest tests.lab.test_base_prompt tests.run.test_improvement_versions tests.run.test_task_prompt_catalog -v
```

[snapshots.py](snapshots.py) stores verified text trees and materializes fresh directories. [versions.py](versions.py) stores H/I/S and modification manifests with verified referenced contents. Source snapshots include package Python files and declared build inputs, excluding local sessions, secrets and caches. Candidate compaction follows structured artifact references and protects experiment manifests before collecting obsolete prompt text. Hashes describing task/trace identities need not identify stored artifacts.

Content-addressed artifact files use the bare lowercase SHA-256 digest as the filename under `.fruitfly/artifacts/`. External consumers can copy explicitly referenced immutable files after checking their content hash; they must not copy the whole workspace store or infer mutable learning state from it.

Job plans use schema 2 for execution metadata and normalized requests. Submitted-run
summaries keep their independent schema 1; old histories remain readable. Pending
lessons retain their own schema 1, including initial library identity and review
status. Only explicit commit changes the S snapshot. Verification claims use a
locked atomic ledger; completed-proof reuse does not claim a new use. These stores
do not validate model quality or grant activation authority.

`evolution.py` owns atomic schema-2 evolution jobs under `.fruitfly/evolution/`,
including phase, strategy identity, charged root usage and deadline. Schema-1 jobs
remain readable; writes normalize updated jobs. Storage does not score or adopt.

