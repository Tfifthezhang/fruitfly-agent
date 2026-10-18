# Skill Document Optimization

[Up: Improvement Methods](../README.md)

Optimize **reusable procedural knowledge** with bounded document edits. The `skill-edit` method changes the [Skill document](../../../context_manager/augmentation/skills/README.md#optimize-a-skill-body), an S target with schema `skill-document-v1`. Catalog-loading guidance remains H.

## Run an update

Enable **Reusable skill document** under Context augmentation. Set `source_path` to one workspace-relative `SKILL.md`, or enter `initial_text`. Start a new session and select the named Skill target, then **Skill document optimization** in `/improvement`. Choose a pack compatible with `skill-document`, with disjoint training, selection and holdout. [Offline example](../../../../../examples/improvement/native_methods/README.md).

| Stage | Implemented behavior |
|---|---|
| Rollout | Rotate bounded batches from the frozen training partition |
| Reflect | Analyze measured successful and failed training trajectories in minibatches |
| Merge | Merge/rank proposals from multiple minibatches under the edit allowance |
| Edit | Apply `add`, `replace` or `delete`; replacements require an exact unique match |
| Gate | Accept only strict selection improvement; remember rejected edits and scores for later reflection |
| Confirm | Test the selection winner once against the baseline on independent tasks; reject regressions |
| Deploy | Human-reviewed immutable Skill body; new sessions consume the complete body with its reference directory |

| Parameter | Default | Meaning |
|---|---:|---|
| `rounds` | 2 | Maximum update rounds |
| `edit_budget` | 2 | Maximum operations per candidate |
| `rollout_batch_size` | 4 | Training tasks per update |
| `reflection_batch_size` | 2 | Training trajectories per reflection request |

The model and H/I stay fixed. Current Skill and rejected-edit memory are job-local; each search starts from its target snapshot. Source files and references are unchanged. Shared model/trial budgets include confirmation. Invalid patches skip the update; infrastructure errors do not teach lessons. Cancellation publishes nothing; interrupted model requests are not replayed. Accepted artifacts and normal sessions support recovery, not mid-search optimizer resumption. Real execution calls models and may incur charges.

## Research source and scope

Yang et al., [SkillOpt: Executive Strategy for Self-Evolving Agent Skills](https://arxiv.org/abs/2605.23904), treat the skill document as the external trainable state of a frozen agent. This native implementation adopts trajectory minibatches, bounded edits, proposal merging, a strict validation gate and a rejected-edit buffer. The edit allowance is constant per job. Epoch-wise slow/meta updates, learning-rate schedules, Sleep integrations and the paper's benchmarks are not implemented. Source Skill dependencies are bounded Markdown/text snapshots; this does not freeze arbitrary linked programs or external resources. No upstream implementation code is included. Scripted tests do not establish model quality.

The [public entry](./__init__.py) exports `SkillEditImprover`, `apply_edits` and `definition()`; [registration.py](registration.py) declares the method. No method-specific environment variables.

```bash
.venv/bin/python -m unittest tests.lab.test_document_methods tests.workflows.test_native_improvement
```
