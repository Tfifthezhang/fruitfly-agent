# Execution Environments

[Up: Lab](../README.md)

`LocalEnv` accesses the host filesystem and runs local shell commands through Core's execution contracts.

| Behavior | Contract |
|---|---|
| Working directory | Relative paths and default command execution use `LocalEnv.cwd`; `ExecOptions.cwd` can override it. |
| Permissions | Current user permissions; absolute paths, `..`, network, and inherited environment are not restricted. |
| Failures | Common path/process failures return `Result.failure`. |
| Timeout / cancellation | Clean up the subprocess group. |
| Output | Incremental chunk reads and UTF-8 decoding; callbacks run while the process is active. |
| Callback failure | Isolate ordinary failures; preserve task cancellation. |
| Limits | File I/O is synchronous; complete stdout/stderr are retained in memory. |

## Files and extension

| File | Responsibility |
|---|---|
| [local.py](local.py) | `LocalEnv` implementation |
| [__init__.py](__init__.py) | Public exports |
| [Core protocols](../../core/env/protocols.py) | Required filesystem and shell operations |

Implement `ExecutionEnv` for another backend. Document paths, symlinks, encoding, environment inheritance, permissions, output, timeout, and cleanup. Register backend resources once through [Catalog](../catalog/README.md); tools share the injected backend. Container and read-only backends are extension options, not built-in capabilities.

No module-specific environment variables. See [Known limitations](../ALGORITHM_AUDIT.md).

```bash
.venv/bin/python -m unittest tests.lab.test_env tests.lab.test_builtin_tools -v
```
