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

## Apply lightweight permissions

[permissions.py](permissions.py) defines `PermissionPolicy` and `PermissionAuthorizer`. [guarded.py](guarded.py) implements `GuardedEnv`. Run installs this wrapper through the public [Catalog assembly](../catalog/README.md) interface after all mechanisms are assembled.

| Operation | Standard behavior |
|---|---|
| Read/write workspace files | Allow, except protected targets |
| External files | Request user confirmation; exact-call or operation-specific directory approval |
| Known credential paths, `.env`, `.env.*`, `secrets.env` | Deny file-tool access; `.env.example`, `.env.sample`, `.env.template` are examples |
| Current Session file | Readable; model file tools cannot write it |
| Algorithm configuration, learning state, candidates | Ordinary authorized files; not categorically blocked |
| Delete or move | Explicit confirmation, with all declared targets checked |
| Shell/IPython | Explicit local-execution confirmation; optional runtime-session approval |
| Undeclared custom tool operation | Deny |

The wrapper checks canonical targets at actual file access, including both move targets. A symlink retargeted after approval needs a new grant. Grants expire when the authorized call exits, including inherited asynchronous contexts. Temporary files stay in the workspace's `.fruitfly/tmp` directory. Local shell commands and their working directory must match the approved call.

`PermissionPolicy(workspace, read_roots=(), write_roots=(), sensitive_paths=(), readonly_paths=())` is host-owned. Read roots do not grant writes; writes permit the associated reads needed for edits. Registered credential paths are also checked for existing hard-link aliases. All explicit roots and protection paths are normalized. The host must identify credential locations; this is not a scanner for secrets in arbitrary files.

Children receive a minimal environment: a system `PATH` and selected locale/timezone/terminal variables. IPython additionally receives its package and artifact transport settings. Provider key variables and ambient `HOME`, `PYTHONPATH`, and startup configuration are not inherited automatically. Explicit host-supplied execution options can add environment values and are trusted.

These controls protect model tool entry points. They are not OS isolation: approved local code can access host files/network with current user permissions, and arbitrary trusted plugin code can use Python APIs directly. Canonical path checks do not eliminate all concurrent filesystem races. No containers, automatic command parsing, permanent approvals, or shell command blacklists are supplied.
