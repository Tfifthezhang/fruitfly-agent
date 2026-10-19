# Interaction Contracts

[Up: Interactive](../README.md)

Define the data and capabilities shared by hosts, Application, Session, and frontends. This package contains protocols and immutable views; it does not construct Providers, manage resources, or implement algorithms.

| File | Public entries / responsibility |
|---|---|
| [runtime.py](runtime.py) | RuntimeFactory, RuntimeSession, RuntimeAuthorization, and the RuntimeHandle protocol |
| [commands.py](commands.py) | InteractiveCommand, CommandResult, CommandContext, and CommandHandler |
| [events.py](events.py), [models.py](models.py) | Event envelopes, EventSink, status, history, and session views |
| [configuration.py](configuration.py), [model_setup.py](model_setup.py) | Generic configuration choices, model forms, and staging services |
| [mechanism_setup.py](mechanism_setup.py) | Optional guided mechanism forms, non-secret credential status and atomic staging |
| [improvement.py](improvement.py) | Role/target/method/parameter views, search preview/execution, activity, progress, optional history/log queries and submission receipts |
| [learning.py](learning.py) | Completed-task observation and optional material production service |
| [candidates.py](candidates.py) | Candidate views with evidence assessments, review, and isolated preparation/activation contracts |
| [task_packs.py](task_packs.py) | Task material and correction views/services |
| [evaluation.py](evaluation.py) | Optional benchmark task selection, improvement previews, and event contracts |

Implement only the capabilities a host supplies. Optional `ImprovementSubmissionService` records authorized intent before the Application task is scheduled, including immediate cancellation; it grants no execution or activation authority. Existing `ImprovementService` and `TextImprover` search signatures remain unchanged. Improvement, candidates, and task materials are independently injected. Candidate preparation returns a handle satisfying this package's RuntimeHandle protocol. The concrete constructor belongs to [Application](../application/README.md) and is exported as `fruitfly_agent.interactive.RuntimeHandle`.

Runtime protocols reference public Core result, context-item, and permission types. Other view contracts remain independent of Core. Contracts do not import any Interactive implementation, including in TYPE_CHECKING blocks. Event and data serialization behavior is independent of directory layout; no schema or project version changes.

No environment variables, model calls, filesystem writes, or resource ownership. Concrete effects belong to service implementations. See [Run adapters](../../run/adapters/README.md) and [terminal feature extensions](../terminal/features/README.md).

Configuration and improvement method views carry registration-owned implementation/guide paths. Configuration also declares `input_parameters`; improvement views identify the active configuration file/profile. Improvement method views declare optional `direction_help` for search-guidance input. Parameter views carry descriptions, choices, nullability and numeric bounds so frontends can show individual fields. These views describe input; task/method previews retain scoring and acceptance authority.

```bash
.venv/bin/python -m unittest tests.architecture.test_boundaries tests.contracts.test_public_api tests.contracts.test_signatures -v
.venv/bin/python -m mypy
```

`BenchmarkImprovementController` and `BenchmarkImprovementRequest` in [evaluation.py](evaluation.py) provide optional bounded task-source selection and offline improvement previews. A one-use token launches task preparation and iteration through Application. The preview and candidate values reuse the independent improvement and candidate contracts. Standalone evaluation belongs to the optional Eval CLI.

Tool start/finish events carry an optional plain-text `description`. Tool finish
adds `status` (`succeeded`, `failed`, `cancelled`, or `unknown`) and optional
`elapsed_seconds`. These fields are renderer-neutral and additive. Older payloads
without status deserialize as `unknown`; frontends must not infer success from
completion alone. `terminate` requests stopping the loop and is independent of
success/failure. Existing event IDs, sequence ordering and unknown-field handling
remain unchanged.
