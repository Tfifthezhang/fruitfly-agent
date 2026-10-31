# Assemble Improvement Workflows

[Up: Improvement](../README.md)

Lab supplies concrete strategies, selection, exploration, optional research and
stop policies to the independent [workflow runtime](../../../improvement/workflow/README.md).
It owns no second Agent loop.

| File | Responsibility |
|---|---|
| `assembly.py` | Inject concrete workflow policies |
| `task_sets.py` | Shared-batch execution and complete-set comparison |
| `mechanisms.py` | Optional research context and progress stopping |
| `adaptive.py` | Translate explicitly injected online control requests |

Task, task-set and fixed-I execution consume the same independent stage times.
Final selection has no protected call allowance. Completed incumbent evidence is
retained when a later stage fails. Selection does not grant independent adoption.

Offline checks: `tests.lab.test_task_set_search`,
`tests.lab.test_task_set_lifecycle`, `tests.workflows.test_improvement_pipeline`.
