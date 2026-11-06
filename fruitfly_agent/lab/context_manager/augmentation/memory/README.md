# Cross-session Memory

[Up: Augmentation](../README.md)

Memory provides durable, attributed notes and on-demand reading across sessions.
The selected method owns reading and maintenance. Its saved content is a separate
S configuration surface, not a second selectable mechanism.

| Entry | Responsibility |
|---|---|
| [registration.py](registration.py) | Compose implementations for the Memory selection group |
| [improvement.py](improvement.py) | Public mechanism and isolated-learning execution declarations |
| [File memory](methods/file_memory/README.md) | H reading/maintenance policy and S retained entries |

Choose Memory under Context augmentation. New memory methods use the same
selection group, feature path and existing Catalog contracts. Do not add method
branches to Run or Interactive. Declare initial state, reset/recovery, editable
fields, isolated execution and verified activation alongside the implementation.

Offline checks: `tests.lab.test_memory_comparison`, `tests.run.test_memory_lifecycle`
and `tests.workflows.test_memory_skills`. These establish behavior and isolation;
they do not demonstrate recall quality or benchmark gains.
