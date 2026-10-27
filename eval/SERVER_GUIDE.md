# Server Evaluation Guide

[Up: Eval](README.md)

Prepare one reusable controller environment and one reusable Agent runtime, then
select a Harbor dataset and validate its task environments. This procedure is
shared by every registered benchmark. Dataset identities and smoke tasks belong
to [benchmark declarations](benchmarks/TASKS.md), not machine configuration.

Run commands on the Linux evaluation server unless marked **Local computer**.
Replace uppercase placeholders before execution. Reuse existing validated files
and environments; do not overwrite them or update environments used by active jobs.
Installation and preparation can download files, build images and start containers.
Only `run` invokes the Agent and official verifier and can incur model charges.

For a fresh public-template setup and candidate search through the independent
experiment CLI, see [experiment examples](../examples/experiments/README.md#start-a-remote-linux-benchmark-experiment).
Its `init` command generates editable request/host/default files without private
configuration transfer. This guide also covers reusable environment preparation
and fixed-version evaluation independently of search.

## 1. Inspect the server before installing

| Layer | Responsibility | Reuse |
|---|---|---|
| Controller | Project, Eval CLI, pinned Harbor and its dependencies | Across supported Harbor datasets |
| Agent runtime | Complete Linux Python, dedicated Agent venv and required libraries | Across task images that pass probes |
| Task environments | Dataset definitions, Agent/Verifier images, services and task dependencies | According to exact task and image identities |

Record existing Python/venv paths, installed versions and whether a venv inherits
system site-packages. Missing `fruitfly_agent` alone does not mean all dependencies
must be reinstalled. A macOS venv cannot be used as a Linux runtime.

```bash
uname -m
getconf GNU_LIBC_VERSION
uv --version
docker context show
docker info
docker compose version
df -h .
# Replace this path with an existing interpreter; no packages are changed.
/ABSOLUTE/PYTHON -c 'import sys,ssl; print(sys.version); print(sys.executable); print(sys.base_prefix); print(ssl.OPENSSL_VERSION)'
uv pip list --python /ABSOLUTE/PYTHON
```

Harbor requires Python 3.12+; the Agent requires Python 3.11+. Python version and
system glibc compatibility are separate requirements. A venv does not replace
glibc. A wheel's `manylinux_2_28` tag requires glibc 2.28 or newer; an older host
may fall back to a source build that requires compilers and additional downloads.
See [wheel compatibility tags](https://packaging.python.org/en/latest/specifications/platform-compatibility-tags/).

Check connectivity to the actual Git remote, Python distribution host, package
index, Harbor dataset service, image registry and model endpoint separately.
DNS/TCP success does not establish HTTPS/download success. Keep certificate
verification enabled. Configure a trusted index or proxy according to your server
policy; do not assume one public mirror works on every machine.

| Client | Configuration boundary |
|---|---|
| pip | pip configuration and `PIP_INDEX_URL` |
| uv | uv configuration or `UV_DEFAULT_INDEX`; it does not read `pip.conf` |
| Git | Git remote/proxy configuration |
| Docker pulls | Selected daemon's registry/proxy settings |
| Task downloads | Task/Verifier environment and their own installers |

See [uv configuration differences](https://docs.astral.sh/uv/pip/compatibility/)
and [certificate settings](https://docs.astral.sh/uv/concepts/authentication/certificates/).
If needed, set `UV_DEFAULT_INDEX` to your approved credential-free index URL
before installation. Configure credentials privately, not in YAML, requests or logs.

For rootless Docker, verify the selected context and socket as the evaluation user
in the same shell used by automation. Set `DOCKER_HOST` only when selecting your
actual socket; do not replace a working context blindly. Host shell proxy settings
do not automatically configure daemon pulls or container downloads.

## 2. Obtain the project and private configuration

Clone the project into your chosen directory, or reuse an existing checkout:

```bash
git clone https://github.com/Tfifthezhang/fruitfly-agent.git
cd fruitfly-agent
umask 077
mkdir -p .fruitfly
chmod 700 .fruitfly
```

Create the remote directory before transferring files. **Local computer:** replace
`USER`, `SERVER` and `/ABSOLUTE/PROJECT` with your destination:

```bash
scp .fruitfly/secrets.env \
    .fruitfly/default-config.yaml \
    .fruitfly/models.yaml \
    USER@SERVER:/ABSOLUTE/PROJECT/.fruitfly/
```

| File | Required content |
|---|---|
| `.fruitfly/default-config.yaml` | Selected evaluation harness profile using local task execution |
| `.fruitfly/models.yaml` | Model/protocol/endpoint settings and credential variable names |
| `.fruitfly/secrets.env` | Actual model and enabled-tool credential values |
| `.fruitfly/eval-host.yaml` | Server-specific paths, mounts and dependency preparation |
| `.fruitfly/eval-smoke.json`, `.fruitfly/eval-selected.json` | Dataset selection and execution budgets |

Transfer `.fruitfly/config.yaml` only for optional daily interaction; daily and
Eval configs can select different aliases from the same `.fruitfly/models.yaml`.
Eval defaults to the independent default configuration and never falls back to
daily settings. Transfer its referenced component files too. Copy exact `.fruitfly/artifacts/<hash>` files if the
profile references immutable `sha256:` bindings. Arbitrary memory, Skills and host
workspace files are not copied into tasks.

**Server:** verify filenames and permissions without printing keys:

```bash
chmod 700 .fruitfly
chmod 600 .fruitfly/secrets.env
```

If defaults do not exist yet, use the public
[configuration templates](../examples/configuration/README.md), preserving existing
files. Model catalogs contain `api_key_env` names, not key values. Process variables
win over the secret file. Inspect conflicting exports without printing their values.

## 3. Establish and freeze the two Python environments

Install missing prerequisites using your server's supported process. The examples
assume [uv](https://docs.astral.sh/uv/getting-started/installation/) is on `PATH`.
Choose a dedicated, complete Linux Python installation; avoid mounting `/usr`,
`/usr/local`, a whole Conda installation or the project checkout into task paths.

Choose the runtime directory for either installation route:

```bash
umask 022
export FRUITFLY_EVAL_ROOT="$HOME/fruitfly-eval-runtime"
```

If a suitable Python already exists, set `FRUITFLY_EVAL_BASE_PYTHON` to its absolute
executable path. Otherwise, the following optional download creates one:

```bash
export UV_PYTHON_INSTALL_DIR="$FRUITFLY_EVAL_ROOT/python"
uv python install 3.12
export FRUITFLY_EVAL_BASE_PYTHON="$(uv python find --managed-python --system 3.12)"
```

For either route, keep the same shell and derive the actual base installation:

```bash
export FRUITFLY_EVAL_PYTHON_ROOT="$("$FRUITFLY_EVAL_BASE_PYTHON" -c 'import sys; print(sys.base_prefix)')"
export FRUITFLY_EVAL_VENV="$FRUITFLY_EVAL_ROOT/agent-venv"
```

Inspect existing `.venv` and `agent-venv` before proceeding. For a **new** setup:

```bash
uv venv --python "$FRUITFLY_EVAL_BASE_PYTHON" .venv
uv pip install --python .venv/bin/python -e '.[benchmarks]'
uv pip check --python .venv/bin/python

uv venv --python "$FRUITFLY_EVAL_BASE_PYTHON" "$FRUITFLY_EVAL_VENV"
uv pip install --python "$FRUITFLY_EVAL_VENV/bin/python" --link-mode copy .
uv pip check --python "$FRUITFLY_EVAL_VENV/bin/python"
umask 077
```

For an existing validated installation, install only missing material using its
reviewed constraints, for example `uv pip install --python .venv/bin/python -c
.fruitfly/controller-versions.txt -e .`. Ordinary `-e .` does not install Harbor;
`.[benchmarks]` does. Never let a fresh resolution silently replace a validated
SDK stack. A resolver dry run does not prove builds, imports or task compatibility.

Harbor is pinned to `0.23.0`; its transitive dependencies are not pinned by the
project extra. On an old host, inspect the failing package, compatible wheels and
source-build requirements before changing versions or choosing another deployment
environment. A controller container is an alternative requiring Docker socket,
shared-path and kernel validation, not an automatic requirement.

**Dependency exceptions:** `--no-deps` bypasses declared requirements. A lower
version that runs one path still conflicts with package metadata. Do not make
such an override the standard installation procedure or hide dependency-check
failures. Record any reviewed exception, exact versions, reason and tested paths;
updates or other Harbor agents can invalidate it. Eval records declared conflicts
as `controller_dependencies: unverified`, even when a task completes.

After validation, save the actual installed versions separately for both layers:

```bash
uv pip freeze --python .venv/bin/python --exclude-editable > .fruitfly/controller-versions.txt
uv pip freeze --python "$FRUITFLY_EVAL_VENV/bin/python" --exclude-editable > .fruitfly/agent-versions.txt
.venv/bin/python - <<'PY'
import json
from pathlib import Path
from eval.harbor.controller import environment_snapshot
Path('.fruitfly/controller-environment.json').write_text(
    json.dumps(environment_snapshot(), indent=2) + '\n')
PY
```

Keep source URLs credential-free. Version lists are constraints, not complete
reproducible artifacts: retain the corresponding project source/wheel, Python build,
required libraries and approved package artifacts/checksums when rebuilding must
work offline. Update snapshots only after validating an intentional environment change.

### Check native libraries and certificates

Inspect trusted runtime binaries and extension modules, not just the Python main
executable. A static Python executable can still load dynamically linked modules.
For example, after setting the paths above:

```bash
ldd "$FRUITFLY_EVAL_BASE_PYTHON"
find "$FRUITFLY_EVAL_PYTHON_ROOT/lib" -name '*.so' -exec ldd '{}' \;
```

An older glibc build can be a useful compatibility baseline, but glibc ordering
alone does not prove compatibility. Architecture, loader, OpenSSL, libffi,
libstdc++, extension modules, absolute links and access permissions also matter.
Collect only the required trusted non-glibc libraries into a dedicated directory,
retain their provenance/checksums, mount that directory read-only and declare its
container path in `agent.library_paths`. Do not copy the whole system library tree
or replace a task's libc. The needed library set depends on the Python build.

Certificate behavior also differs between uv, Python and HTTP clients. Check the
runtime's CA paths and configure approved CA bundles when needed. Offline imports
cannot establish successful TLS or model authentication; the authorized smoke
provides actual endpoint evidence. The public preparation probe checks common
native modules and imports without making model requests.

## 4. Create the machine YAML

Create `.fruitfly/eval-host.yaml` once for this server. Reuse it across datasets.
This generator preserves existing files and uses the public host validator:

```bash
.venv/bin/python - <<'PY'
import os
from pathlib import Path
import yaml
from eval.harbor.host import HostConfig
workspace = Path.cwd().resolve()
target = workspace / '.fruitfly/eval-host.yaml'
if target.exists():
    raise SystemExit('Host file exists; review it without overwriting.')
python_root = Path(os.environ['FRUITFLY_EVAL_PYTHON_ROOT']).resolve()
runtime = Path(os.environ['FRUITFLY_EVAL_VENV']).resolve()
if not (python_root / 'bin').is_dir() or not (runtime / 'bin/python').is_file():
    raise SystemExit('Prepare the complete Python installation and Agent venv first.')
settings = yaml.safe_load(Path('examples/configuration/eval-host.example.yaml').read_text())
settings['cache'] = str(workspace / '.fruitfly/eval-cache')
settings['agent']['python'] = str(runtime / 'bin/python')
settings['agent']['mounts'] = [{'source': str(python_root)}, {'source': str(runtime)}]
with target.open('x') as handle:
    yaml.safe_dump(settings, handle, sort_keys=False)
HostConfig.read(workspace, target)
print(target)
PY
```

If additional libraries are needed, add their mount and container library path:

```yaml
# Illustrative fragment: replace every path; preserve the other runtime mounts.
agent:
  python: /ABSOLUTE/RUNTIME/agent-venv/bin/python
  mounts:
    - source: /ABSOLUTE/PYTHON
    - source: /ABSOLUTE/RUNTIME/agent-venv
    - source: /ABSOLUTE/RUNTIME/libraries
  library_paths:
    - /ABSOLUTE/RUNTIME/libraries
```

Host paths resolve relative to the YAML directory. Omitted mount targets preserve
the same absolute paths inside containers. Library paths must be covered by runtime
mounts. Keep the cache outside all runtime mounts and runtime files readable by the
task user, including directory traversal permissions. No credentials belong in this YAML.

Leave `task_directory` unset for Harbor's public dataset API. A local export must
contain `task.toml` or immediate `<task>/task.toml` children; a downloaded
`<task>/<revision>/task.toml` tree is not that export format. Export a flat collection
with unique task names, or use registry resolution. Local coverage is recorded as
`selection.source: local`; it does not establish official full-dataset coverage.

## 5. Choose a dataset and create the request JSON

```bash
.venv/bin/python -m eval catalog --json
# Replace the placeholder with an ID listed by catalog.
export FRUITFLY_BENCHMARK=REPLACE_WITH_CATALOG_ID
```

Every dataset uses exactly three lowercase selections:

| `benchmark.variant` | Selection |
|---|---|
| `smoke` | The declaration's one exact smoke task |
| `no_gpu` | Resolved tasks without GPU requests in any effective Agent/Verifier/step environment or Compose service |
| `full` | Every resolved task, retaining its official resources |

`no_gpu` resolves Harbor inheritance and checks auxiliary Compose services before
image inspection, builds or task startup. Tasks with external Compose includes or
service inheritance are conservatively excluded because local inspection cannot
establish the absence of GPU requirements. Review the recorded reasons. Scripts or
externally managed services can impose undeclared resource requirements; selection
does not prove otherwise. `full` does not require every task to use a GPU, and a
host `nvidia-smi` executable does not prove that task resource requirements are met.

Generate a smoke request with explicit reviewed budgets:

```bash
.venv/bin/python - <<'PY'
import json
import os
from pathlib import Path
from eval.catalog import builtin_catalog
from eval.contracts import EvaluationRequest
benchmark = os.environ['FRUITFLY_BENCHMARK']
builtin_catalog().get(benchmark)
request = EvaluationRequest.from_dict({
    'runtime': {'working_directory': str(Path.cwd().resolve())},
    'benchmark': {'id': benchmark, 'variant': 'smoke'},
    'execution': {'attempts': 1, 'concurrency': 1, 'timeout_seconds': 36000},
})
with Path('.fruitfly/eval-smoke.json').open('x') as handle:
    json.dump(request.to_dict(), handle, indent=2)
    handle.write('\n')
PY
```

The 36,000 seconds are an example whole-job cap, not a task timeout or price limit.
Choose a cap appropriate to the declared task limits and your budget. The cap does
not cover a preceding `prepare` command. Omitted runtime config/profile selects
`.fruitfly/default-config.yaml` and its default profile.

## 6. Validate configuration without model calls

```bash
.venv/bin/python - <<'PY'
from dataclasses import asdict
import os
from pathlib import Path
import tempfile
from fruitfly_agent.providers.config import load_env
from fruitfly_agent.providers.workspace import WorkspacePaths
from eval.contracts import EvaluationRequest
from eval.harbor.host import HostConfig
from eval.runtime import prepare_runtime
request = EvaluationRequest.read('.fruitfly/eval-smoke.json')
workspace = Path(request.runtime.working_directory).resolve()
HostConfig.read(workspace)
environment = {**load_env(WorkspacePaths(workspace).secret_file()), **os.environ}
with tempfile.TemporaryDirectory(prefix='fruitfly-config-check-') as directory:
    _, _, names = prepare_runtime(runtime=asdict(request.runtime),
        output_dir=Path(directory), environment=environment)
    print('Configuration valid; credential variables:', ', '.join(names))
PY
```

This validates request fields, profile/model references, required credential names
and immutable bindings. It does not contact the model. Eval rejects SSH execution
profiles: Agent tools must operate in the selected task environment.

## 7. Inspect task selection and local image references

```bash
.venv/bin/python -m eval prepare --request .fruitfly/eval-smoke.json --tasks-only
```

This can download task definitions and freezes selected task copies. It inspects
local image references but does not pull images, build images, prepare the Agent
runtime, invoke models or start containers. Output includes selected/excluded IDs,
GPU exclusion reasons, effective roles/steps, declared images, build contexts and
local image status. Inventory is saved under the configured cache's `selections/`.
It is not a completed preparation receipt.

Check exact `name:tag@sha256:digest` references, architecture and Agent/Verifier/
auxiliary-service coverage. A matching short tag or Docker image ID does not prove
that a declared repository digest is locally resolvable. `docker tag` alone does
not establish that identity. Use the exact trusted registry reference when fetching
missing images; preserve declared digests. Cached layers can be reused, but a pull
can still contact the registry and download metadata or missing layers. See
[Docker digest pulls](https://docs.docker.com/reference/cli/docker/image/pull/).

Review `builds` and task resources before full preparation. Prebuilt role images
can avoid their builds; Dockerfile-only definitions and Compose builds can still
build. Harbor can also prepare network-control sidecars. Inventory does not predict
all dynamic Dockerfile downloads, external Compose fragments or Harbor auxiliary images.
Do not strip digests or change scoring files to work around image lookup failures.

## 8. Prepare, check and run the smoke

```bash
.venv/bin/python -m eval prepare --request .fruitfly/eval-smoke.json
.venv/bin/python -m eval check --request .fruitfly/eval-smoke.json
```

Stop at the first failure. Full preparation freezes source/tasks, records the
controller package environment, prepares declared assets/caches, and probes the
Agent plus effective independent Verifiers. It can build/start environments and
makes no model calls. `check` starts no containers and performs no downloads.

| Evidence | Establishes | Does not establish |
|---|---|---|
| Catalog preflight | Executable discovery and basic Docker/Compose access | Successful imports, task startup or glibc diagnosis |
| Task inventory | Recorded selection, declared resources/images and local lookups | Runtime compatibility or complete environment startup |
| `check: available` | Matching prepared contents, controller and images | Model connectivity or complete verification |
| Authorized smoke | One actual Agent-to-verifier execution path | Every task image, full coverage or Agent quality |

`controller_dependencies: unverified` means dependency metadata was not fully
validated or declared conflicts remain; inspect its issues. A changed controller
requires preparation again. `verifier_execution` and `model_connectivity` stay
`unverified` in offline readiness; successful real trial evidence is separate.

**Model calls and charges:** run the next command only when actual model execution
is intended. Use a persistent terminal such as tmux on disconnect-prone links and
retain its output. Do not modify runtime directories or prepare into the same cache
concurrently with an active evaluation.

```bash
.venv/bin/python -m eval run --request .fruitfly/eval-smoke.json --events jsonl
.venv/bin/python -m eval report '<EVALUATION_ID>' --json
```

Use the actual ID from the final `finished` event. Confirm Agent execution, verifier
execution, a valid reward, complete selected-task coverage and cleanup. `completed`
means report assembly succeeded. A real reward 0 differs from an execution error;
it does not establish that the Agent solved the task. One smoke never proves that
all dataset environments or Verifier downloads work.

## 9. Prepare dependencies and the intended selection

Agent installation is already outside trials. Task builds and Verifier scripts
can still install their own packages. The default empty `dependencies.assets` and
`dependencies.prepare` do not prewarm packages or guarantee offline verification.

Use [dependency preparation](harbor/README.md#prepare-verifier-dependencies-separately)
to declare pinned assets/checksums and reviewed cache-warming recipes matching each
Verifier's actual Python, platform and versions. Keep `offline: false` until cache
completeness is demonstrated. uv/pip caches and offline flags do not control apt,
curl, custom installers or model networking.

`task_patches` supports exact setup replacements only under `tests/`; it cannot
edit `task.toml`, environment Dockerfiles or image references. Changes remain
recorded evaluation conditions. Do not edit Harbor's private cache, assertions or
rewards to repair setup. Separate image-embedded verifier files can require rebuilding
and revalidating the affected environment.

Create the intended request using the same dataset and machine YAML. Set `variant`
to `no_gpu` or `full`. These example budgets require review:

```bash
.venv/bin/python - <<'PY'
import json
from pathlib import Path
from eval.contracts import EvaluationRequest
payload = EvaluationRequest.read('.fruitfly/eval-smoke.json').to_dict()
payload['benchmark']['variant'] = 'no_gpu'
payload['execution'] = {'attempts': 1, 'concurrency': 1, 'timeout_seconds': 604800}
request = EvaluationRequest.from_dict(payload)
with Path('.fruitfly/eval-selected.json').open('x') as handle:
    json.dump(request.to_dict(), handle, indent=2)
    handle.write('\n')
PY

.venv/bin/python -m eval prepare --request .fruitfly/eval-selected.json --tasks-only
.venv/bin/python -m eval prepare --request .fruitfly/eval-selected.json
.venv/bin/python -m eval check --request .fruitfly/eval-selected.json
# Model calls and official verification; charges apply according to actual usage.
.venv/bin/python -m eval run --request .fruitfly/eval-selected.json --events jsonl
```

Preparing smoke does not prepare the intended selection. Inspect excluded IDs and
local-export scope before interpreting coverage. Keep the actual task list in
comparisons. Size concurrency for both Agent and Verifier resources. Do not infer
full-dataset duration or cost from a single task; whole-job limits are not monetary
limits, and missing billing/cache information cannot establish exact cost.

## 10. Stop, inspect and update

```bash
.venv/bin/python -m eval stop '<EVALUATION_ID>'
```

Wait for confirmed cleanup; `stop_requested` alone is not confirmation. If overriding
`--output-root`, use the same root for `run`, `report` and `stop`.

| Evidence | Location |
|---|---|
| Reports and normalized trials | `.fruitfly/eval/<id>/report.json`, `report.md`, `trials/` |
| Selected configuration and receipts | Evaluation `artifacts/harbor/` |
| Controller packages, selected/excluded tasks | `artifacts/harbor/preparation.json` |
| Runner and cleanup | `artifacts/harbor/harbor.log`, `control.json`, `cleanup.json` |
| Native Agent messages/tools | Harbor trial `agent/session.jsonl` |
| Standard trajectory and display events | Harbor trial `agent/trajectory.json`, `events.jsonl` |
| Official rewards and verifier output | Harbor trial `verifier/` and `result.json` |
| Task/image inventory | Configured cache `selections/<key>.json` |
| Probe output | Configured cache `checks/<key>/<index>-<role>/probe.log` |
| Dependency preparation | Configured cache `dependencies/prepare-<index>.log` |

Container workspaces are not fully archived; retain task-declared collected
artifacts when needed. Sessions do not preserve every raw API request or streamed
token. Abrupt host/process failure can leave partial records. Report directories
reference external frozen tasks/runtime material and do not export Docker images;
retain those separately for later reproduction. No key values are deliberately
included in configuration snapshots; avoid commands that expose keys in tool output.

After source, environment, library, link, task, image or dependency changes, repeat
preparation and checks outside active jobs. Matching caches can remain. Rerun the
relevant smoke when the evaluated condition changes. Receiving another supported
dataset should normally change task selection and task dependencies, not reinstall
Harbor or introduce benchmark-specific runtime branches.
