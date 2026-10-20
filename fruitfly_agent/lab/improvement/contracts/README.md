# Improvement Contracts

[Up: Improvement](../README.md)

[Pipeline](pipeline.py) defines immutable task materials, component file sets,
candidate bundles, execution records, optional measurements, plans, stage requests,
selection decisions and attributed experience. Stage protocols are exported through
[the public API](../api.py). There are no model requests or filesystem operations.

| Contract | Invariant |
|---|---|
| `TaskMaterial` / `Resource` | Owned relative paths and immutable byte references; no answers |
| `HarnessSnapshot` / `ComponentDocument` | Distinct stable IDs, declared kind, axis and schema |
| `CandidateBundle` | Frozen parent, complete component set and per-edit evidence |
| `ExecutionRecord` | Task, material, harness, initial state and conditions identities |
| `SelectionDecision` | Existing run ID; output selection differs from verification |
| `JobServices` / `JobResource` | Shared budgets, cancellation, operations and optional asynchronous cleanup |
| `RunPlan` | Exact component scope, generator, modes and shared allocations |
| `ExperienceEntry` | Task attribution, lesson, limitations, evidence and reusable snapshot |

[Versions](versions.py) bind H/I/S separately. [Candidates](candidates.py) declare
actual target changes; scope checks reject undeclared axes. Concrete adapters
belong to the object owner. Role metadata does not supply execution or activation.
Run uses the same version contracts for persistent publication and recovery.

```bash
.venv/bin/python -m unittest tests.lab.test_improvement_pipeline tests.lab.test_experiment_contracts tests.contracts.test_signatures
```
