# Attributed Experience

[Up: Improvement](../README.md)

[__init__.py](__init__.py) serializes validated `ExperienceEntry` records and
computes ordered library snapshot identity. Each record retains task, cue, lesson,
limitations, cited execution IDs and a reusable harness snapshot. No filesystem,
Provider requests or automatic activation occur in this module.

The reflector may decline to create an entry. Run freezes one library snapshot per
task, commits pending entries only at a completed task boundary, and includes the
library in S identity. Optimistic snapshot checks reject concurrent changes;
repeated identical entries are idempotent and conflicting identities fail.
Persistent improvement defers library updates rather than changing the candidate's
parent during verification. One coordinator writes the library; cross-process
transactions are not provided.

Future tasks receive experience as evidence while keeping the common configured
baseline. The library does not automatically install every prior task-local edit.
No benchmark answer or scorer is an implicit learning resource. Offline checks:
`tests.lab.test_improvement_pipeline`, `tests.workflows.test_improvement_pipeline`.
