# Improvement Host

[Up: Run](../README.md)

Bind the public Lab workflow to durable storage and Application lifecycle. Leaf
services receive explicit callbacks and stores, never the composition Factory.

| Entry | Responsibility |
|---|---|
| [pipeline.py](pipeline.py): `RunComponentJobs` | Freeze previews; assemble injected stage ports; persist outcomes and journals |
| [external.py](external.py): `RunExternalJobs` | Prepare external task streams and reuse the same workflow |
| `RuntimeTrialRunner` | Bind normal Application trials and validate official receipts |
| [versions.py](versions.py): `RunVersions` | Source-backed H, declared I and registered S identity |
| [candidates.py](candidates.py): `RunCandidates` | Review, scope validation, adoption and recovery |
| [evolution.py](evolution.py): `RunEvolutionHost` | Durable RSI phases with independent verification |
| [startup_versions.py](startup_versions.py) | Explicit temporary or remembered version choices |

Preview freezes the instruction, byte resources, components, parent H/I/S,
experience and comparison materials. Its one-use token binds exact guidance and
allocations. Changed conditions reject execution. Construction, timeout,
cancellation and ordinary failure close journal resources; submitted intent remains
in history even without a candidate.

Native file tasks use detached in-memory inputs. External execution downloads only
after submission, freezes source/configuration and validates task, lease, model-call,
runtime and environment receipts. Scores remain outside behavior editing. The
stream shares a total allocation, starts each task with the common configured
harness, and carries committed experience separately. External streams currently
return task-local outputs rather than persistent candidates.

Persistent publication requires `verified` assurance from the injected verifier.
Changed text bindings form one version candidate, including mixed H/S changes.
Review and activation use existing host guards. Model, permissions and source
conditions are rechecked before adoption. Registration alone cannot activate code.

The public Run evolution wrapper requires an explicit workflow `request` and an
independent verifier. It previews each persistent proposal before invoking the
normal Application job. Unknown proposing/verifying work is not replayed; partial
activation is reconciled. One coordinator owns a job; no cross-process transaction
is provided.

See [Lab Improvement](../../lab/improvement/README.md),
[RSI](../../lab/rsi/README.md), [Storage](../storage/README.md) and
[Application adapters](../adapters/README.md). There are no new secret variables.

```bash
.venv/bin/python -m unittest tests.run.test_host_services tests.workflows.test_improvement_pipeline tests.workflows.test_improvement_history tests.workflows.test_evolution
```
