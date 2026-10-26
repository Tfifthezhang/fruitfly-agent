# Execution Environments

[Up: Lab](../README.md)

`LocalEnv` accesses the host filesystem and runs local shell commands through Core's execution contracts.

Choose **Local environment** to execute on the machine or container running the
Agent. Select [Remote environment](ssh/README.md) to run file and Bash
tools on an external server through SSH. It supports configurable host/port, remote paths,
password authentication through the host secret environment, verified host keys,
and remote process supervision. Local sessions and model calls stay local.

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
| [description.py](description.py) | Immutable execution description published through Catalog for host presentation |
| [permissions.py](permissions.py), [guarded.py](guarded.py) | Guarded host strategy, authorizer and environment wrapper |
| [execution.py](execution.py) | Explicit unrestricted strategy and allow authorizer |
| [ssh](ssh/README.md) | `SshConfig`, `SshEnv`, remote permissions and Catalog registration |
| [__init__.py](__init__.py) | Public exports |
| [Core protocols](../../core/env/protocols.py) | Required filesystem and shell operations |

Implement `ExecutionEnv` for another backend. Document paths, symlinks, encoding, environment inheritance, permissions, output, timeout, and cleanup. Register backend resources once through [Catalog](../catalog/README.md); tools share the injected backend. Container and read-only backends are extension options, not built-in capabilities.

Environment installers publish an `ExecutionEnvironmentDescription` under
`EXECUTION_ENVIRONMENT_COMPONENT`; both are host-facing exports of
[Catalog](../catalog/README.md#describe-the-execution-environment). The view carries
only a label, actual execution directory and optional server address. Local and
SSH installers supply it from their installed backend. It is presentation metadata,
independent of permission wrapping and Session/runtime identity schemas.

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
| Declared `network_read` tools | Allow when host-owned `allow_network=True` (default); otherwise deny before execution |
| Undeclared custom tool operation | Deny |

The wrapper checks canonical targets at actual file access, including both move targets. A symlink retargeted after approval needs a new grant. Grants expire when the authorized call exits, including inherited asynchronous contexts. Temporary files stay in the workspace's `.fruitfly/tmp` directory. Local shell commands and their working directory must match the approved call.

`PermissionPolicy(workspace, read_roots=(), write_roots=(), sensitive_paths=(), readonly_paths=(), allow_network=True)` is host-owned. Read roots do not grant writes; writes permit the associated reads needed for edits. Registered credential paths are also checked for existing hard-link aliases. All explicit roots and protection paths are normalized. The host must identify credential locations; this is not a scanner for secrets in arbitrary files. Network-read policy is recorded in permission identity version `local-permissions-v2`; it does not restrict Providers, live context sources, approved local code or arbitrary trusted plugins. Existing policy callers default to allowing selected network-read tools.

Children receive a minimal environment: a system `PATH` and selected locale/timezone/terminal variables. IPython additionally receives its package and artifact transport settings. Provider key variables and ambient `HOME`, `PYTHONPATH`, and startup configuration are not inherited automatically. Explicit host-supplied execution options can add environment values and are trusted.

These controls protect model tool entry points. They are not OS isolation: approved local code can access host files/network with current user permissions, and arbitrary trusted plugin code can use Python APIs directly. Canonical path checks do not eliminate all concurrent filesystem races. No containers, automatic command parsing, permanent approvals, or shell command blacklists are supplied.

## Select an execution strategy

`PermissionPolicy` implements the guarded strategy through `prepare_environment`
and `bind`. `PermissionPolicy.unrestricted(workspace)` returns
`UnrestrictedExecutionPolicy`: environment preparation preserves task variables,
binding retains the backend and supplies an explicit allow authorizer. It does
not invoke `with_permissions` adapters or enforce directory/credential/Session
checks. Core still validates tool calls; timeout, cancellation and cleanup retain
their owning implementations. Authorization audits omit arguments and key values.

Run selects the strategy once at startup. Eval explicitly selects unrestricted
execution inside Harbor/Docker; it is independent of Agent YAML and never inferred
from Docker detection. The manifest records `unrestricted-execution-v1` and the
inherited environment. External isolation must bound its effects. See
[host execution](../../../CONFIGURATION.md#host-execution-policies).
