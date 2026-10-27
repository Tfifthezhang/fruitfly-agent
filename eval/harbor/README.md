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

Library directories must be covered by runtime mounts.
Host paths resolve relative to the host YAML. Host paths and container runtime
paths expand process environment variables and reject unresolved variables.
Phase environment values are literal strings. Relative task paths do not refer
to Harbor's private cache. Export the necessary task definitions explicitly.
`task_directory` accepts one task or immediate `<task>/task.toml` children;
nested revision caches require a flat export or registry resolution.
Runtime import/library variables and dependency cache/offline variables are owned
by their dedicated settings and cannot be overridden by a phase mapping.

## Inspect selection before starting containers

All datasets share `smoke`, `no_gpu` and `full`. The public Harbor resolver supplies
effective Agent/Verifier/step definitions. `no_gpu` excludes tasks declaring GPUs
or GPU types in any role and checks Compose auxiliary-service GPU requests.
External Compose includes or service inheritance are excluded conservatively.
Scripts can have undeclared resource needs; filtering cannot prove their absence.
Selection records include source scope, resolved count, exact selected IDs and
excluded IDs/reasons. Local exports do not establish full official coverage.

`prepare --tasks-only` freezes task copies and writes `selections/<key>.json`
with full local image lookups and declared builds. It downloads task definitions
when needed but never pulls/builds images, starts containers, prepares the Agent
runtime or calls models. Review it before fetching images or preparing large jobs.
A matching tag is not proof of a locally resolvable repository digest. Preserve
full references and check every effective role and Compose service. Harbor auxiliary
images and dynamic build inputs are outside this static inventory.

Use a complete **Linux** Python installation and a dedicated environment with
the project's runtime dependencies installed once on the evaluation server.
The host interpreter used by Harbor must also satisfy Harbor's Python 3.12+
requirement. Old-host wheel compatibility is separate from container runtime
compatibility; a venv does not replace glibc. Inspect existing installations before
resolving dependencies. `controller.environment_snapshot` records Python, libc,
installed versions and declared dependency conflicts without importing clients or
saving environment values. Conflicts remain visible as unverified readiness.
The controller environment must match its preparation before a run. Preserve absolute symlink targets and Python installation paths
inside containers. Mount any required OpenSSL or other shared libraries as
additional read-only directories. A macOS venv cannot serve as a Linux runtime. Inspect extension-module
dependencies too; a static main executable is not proof of a self-contained runtime.
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
.venv/bin/python -m eval prepare --request .fruitfly/eval-request.json --tasks-only
.venv/bin/python -m eval prepare --request .fruitfly/eval-request.json

# No downloads, installs, environment creation or model calls.
.venv/bin/python -m eval check --request .fruitfly/eval-request.json

# Starts Agents and official verifiers; model requests may incur charges.
.venv/bin/python -m eval run --request .fruitfly/eval-request.json --events jsonl
```

Full preparation hashes mounted runtime files, resolved links and source/wheel inputs.
Only package Python and declared build/license files enter the source snapshot.
It freezes the exact selected tasks outside Harbor's private cache. Explicit
setup replacements must match once; each applied diff is recorded. Original
task files remain untouched. Restrict replacements to dependency/bootstrap
operations; changing assertions or rewards changes the evaluation condition.

The preparation receipt also records controller identity and task selection.
Preparation records use schema 3. Missing or incompatible preparation records require
`prepare` again; request and machine-file formats are unchanged. Each record covers
the Agent environment and every effective separate verifier, including multi-step
overrides. Configuration inheritance uses Harbor's public resolver. Separate
verifier build contexts come from `tests/` or an existing `steps/<name>/tests/`.
Shared verifiers continue to use the Agent environment.

Prebuilt Linux Agent images are probed with networking disabled. Dockerfile,
Compose and separate-verifier environments use Harbor's public environment
factory, then their live resources are retired while images remain cached.
Preparation may build images or start task services; it does not run the Agent
or scoring assertions. Agent probes import the runtime, SSL, SQLite, compression,
native extensions and Provider dependencies. Both roles check asset access and
cache writes using the declared execution user. Verifier probes do not import
the Agent or require its Python installation. Records retain each role, step,
build context, effective resource configuration and actual image identities.
Verifier definitions and build-context contents participate in probe identities.
Task resource, timeout and network declarations remain Harbor's responsibility
during trials; probes do not establish complete phase-network or resource compliance.

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
| Runtime mount targets | Agent only: read-only interpreter, dependencies and libraries |
| `/installed-agent/fruitfly/source` | Agent only: read-only frozen Agent source |
| `/installed-agent/fruitfly/runtime` | Agent only: per-trial configuration and immutable input copies |
| `/opt/fruitfly-eval-dependencies/assets` | Both roles: read-only checksum-verified binaries/assets |
| `/opt/fruitfly-eval-dependencies/cache` | Both roles: writable uv, Python download and pip caches |

The public `environment.import_path` extension in [docker_environment.py](docker_environment.py)
appends dependency mounts to each Harbor-created environment. Agent runtime mounts
remain in Harbor's role-specific Agent mount list. The extension does not infer
roles from names or change artifact transfer, test upload or scoring. Model keys
remain in the installed Agent's environment; separate verifiers receive none of
those credentials. Harbor's built-in Docker implementation still owns Compose,
image selection, resource enforcement and network policies.

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
projects recorded by its trials. The environment extension records exact sessions
under each trial's `fruitfly-environments/` before startup, outside container-mounted
log paths. This covers separate verifiers and shortened multi-step session names.
Normal return, whole-job timeout, Ctrl+C,
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
| [tasks.py](tasks.py) | `prepare_tasks`, `validate_coverage`: frozen selections, exclusions and all-run coverage |
| [selection.py](selection.py) | `task_requirements`, `inspect_images`: effective resources, Compose services and exact local image checks |
| [controller.py](controller.py) | `environment_snapshot`: installed controller identity and declared dependency conflicts |
| [dependencies.py](dependencies.py) | `prepare_dependencies`, `check_dependencies`: assets and caches |
| [environments.py](environments.py) | `probe_environment`: prebuilt images and public Harbor environment factory |
| [docker_environment.py](docker_environment.py) | `PreparedDockerEnvironment`: dependency mounts and exact ownership through Harbor's public environment plugin |
| [preparation.py](preparation.py) | `prepare`, `inspect`, `load_preparation`: shared readiness |
| [docker.py](docker.py) | `run_container`: bounded preparation-container retirement |
| [supervisor.py](supervisor.py), [lifecycle.py](lifecycle.py) | Container Agent and host job ownership |
| [diagnostics.py](diagnostics.py) | Phase evidence and additional qualified traceback exceptions |

The [adapter guide](../DEVELOPER_GUIDE.md#add-a-benchmark) describes registration.
This implementation targets Linux Docker tasks on a local Docker daemon.
Remote Docker daemons need equivalent bind paths and are unverified. Other Harbor
backends and Windows task containers are not implemented here. Shared and separate
verifiers use the same prepared dependency contract. A different Linux benchmark
reuses these modules; no benchmark-name or version branches select execution behavior.
Compatibility with real images, GPU scheduling and complete verifier execution
still requires a smoke trial on the evaluation host.

```bash
.venv/bin/python -m unittest tests.eval.test_preparation tests.eval.test_verifier_environments tests.eval.test_harbor_lifecycle -v
```

These tests are offline. The real `/proc` process test runs only on Linux;
macOS runs the ownership doubles and local host-process tests.
