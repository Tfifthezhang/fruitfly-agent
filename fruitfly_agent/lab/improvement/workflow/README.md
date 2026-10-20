# Workflow and Execution

[Up: Improvement](../README.md)

[__init__.py](__init__.py) implements the default `WorkflowController`,
`GeneratorRegistry`, shared allocation and cancellation services. Generation,
composition, execution, selection, optional verification and reflection use
public ports. No stage activates a candidate.

Parallel proposals share frozen references and prior history. Sequential rounds
carry the previous composition and executed edits. Scope, ownership, evidence
citations and task/state/condition receipts are checked before reuse. Generator
factories create job-local state; discovery uses registration metadata only.

[execution.py](execution.py) provides `FileTaskRunner`: fresh in-memory files,
read/write/edit tools, exact owner projections, root-budgeted model calls and
immutable output/trajectory resources. It uses final-stage answers. Bash, live
network tools and ambient Session/filesystem access are absent. Other runners
must declare capabilities and return attributable receipts.

Services reserve calls before work and cancel outstanding tasks on timeout or
cancellation. Exhaustion never invents a complete or verified result. No in-flight
work is replayed after process loss. Independent verification consumes the same
root allocation. Token and monetary limits require additional host accounting.

Offline checks: `tests.lab.test_improvement_pipeline`,
`tests.lab.test_retained_targets`, `tests.workflows.test_improvement_pipeline`.

Per-job factory products can implement `JobResource.aclose`. The Run host registers
ownership immediately, deduplicates objects and closes in reverse order after
success, failure or cancellation. Cleanup waits at most ten seconds per resource
(or the smaller operation timeout) and records failures. Borrowed verifier and
measurement ports remain caller-owned. Embeddings use `async with WorkflowServices`
or close their services explicitly after execution; generator factories must clean
up partially failed construction.
