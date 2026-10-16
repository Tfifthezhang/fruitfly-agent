# Improvement Contracts

[Up: Improvement](../README.md)

Represent modification scope, immutable parent versions and comparison evidence without benchmark-specific dependencies.

| Entry | Responsibility |
|---|---|
| [__init__.py](__init__.py): `ImprovementRequest` | One H/S/I role, target and fixed comparison conditions |
| `ImprovementAdapter`, `ImprovementComparison` | Explicit preparation/cleanup and evidence-producing comparison |
| `ComparisonEvidence` | Bind the decision to candidate, policy and conditions |
| [search.py](search.py) | Text search problems, strategy/services protocols, observations and results |
| [versions.py](versions.py) | Immutable H/I/S identity and registered persistent-state snapshots |
| [candidates.py](candidates.py) | Declared target changes, candidate identity and target registry |

Target meaning and execution remain owned by the object module. A declared role or content hash does not provide an executable adapter. Model allocation, budgets and acceptance conditions remain external to the modifiable H/I/S triple. Original-task context belongs to [Experiments](../experiments/README.md).

No configuration, filesystem operations or model requests occur here. [Runtime](../runtime/README.md) validates and consumes these values; Run persists and activates candidates.

```bash
.venv/bin/python -m unittest tests.lab.test_improvement_roles tests.lab.test_experiment_contracts
```
