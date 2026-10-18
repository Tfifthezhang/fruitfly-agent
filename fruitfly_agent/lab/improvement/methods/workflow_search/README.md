# Workflow Search

[Up: Improvement Methods](../README.md)

Search **how the Agent executes a task**. The native `workflow-search` method generates and compares [bounded execution workflows](../../../workflow/README.md), an H target with schema `execution-workflow-v1`.

## Run a search

Enable **Execution workflow**, start a session, and select that target in `/improvement`. Expand **Workflow search**, then choose a task pack whose `compatible_targets` includes `execution-workflow`. Train, selection and holdout must be nonempty and disjoint. [Offline example](../../../../../examples/improvement/native_methods/README.md).

| Stage | Implemented behavior |
|---|---|
| Initialize | Measure the current workflow on selection and training tasks |
| Design | Show prior measured designs, training evidence and optional user guidance to the improver model |
| Reflect and repair | Review the design, repair schema errors within the configured allowance |
| Compare | Execute every stage; measure training and selection; retain distinct measured designs as stepping stones |
| Select | Rank workflows that strictly beat the initial selection score |
| Confirm | Test only the selection winner on independent holdout; require no aggregate or per-case regression |
| Adopt | Human review, then exact H artifact activation in a new session |

| Parameter | Default | Meaning |
|---|---:|---|
| `rounds` | 2 | Maximum new designs |
| `archive_limit` | 5 | Latest measured designs shown to the generator |
| `reflection_steps` | 1 | Self-review requests per design |
| `repair_attempts` | 1 | Repairs of invalid declarations |

Shared [budgets](../../README.md#budgets-progress-and-failure) apply to generation, every execution stage and confirmation. All steps borrow the active model. The archive is job-local, resets for each search and is recorded in the shared journal. Errors have no score; semantic duplicates skip trials. Cancellation publishes nothing. A budget exit can retain measured search results internally, but cannot bypass mandatory confirmation. Unknown paid work is not replayed.

## Research source and scope

Hu, Lu and Clune, [Automated Design of Agentic Systems](https://arxiv.org/abs/2408.08435), introduce Meta Agent Search. This implementation adopts archive-conditioned design, self-reflection, repair and task-based comparison. Its representation is a bounded sequential instruction workflow. It does not reproduce arbitrary Python `forward()` generation, parallel multi-agent architectures or the paper's experiments. No upstream implementation code is included. Offline tests establish covered execution and lifecycle behavior, not quality gains.

The [public entry](./__init__.py) exports `WorkflowSearchImprover` and `definition()`; [registration.py](registration.py) owns parameters and binding. Dependencies are injected search services; no method-specific environment variables.

```bash
.venv/bin/python -m unittest tests.lab.test_document_methods tests.lab.test_retained_targets tests.workflows.test_native_improvement
```
