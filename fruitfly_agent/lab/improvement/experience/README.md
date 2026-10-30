# Attributed Experience

[Up: Improvement](../README.md)

[__init__.py](__init__.py) serializes validated `ExperienceEntry` records and
computes ordered library snapshot identity. Each record retains task, cue, lesson,
limitations, cited execution IDs and a reusable harness snapshot. No filesystem,
Provider requests or automatic activation occur in this module.

The reflector may decline to create an entry. Run freezes one library snapshot per
task and stages entries at a completed task boundary. Explicit idle review
commits or rejects them. Only the committed library enters S identity. Optimistic snapshot checks reject concurrent changes;
repeated identical entries are idempotent and conflicting identities fail.
Persistent improvement defers library updates rather than changing the candidate's
parent during verification. One coordinator writes the library; cross-process
transactions are not provided.

Future tasks receive experience as evidence while keeping the common configured
baseline. The library does not automatically install every prior task-local edit.
No benchmark answer or scorer is an implicit learning resource. Offline checks:
`tests.lab.test_improvement_pipeline`, `tests.workflows.test_improvement_pipeline`.

## Review a pending lesson

Use `/improvement` → Results and history → Pending experience. Inspect the lesson
and initial S identity, choose Commit or Reject, and confirm. Application rejects
writes while work is active. A changed library snapshot rejects a stale commit;
it does not silently merge a lesson into new conditions. Human confirmation
expresses adoption, not a measured claim of improvement.

Pending records live in `.fruitfly/improvement/experience-pending/`; committed
state remains `.fruitfly/improvement/experience.json`. Rejected/committed pending
records are retained as attributed decisions. They protect artifact references
during retention. [Editor experiments](../improver/README.md) never stage or commit
experimental lessons, and no inner episode has a production writer.

`reflection.py` owns model-based reflection. It consumes an injected read-only evidence inspector and services; it
cannot commit its own result. `AgentReflector` is provided by `experience.reflection`.
