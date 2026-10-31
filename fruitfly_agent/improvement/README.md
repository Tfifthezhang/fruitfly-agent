# Improvement Runtime

[Up: Runtime Architecture](../README.md)

Run bounded improvement stages through injected capabilities. This module is a
peer of Core and Lab. It depends only on Python's standard library, Core and its
own contracts. It constructs no editor, Provider, benchmark, configuration loader,
Application, filesystem store or activation service.

## Separate responsibilities

| Owner | Responsibility |
|---|---|
| Improvement | Stage transitions, evidence identity, independent stage times, scheduling, lifecycle hooks and result retention |
| [Core](../core/README.md) | Existing messages, tools, Provider and Agent loop contracts |
| [Lab](../lab/improvement/README.md) | Editors, assessors, selection/exploration/soft stopping, research, delivery validation, strategies and adapters |
| [Catalog](../lab/catalog/README.md) | Configuration, supported fields, dependencies and assembly |
| [Run](../run/improvement/README.md) / Application | Composition, durable records, publication and explicit activation |
| [Eval](../../fruitfly_eval/improvement/README.md) | Optional benchmark runners and benchmark episode adapters |

A generator proposes an evidence-grounded candidate; an executor supplies its
receipt; a selector chooses an existing completed result; an independent verifier
may grant persistent eligibility. No stage activates a candidate. Editing uses the
existing Core Agent loop supplied by Lab, rather than a second model loop here.

## Use the public ports

[api.py](api.py) exposes immutable values and runtime services. Construct
`ImprovementWorkflow` with an explicit strategy registry, selection and stop policies,
components, generators, runner and composition ports. Optional measurement, assessment,
exploration, reflection and verification ports retain separate responsibilities.
Lab's workflow assembly supplies built-in defaults. Use `async with WorkflowServices`
or close it explicitly; borrowed ports remain caller-owned.

| Module | Purpose |
|---|---|
| [Contracts](contracts/README.md) | Materials, snapshots, stages, receipts, failures and identities |
| [Workflow](workflow/README.md) | Shared search engine, controller and usage observation |
| [Execution](execution/README.md) | Bounded queues, handles, immutable events and batch execution |
| [Components](components/README.md) | Owner registry, exact component set and publication binding validation |
| [Evidence](evidence/README.md) | Immutable receipt/report reading |
| [Extensions](extensions/README.md) | Immutable lifecycle snapshots and bounded context contributions |

[Lab termination](../lab/improvement/termination/README.md) supplies concrete soft
stop conditions. [Lab research](../lab/improvement/research/README.md) supplies
research context and progress analysis; none belongs in
the kernel merely because it affects task success.

## Handle failure without inventing success

Ordinary stage exceptions and local operation timeouts become attributable
`StageFailure` records. Proposal/composition failure preserves earlier candidates;
execution failure preserves a failed receipt; missing measurement prevents an
unsupported promotion; failed selection retains the incumbent. A failed reference
can support diagnosis only when its granted facts explicitly mark useful observed
execution. Diagnostic evidence supplies no missing score or verification.

User cancellation, mismatched immutable identities,
failed persistence and unconfirmed cleanup stop work. Cancellation propagates;
unknown model work is never automatically replayed. The host journals execution
receipts, validated candidates and selection checkpoints as work completes.
Checkpoints support inspection, not transparent resumption of uncertain work.
Cleanup attempts all owned resources and reports failures.
Trusted plugins must cooperate with cancellation; Python cannot forcibly stop an
arbitrary plugin or certify external process termination.

## Verify offline

```bash
.venv/bin/python -m unittest tests.improvement.test_reliability tests.architecture.test_improvement_boundaries tests.eval.test_improvement
```

Fake Providers and rewards establish covered control flow, isolation and accounting.
They do not establish model quality, benchmark gains or live service compatibility.
