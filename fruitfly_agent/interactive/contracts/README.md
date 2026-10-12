# Interaction Contracts

[Up: Interactive](../README.md)

Define the data and capabilities shared by hosts, Application, Session, and frontends. This package contains protocols and immutable views; it does not construct Providers, manage resources, or implement algorithms.

| File | Public entries / responsibility |
|---|---|
| [runtime.py](runtime.py) | RuntimeFactory, RuntimeSession, RuntimeAuthorization, and the RuntimeHandle protocol |
| [commands.py](commands.py) | InteractiveCommand, CommandResult, CommandContext, and CommandHandler |
| [events.py](events.py), [models.py](models.py) | Event envelopes, EventSink, status, history, and session views |
| [configuration.py](configuration.py), [model_setup.py](model_setup.py) | Generic configuration choices, model forms, and staging services |
| [optimization.py](optimization.py) | Search preview/execution, activity, and progress contracts |
| [candidates.py](candidates.py) | Candidate views, review, and isolated preparation/activation contracts |
| [task_packs.py](task_packs.py) | Task material and correction views/services |
| [evaluation.py](evaluation.py) | Optional external evaluation selection, launch, and event contracts |

Implement only the capabilities a host supplies. Optimization, candidates, and task materials are independently injected. Candidate preparation returns a handle satisfying this package's RuntimeHandle protocol. The concrete constructor belongs to [Application](../application/README.md) and is exported as `fruitfly_agent.interactive.RuntimeHandle`.

Runtime protocols reference public Core result, context-item, and permission types. Other view contracts remain independent of Core. Contracts do not import any Interactive implementation, including in TYPE_CHECKING blocks. Event and data serialization behavior is independent of directory layout; no schema or project version changes.

No environment variables, model calls, filesystem writes, or resource ownership. Concrete effects belong to service implementations. See [Run adapters](../../run/adapters/README.md) and [terminal feature extensions](../terminal/features/README.md).

```bash
.venv/bin/python -m unittest tests.architecture.test_boundaries tests.contracts.test_public_api tests.contracts.test_signatures -v
.venv/bin/python -m mypy
```
