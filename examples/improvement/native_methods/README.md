# Offline Workflow, Skill and Memory Improvement

[Up: Improvement Examples](../README.md)

Run all three methods through the normal Application without keys, network access or paid models:

```bash
.venv/bin/python -m examples.improvement.native_methods.offline
```

Expected output:

```text
workflow-search: confirmed and adopted (H changed).
skill-edit: confirmed and adopted (S changed).
memory-exploration: confirmed and adopted (S changed).
Scripted lifecycle checks; no model-quality claim.
```

[offline.py](offline.py) creates a temporary model catalog and schema-2 train/selection/holdout pack, registers a scripted Provider, searches one candidate, confirms it independently and explicitly adopts it. It verifies that search leaves the active version unchanged, then adoption changes only the declared H or S axis. All files are isolated in temporary workspaces and removed after closing resources.

## Use configured models

| Target | Enable this object mechanism | Method |
|---|---|---|
| Execution workflow | **Execution workflow** | [Workflow search](../../../fruitfly_agent/lab/improvement/methods/workflow_search/README.md) |
| Skill document | **Reusable skill document**, under Context augmentation | [Skill document optimization](../../../fruitfly_agent/lab/improvement/methods/skill_edit/README.md) |
| Environment memory | **Learned environment memory**, under Context augmentation | [Exploratory memory learning](../../../fruitfly_agent/lab/improvement/methods/memory_exploration/README.md) |

For a specific Skill, set `source_path` to a workspace-relative `SKILL.md`; its target label uses the Skill name. Original files remain unchanged, and the adopted full body retains the reference directory. Each configured mechanism supports one retained document.

Prepare a [task pack](../../../fruitfly_agent/lab/improvement/tasks/README.md) with compatible target IDs `execution-workflow`, `skill-document` or `learned-memory`. The task projection remains `text-v1`; concrete target adapters validate workflow JSON or document schemas separately. Training, selection and independent inputs must be disjoint. Select the target first, then its algorithm inline in `/improvement`, choose Task, Budget and Evaluation, and review the confirmation before starting.

Real model runs use the network and may incur charges for generation, every workflow stage, practice and confirmation. Defaults use tool-free trials; environment actions require an explicitly injected isolated executor and verifier. The example demonstrates lifecycle behavior, not capability gains or the papers' benchmark results.

```bash
.venv/bin/python -m unittest tests.lab.test_document_methods tests.lab.test_retained_targets tests.workflows.test_native_improvement
```
