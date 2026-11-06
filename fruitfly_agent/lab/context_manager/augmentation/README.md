# Augmentation

[Up: Context Manager](../README.md)

Add bounded instructions or information to model requests without rewriting
canonical conversation facts.

| Peer capability | Implementation and state |
|---|---|
| [Memory](memory/README.md) | File memory: H reading/maintenance and S retained notes |
| [Skills](skills/README.md) | H progressive loader and S installed procedures |
| [Local knowledge](information/methods/local_knowledge/README.md) | Read-only documents through shared information selection |
| [Live HTTP](information/methods/live_http/README.md) | External information through the same selection policy |

[Information spaces](information/README.md) own query, retrieval and rendering
contracts for the last two sources. Their hidden H policy is independently
editable; connectors and read-only knowledge are fixed input conditions. Memory
and Skills generate metadata directories directly and load bodies through `read`.
They do not need an information-ranking dependency or a separate catalog switch.

## Implement a transformer

Return a new `ContextFrame`, `ContextTransform(frame, metadata)` or `None` from
`transform(frame)`. Sync and async implementations are supported. Treat input and
nested messages as read-only. Bound projection size, define repeated-request
behavior, inject I/O and preserve cancellation. Core isolates ordinary stage
failures. Retrieved text remains untrusted data.

Declare the same owner feature path for the mechanism, configuration menu and
optimization surfaces through [Catalog](../../catalog/README.md). See the
[offline extension](../../../../examples/extensions/README.md).

Offline checks: `tests.lab.test_skill_catalog`, `tests.lab.test_information_pipeline`
and `tests.workflows.test_memory_skills`.
