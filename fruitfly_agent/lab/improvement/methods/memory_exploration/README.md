# Exploratory Memory Learning

[Up: Improvement Methods](../README.md)

Learn **reusable knowledge from verified practice**. The `memory-exploration` method changes [learned environment memory](../../../context_manager/augmentation/information/file_memory/README.md#learn-environment-memory), an S target with schema `environment-memory-v1`.

## Run exploration

Enable **Learned environment memory** under Context augmentation and start a session. Choose **Environment memory → Exploratory memory learning** in `/improvement`. The task pack must support `learned-memory`, with independent training, selection and holdout. [Offline example](../../../../../examples/improvement/native_methods/README.md).

| Stage | Implemented behavior |
|---|---|
| Broad practice | Curriculum model selects distinct authorized training task indices for coverage |
| Focused practice | Later rounds select one training task using prior measured outcomes and current memory |
| Act and verify | Run the selected tasks; the task policy or injected verifier supplies outcomes |
| Consolidate | Distill grounded procedures, conditions, hypotheses and failure lessons into a candidate document |
| Retain | Non-regressing memory may support later practice; only strict selection improvements qualify for publication |
| Confirm | Freeze the selection winner; compare it once against baseline on independent tasks |
| Reuse | Human-reviewed frozen memory is projected in subsequent sessions; deployment performs no exploration or updates |

| Parameter | Default | Meaning |
|---|---:|---|
| `rounds` | 3 | Maximum practice/consolidation rounds |
| `broad_rounds` | 1 | Initial rounds for coverage; later rounds focus on gaps |
| `practice_batch_size` | 3 | Maximum broad-phase tasks; focused phases select one |

Curriculum sees training inputs and grounded outcomes, not selection answers or holdout. Successes and measured failures can teach; infrastructure errors cannot. Curriculum cannot add tasks or change their acceptance. Consolidation is model-generated and remains fallible. Selection and confirmation checks do not prove every memory statement.

Shared budgets cover curriculum, task execution, consolidation and confirmation. Memory and curriculum evidence are job-local; searches reset from the frozen target. Adopted artifacts survive session recovery. Cancellation publishes nothing; unknown paid requests are not replayed. No automatic adoption or daily learning is installed. Calls may incur model charges.

## Research source and scope

Zhu et al., [RSIAgent: Autonomous Exploration for Recursive Self-improvement in New Environments](https://arxiv.org/abs/2609.15364), organize broad/deep exploration, grounded feedback, memory consolidation and frozen-memory reuse. This implementation adopts those mechanisms within an authorized finite task pool and adds selection and holdout gates. Broad practice is sequential. Default trials are text-only; isolated environment actions require an injected [TrialExecutor](../../trials/README.md) and real verifier. The desktop/VM framework, autonomous new-project creation, parallel reconciliation, source rewriting and published experiments are not implemented. No upstream implementation code is included. The method modifies S, not its own I implementation.

The [public entry](./__init__.py) exports `MemoryExplorationImprover` and `definition()`; [registration.py](registration.py) owns configuration. No method-specific environment variables.

```bash
.venv/bin/python -m unittest tests.lab.test_document_methods tests.workflows.test_native_improvement
```
