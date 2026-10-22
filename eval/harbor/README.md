# Prepared Harbor Execution

[Up: Eval](../README.md)

Own machine settings, runtime and task preparation, dependency assets, environment
probes and cancellation. Benchmark adapters declare datasets and selections.
This package has no Terminal-Bench version or server-specific paths.

## Configure a machine

Copy [eval-host.example.yaml](../../examples/configuration/eval-host.example.yaml)
to `.fruitfly/eval-host.yaml` if absent. It is separate from the Agent's default
configuration, models and secret environment. `--host-config` selects another
machine file. Preparation records contain these settings, so use credential-free
URLs and keep key values in the existing secret environment.

| Field | Meaning |
|---|---|
| `schema_version` | Required integer `1` |
| `cache` | Host directory for frozen material, probes and package caches |
| `agent.python` | Absolute Python executable path inside the container |
| `agent.mounts` | Required read-only `source`/optional `target` binds; target defaults to source |
| `agent.library_paths` | Optional mounted library directories, joined as `LD_LIBRARY_PATH` |
| `environment.setup / agent / verifier` | Non-secret phase-specific variables; credentials are rejected |
| `task_directory` | Optional exported task or directory of task directories; otherwise use Harbor's public dataset API |
| `dependencies.assets` | Explicit `url`, relative `path`, exact `sha256`, optional boolean `executable` |
| `dependencies.uv` | Optional absolute path to a declared executable asset under `/opt/fruitfly-eval-dependencies/assets/` |
| `dependencies.prepare` | Explicit cached `image` and single-line shell `command` for dependency preparation |
| `dependencies.offline` | Set uv/pip offline variables during evaluation; preparation remains online |
| `task_patches` | Optional exact `task` pattern, `tests/` file `path`, `old` and `new` setup text |

Host paths resolve relative to the host YAML. Host paths and container runtime
paths expand process environment variables and reject unresolved variables.
Phase environment values are literal strings. Relative task paths do not refer
to Harbor's private cache. Export the necessary task definitions explicitly.
Runtime import/library variables and dependency cache/offline variables are owned
by their dedicated settings and cannot be overridden by a phase mapping.

Use a complete **Linux** Python installation and a dedicated environment with
the project's runtime dependencies installed once on the evaluation server.
The host interpreter used by Harbor must also satisfy Harbor's Python 3.12+
requirement. Preserve absolute symlink targets and Python installation paths
inside containers. Mount any required OpenSSL or other shared libraries as
additional read-only directories. A macOS venv cannot serve as a Linux runtime.
Task-specific packages belong in the task container, outside the shared Agent
environment. Do not mount the entire checkout or an environment containing
credentials, Sessions or research state.

## Prepare, check and run

```bash
# Placeholder paths: replace with the complete server installations.
export FRUITFLY_EVAL_PYTHON_ROOT=/absolute/path/to/python
export FRUITFLY_EVAL_VENV=/absolute/path/to/agent-venv

# Network and containers: resolves tasks, probes environments and warms declared caches.
# No Agent/model requests or verifier scoring assertions are executed.
.venv/bin/python -m eval prepare --request .fruitfly/eval-request.json

# No downloads, installs, environment creation or model calls.
.venv/bin/python -m eval check --request .fruitfly/eval-request.json

# Starts Agents and official verifiers; model requests may incur charges.
.venv/bin/python -m eval run --request .fruitfly/eval-request.json --events jsonl
```

Preparation hashes mounted runtime files, resolved links and source/wheel inputs.
Only package Python and declared build/license files enter the source snapshot.
It freezes the exact selected tasks outside Harbor's private cache. Explicit
setup replacements must match once; each applied diff is recorded. Original
task files remain untouched. Restrict replacements to dependency/bootstrap
operations; changing assertions or rewards changes the evaluation condition.

Prebuilt Linux images are probed with networking disabled. Dockerfile and Compose
environments use Harbor's public environment factory, including its startup
behavior, then are deleted. Preparation may build images or start task services;
it does not run the Agent or verifier. Probes import the runtime, SSL, SQLite,
compression, native extensions and Provider dependencies, and record versions
and actual image identities. Task environment CPU, memory, timeout and network
declarations remain Harbor's responsibility during trials.

`check` validates all frozen contents, links and local image identities against
the recorded probes. It never pulls a missing image. Moving a symlink, modifying
the runtime or retagging an image requires `prepare` again. Changing current
checkout source alone does not update an already frozen Agent; prepare again to
evaluate that source. Keep runtime directories stable while jobs are active.
Mounts are read-only inside containers; they are not immutable on the host.
Concurrent preparation of the same cache is unsupported.

## Prepare verifier dependencies separately

Dependency assets accept credential-free HTTPS or local `file:` URLs and require
exact SHA-256 values. A local, already downloaded uv binary can be an executable
asset. Its container path and parent directory are then available to explicit
preparation commands and verifier scripts. URLs can change without code edits;
replacement bytes must match the declared checksum.

| Container path | Access / ownership |
|---|---|
| Runtime mount targets | Read-only Agent interpreter, dependencies and libraries |
| `/installed-agent/fruitfly/source` | Read-only frozen Agent source |
| `/installed-agent/fruitfly/runtime` | Per-trial configuration and immutable input copies |
| `/opt/fruitfly-eval-dependencies/assets` | Read-only checksum-verified binaries/assets |
| `/opt/fruitfly-eval-dependencies/cache` | Writable uv, Python download and pip caches |

Preparation recipes use the declared image's recorded identity and save complete
output in `dependencies/prepare-<index>.log`. Successful recipes are reused for
the same asset/recipe/image/environment identity. Warm the exact verifier package
versions for each required Python/platform. Shared caches do not install packages
into task environments. They use package-manager locks and retain no task
answers or learning state. Agent imports do not depend on the task's Python.

`UV_CACHE_DIR`, `UV_PYTHON_INSTALL_DIR` and `PIP_CACHE_DIR` reach task setup and
verification explicitly. Agent-specific values are passed only to the Agent.
The host secret file is not a general phase environment file. Verifier scripts
that download a bootstrap tool directly need an explicit reviewed setup
replacement to use the pinned asset. There is no automatic mirror rewrite.

Offline flags cover uv/pip, not apt, curl, custom downloaders or task services.
Asset and cache checks cannot establish that all verifier dependencies exist.
`check` therefore leaves verifier execution and model connectivity **unverified**.
A complete real smoke trial supplies that evidence. A different task/Python
version can require additional cache preparation.

## Stop and inspect ownership

```bash
.venv/bin/python -m eval stop '<EVALUATION_ID>' --output-root .fruitfly/eval
```

The runner owns a separate process group, a tokenized stop record and the Compose
projects recorded by its trials. Normal return, whole-job timeout, Ctrl+C,
SIGTERM and `stop` terminate the owned process group and retire remaining exact
project containers, networks and volumes. `resources.json` records removed
identifiers. Unrelated jobs are not selected by process-name patterns.
Cleanup errors remain explicit and keep live event files unarchived.

The Linux container supervisor owns the CLI and adopts detached descendants.
Cancellation stops those processes and confirms cleanup before returning to
Harbor; failed confirmation stops the task environment. Normal CLI completion
preserves task-created background services for verification. Stop tokens handle
cancellation during startup, and PID start identities reject PID reuse.
SIGKILL, host/Engine failure and lost control records cannot guarantee cleanup;
`stop` reports unconfirmed state if its owner is gone. Inspect the saved job's
exact trial/project identities before manual cleanup. A pending stop request is
not confirmation.

## Files and checks

| Module | Public entry points / responsibility |
|---|---|
| [host.py](host.py) | `HostConfig.read`: strict machine configuration |
| [material.py](material.py) | `prepare_material`, `check_material`: source/runtime identities |
| [tasks.py](tasks.py) | `prepare_tasks`, `validate_coverage`: frozen selections and all-run coverage |
| [dependencies.py](dependencies.py) | `prepare_dependencies`, `check_dependencies`: assets and caches |
| [environments.py](environments.py) | `probe_environment`: prebuilt images and public Harbor environment factory |
| [preparation.py](preparation.py) | `prepare`, `inspect`, `load_preparation`: shared readiness |
| [docker.py](docker.py) | `run_container`: bounded preparation-container retirement |
| [supervisor.py](supervisor.py), [lifecycle.py](lifecycle.py) | Container Agent and host job ownership |
| [diagnostics.py](diagnostics.py) | Phase evidence and additional qualified traceback exceptions |

The [adapter guide](../DEVELOPER_GUIDE.md#add-a-benchmark) describes registration.
This implementation targets Linux Docker tasks on a local Docker daemon.
Remote Docker daemons need equivalent bind paths and are unverified. Other Harbor
backends and Windows task containers are not implemented here. Tasks declaring a
separate verifier environment are rejected during preparation: Harbor 0.23.0
does not forward the configured dependency mounts into that separate environment.
That capability needs an integration extension rather than silently repeating
downloads without the prepared cache. A different
Linux benchmark reuses these modules; no TB-specific installation branches exist.

```bash
.venv/bin/python -m unittest tests.eval.test_preparation tests.eval.test_harbor_lifecycle -v
```

These tests are offline. The real `/proc` process test runs only on Linux;
macOS runs the ownership doubles and local host-process tests.
