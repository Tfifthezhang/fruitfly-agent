# Execution Environment Contracts

[Up: Core](../README.md)

Define how tools access files and execute commands. Concrete backends belong in [Lab Environment](../../lab/environment/README.md).

| Contract | Responsibility |
|---|---|
| `FileSystem` | File operations |
| `Shell` | Command execution |
| `ExecutionEnv` | Combined backend passed through `ToolCallContext.env` |
| `FileInfo`, `ExecOptions`, `ExecResult` | Operation inputs and results |

Expected external failures use `Result.failure`. Cancellation propagates after cleanup. The protocols do not supply permissions, path isolation, network isolation, or quotas.

| File | Responsibility |
|---|---|
| [protocols.py](protocols.py) | Structural contracts |
| [types.py](types.py) | Value types |
| [__init__.py](__init__.py) | Public exports |

Backend implementations must document paths, working directory, timeout, cancellation, and environment inheritance. No module-specific environment variables.

```bash
.venv/bin/python -m unittest tests.lab.test_env tests.contracts.test_public_api -v
```
