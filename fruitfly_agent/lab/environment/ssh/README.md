# Use a remote environment through SSH

[Up: Execution Environments](../README.md)

`SshEnv` implements Core's `ExecutionEnv` using SSH command channels and SFTP.
In **Configure → Environment**, use Space to enable **Remote environment**, or expand it
and choose **Set up…**. The guided form asks for the server address, port, remote
directory, local host-key file, hidden account and hidden password, then shows
a review. Choose **Stage settings**, return to startup and save/start a new session.
Selection disables the local environment, local IPython and file memory only
after staging. Cancelling the form preserves the previous environment.
Configuration and construction are offline; Application startup opens the
connection. Authentication failure prevents activation.

After saving once, selecting Remote environment again reuses the server settings and stored
credentials without reopening the form. Unchecking it or selecting the local
environment retains them, including across restarts in the same workspace and
profile. Missing settings or credentials reopen setup; choose **Set up…** explicitly
to edit complete settings. Staged settings are also reused within the current
configuration draft. Exiting without saving still discards new draft values.

## Prepare the server and client

The server needs Linux/POSIX, password authentication, SFTP, `/bin/bash` and
`python3` in its SSH command PATH. Create the remote working directory first.
The small process supervisor is sent over SSH for each command; no daemon or
FruitFlyAgent installation is needed on the server.

Install the optional client dependency (downloads packages):

```bash
.venv/bin/python -m pip install -e '.[ssh]'
```

Use your normal SSH client to verify the server fingerprint through a trusted
source and record its key in a local OpenSSH `known_hosts` file. Nondefault
ports use OpenSSH's `[host]:port` entry format. Unknown or changed keys are
rejected. The backend never automatically accepts or saves host keys. See
[Paramiko host-key and password authentication contracts](https://docs.paramiko.org/en/stable/api/client.html).

## Configure addresses and secrets

Merge the following entries into the selected profile's `mechanisms` in
`.fruitfly/config.yaml`. Preserve unrelated model and mechanism settings.
`server.example`, `2222` and `/srv/workspace` are placeholders. A complete minimal
profile is in the [SSH configuration template](../../../../examples/configuration/ssh.example.yaml).

```yaml
- id: local-env
  enabled: false
- id: memory-files
  enabled: false
- id: ipython-tool
  enabled: false
- id: rlm-ipython
  enabled: false
- id: ssh-env
  enabled: true
  parameters:
    host: server.example
    port: 2222
    cwd: /srv/workspace
    username_env: FRUITFLY_SSH_USERNAME
    password_env: FRUITFLY_SSH_PASSWORD
    known_hosts: ~/.ssh/known_hosts
```

Keep `read-tool`, `write-tool`, `edit-tool` and `bash-tool` enabled. They share the
remote backend. The guided form collects account/password values with terminal
echo and input history disabled. Review and status show only entered, reused,
set or missing; they never show authentication values. Blank input reuses an
existing credential. Missing values and invalid fields are retried in place.
An already enabled SSH selection with missing setup information opens the form
when starting a new session, before runtime construction. The expanded menu also
offers **Set up…** for editing or repairing the selected environment.

Only **Stage settings** changes the draft. Saving configuration writes credentials
to the same workspace-local secret file as API keys with owner-only permissions;
process environment values keep precedence. Cancel, EOF or configuration discard
leaves the new credentials unsaved. Model and mechanism forms share one credential
draft and save transaction. Ordinary save failures restore written files and keep
the draft for retry. A different value in an already set variable is rejected;
reuse it or choose another variable name in configuration. Host keys are never
automatically trusted or fetched by the form.

For manual setup, use the [secret template](../../../../examples/configuration/.env.example):

```dotenv
# In the local workspace's .fruitfly/secrets.env; placeholders only.
FRUITFLY_SSH_USERNAME=your-account
FRUITFLY_SSH_PASSWORD=your-password
```

Use the same secret-file format, process-environment precedence and selected
workspace rules as [API keys](../../../../CONFIGURATION.md#files-and-precedence).
Restrict the local secret file with `chmod 600 .fruitfly/secrets.env`.
`.fruitfly/`, `.env`, `.env.*` and `secrets.env` are ignored by the repository;
source distributions exclude local secrets too. Never force-add credential files.
Git ignore rules do not remove files previously tracked by a user.

| Parameter | Default / behavior |
|---|---|
| `host` | Required hostname, IPv4 or unbracketed IPv6 address; account and port are separate |
| `port` | 22; integer 1–65535 |
| `cwd` | `/srv/workspace`; existing absolute POSIX path on the server |
| `username_env`, `password_env` | `FRUITFLY_SSH_USERNAME`, `FRUITFLY_SSH_PASSWORD`; distinct secret variable names |
| `known_hosts` | `~/.ssh/known_hosts`; local path, relative paths use the local workspace |
| `connect_timeout_seconds` | 15; deadline for each connection/authentication phase |
| `operation_timeout_seconds` | 30; deadline for individual SFTP/channel operations |

Only the named username and password are supplied to SSH authentication. Local
SSH-agent and key-file discovery are disabled. Authentication values are not
added to commands, child environments, prompts, manifests, Session records or
backend error messages. Transport diagnostic logging is suppressed. Rotating a
credential does not serialize its value into runtime identity. Server identity
(host/port), remote directory and variable names are recorded. Avoid embedding
credentials in addresses, directory names or task text. Ordinary remote file
contents and command output are returned to the model and recorded normally;
this backend does not scan or redact arbitrary server data.

## Apply remote permissions

| Operation | Standard host behavior |
|---|---|
| Workspace read/write | Allow within the canonical remote working directory |
| External remote paths | Ask for operation-specific confirmation |
| Delete/move | Ask for confirmation, checking both move targets |
| Remote `.env`, `.env.*`, `secrets.env`, `.ssh` | Deny file-tool access; documented `.env` example names remain allowed |
| Bash | Ask for remote execution confirmation, naming the server and port |
| Temporary output | Remote `cwd/.fruitfly/tmp`; no local log fallback |
| Local extra roots, sensitive paths, Session path | Never interpreted as remote filesystem privileges or targets |

Remote symlinks are resolved through SFTP at authorization and actual access;
changing an approved link requires a new grant. Nonexistent paths are resolved
through existing parents. Network-read tool policy still follows the host's
`allow_network`. Bash starts with a minimal remote environment (system PATH plus
explicit host-supplied values), never the client's ambient environment or its
Provider/SSH secrets. Direct backend callers can request remote environment
inheritance with `ExecOptions.inherit_env`; standard Run disables it.

Permissions are lightweight tool checks, not a sandbox. Approved remote Bash
can access everything permitted to that account, including remote secrets and
network. Hard-link aliases of remote secrets and concurrent filesystem changes
are not fully protected. Use a dedicated server account or server-side isolation
when needed. Trusted Python plugins still run locally with host privileges.

## Understand execution and recovery

| Behavior | Contract / limit |
|---|---|
| Shell | Each invocation starts `/bin/bash -c`; no PTY or interactive stdin; shell state does not persist |
| Output | Separate stdout/stderr, incremental UTF-8 decoding and async callbacks; ordinary callback failures are isolated |
| Timeout | Client cancellation plus a server-side supervisor deadline; returns `ExecResult.cancelled=True` when confirmed |
| Task cancellation | Send cancellation, briefly drain/reap, close the channel and propagate `CancelledError` |
| Disconnect | Supervisor kills its process group when SSH stdin closes; network partitions can delay EOF; cleanup cannot be guaranteed |
| Detached jobs | Processes that deliberately leave the supervised process group may survive |
| Transport failure | Return failure without retrying a potentially completed command or file mutation |
| Connection lifecycle | Owned by Application; failed startup/assembly and runtime retirement close resources |
| Recovery | Open a fresh connection with current configuration/secrets and record current identity; no remote filesystem snapshot or rollback |
| File operations | Synchronous SFTP with per-operation deadlines; large file/path operations can block the event loop |
| Memory use | Complete files and command stdout/stderr are retained in memory |

Sessions, model calls, skills, knowledge and learned context stay local. Files
are not synchronized. Local IPython/RLM and local file memory are incompatible
with this backend and rejected by Catalog. Other local context text may still
mention local paths; use explicit remote paths in tasks. Original-task
experiments are blocked because the SSH workspace has no isolated frozen task
snapshot. Offline checks do not establish real server compatibility.

## Files and offline checks

| File | Responsibility |
|---|---|
| [config.py](config.py) | Non-secret settings and validation |
| [environment.py](environment.py) | `SshEnv`, SFTP, connection lifecycle and streaming commands |
| [supervisor.py](supervisor.py) | Remote process-group supervision and cancellation |
| [permissions.py](permissions.py) | Remote path authorization and guarded temporary output |
| [registration.py](registration.py) | Catalog definition, secret injection and compatibility |
| [__init__.py](__init__.py) | Public `SshConfig` and `SshEnv` exports |

```bash
.venv/bin/python -m unittest tests.lab.test_ssh_env tests.run.test_ssh_environment -v
```

Tests use fake SSH/SFTP connections and local subprocesses for the transmitted
supervisor. They make no network connections and use no real credentials.
