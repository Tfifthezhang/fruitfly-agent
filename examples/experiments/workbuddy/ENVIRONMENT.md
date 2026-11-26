# Diagnose the WorkBuddy execution environment

[Up: WorkBuddy recipe](README.md)

Use the same task, model connection and official verifier throughout diagnosis.
Record each failed check separately. A successful configuration parse does not
prove container, relay or scoring compatibility. Real containers and network
probes require an authorized integration session; model requests require smoke
authorization. The examples below are instructions, not automatic checks.

## Separate the execution layers

| Layer | Required evidence | Failure owner |
|---|---|---|
| Eval controller | Selected Python, installed distributions and source identity | Controller installation and Eval receipts |
| WorkBuddy worker process | Harbor 0.23.0, pinned checkout, shared native bridge imports | WorkBuddy backend |
| Mounted Agent runtime | Linux Python, dependent libraries, imports under the actual Agent user | Machine configuration |
| Task environment | Exact local image or official build definition, effective user and mounts | Official task and environment bridge |
| Model access | Provider connection identity and reachable authorized transport | Providers and host transport bridge |
| Verification/report | Original reward, execution error, initialized engine metrics and confirmed retirement | Official verifier and Eval result adapter |

Do not use a task failure to diagnose a controller installation failure. An
engine progress-display exception and an Agent exception can occur together;
retain both rather than treating the last traceback as the only cause.

## Use explicit requests for fixed evaluation

The generated research document contains task-set collections. The experiment CLI prepares and checks exact Eval collections. Fixed execution
uses the research Eval route or an explicit single Eval request. For a fixed run, use the explicit request and host
with the direct Eval CLI. Do not rewrite the research schema by trial and error.
Collection-only task selections must also be copied into the request's
`benchmark.task_names` before using this route; otherwise the scopes differ.

```bash
# Replace all paths. These commands use the existing FruitFlyAgent controller.
/absolute/path/to/fruitfly-agent/.venv/bin/python -m fruitfly_eval prepare \
  --request /absolute/workspace/.fruitfly/eval-request.json \
  --host-config /absolute/workspace/.fruitfly/eval-host.yaml --tasks-only
# May download/build/start environment probes; no inference requests.
/absolute/path/to/fruitfly-agent/.venv/bin/python -m fruitfly_eval prepare \
  --request /absolute/workspace/.fruitfly/eval-request.json \
  --host-config /absolute/workspace/.fruitfly/eval-host.yaml
/absolute/path/to/fruitfly-agent/.venv/bin/python -m fruitfly_eval check \
  --request /absolute/workspace/.fruitfly/eval-request.json \
  --host-config /absolute/workspace/.fruitfly/eval-host.yaml
```

`check` verifies recorded identities/images and validates the complete execution
job. It does not prove relay reachability or official scoring. Even `available: true` leaves
`verifier_execution` and `model_connectivity` unverified. Read those states before
starting a separately authorized smoke.

## Select the intended Docker daemon and cached image

For a native Linux rootless daemon, set its socket explicitly in the same process
environment as Eval. Verify the path belongs to the intended user:

```bash
export DOCKER_HOST="unix:///run/user/$(id -u)/docker.sock"
docker info
docker compose version
# Replace the image with the exact selected reference, including its tag/digest.
docker image inspect wb-cache/code__api_contract-hard-openapi_params:v1
```

A cached image does not replace task configuration, instructions or verifier
resources. Official `force_build` settings and an environment Dockerfile can
still trigger a build. Inspect the frozen effective environment and probe log
before concluding that a registry request is expected or necessary. Do not edit
task files to force use of a convenient image, prune shared images or change the
daemon to work around a preparation failure.

## Supply the complete Linux runtime

A venv may depend on its original Python installation and external shared
libraries. A missing `libssl.so.1.1` is a dynamic-linker error, not an inference
endpoint error. Inspect the declared interpreter and probe log. For a previously
validated external library bundle, add its read-only mount and library search
path through the existing host fields:

```yaml
# Merge into the existing agent section; preserve its interpreter/venv mounts.
# Placeholders: use a reviewed bundle compatible with the mounted interpreter.
agent:
  mounts:
    - source: /absolute/path/to/pylibs
      target: /absolute/path/to/pylibs
  library_paths:
    - /absolute/path/to/pylibs
```

Do not copy arbitrary system libraries into the task or replace its system
Python. Reprepare after host changes. Test runtime imports as the official Agent
user, not only root. A successful interpreter probe does not prove every task
library, verifier or model connection works.

## Make only the owned dependency cache writable

The host dependency cache is bind-mounted at
`/opt/fruitfly-eval-dependencies/cache`. With rootless Docker, container `dev`
usually maps to a different host UID than container root. Host ownership and
mode 0755 therefore do not establish that `dev` can write it.

1. Identify the exact Agent/verifier UID/GID after official user initialization.
2. Identify their host mappings and inspect permissions on the dedicated cache.
3. Have the environment owner grant access only to that cache and the required
   mapped identities, using ownership, group access or an appropriate ACL.
4. Verify creation/removal of a harmless file under the actual container user,
   then repeat the environment probe. Preserve unrelated study caches.

Do not recursively make the workspace, runtime, assets or cache world-writable.
Do not switch the official task user to root to pass a probe. If the environment
cannot establish mapped ownership safely, report the limitation instead of
repeatedly running smoke. WorkBuddy initialization grants the effective execution group access to owned
cache roots and the uv/python/pip directories. It preserves owner identity, uses
setgid directories and refuses foreign ownership or symlinks. It does not
recursively rewrite existing contents; incompatible old caches need a new
dedicated preparation cache.

## Keep installation identities stable

Use the unified [controller version policy](../../../fruitfly_eval/workbuddy/README.md#controller-version-policy).
The worker requires 0.23.0. Validate a fresh environment with the real SDK before
replacing a controller. Install declared dependencies before
preparation. Dependency changes invalidate readiness and require preparation
again. Review dependency conflicts instead of automatically upgrading a shared
controller used by another experiment. Keep the mounted Agent runtime separate
from the controller, and use one declared Harbor version across benchmarks.
Upstream source locks are source evidence, not authority to silently replace the
selected execution engine. Record the actual installed version and dependency
provenance; recreate preparation and benchmark baselines after engine changes.

If prepare succeeds but immediate check reports a controller mismatch, compare
package names/versions and the current versus frozen import/distribution origins.
Source-path discovery can expose checkout `egg-info` that is absent from a frozen
source tree. Do not move/delete installation metadata, edit receipts or relax
identity comparisons to make this pass. The worker discovers installed distributions only through the selected
interpreter's installation paths. Source-tree metadata is not an installed
controller package. Report a mismatch if those installed identities have not changed.

## Validate transport before model execution

Keep an `opencode-go` subscription connection as that integration. A generic API
entry does not preserve its session-header policy. A 200 response from the base
URL proves neither inference authorization nor required request headers.

Linux Unix relay uses a read-only per-trial mount. The host grants socket
connection permission; the container cannot modify the mounted directory.
Connecting does not authorize inference: the owner-only descriptor supplies an
opaque grant scoped to the selected model and route. The private host parent is
not shared. Never copy these descriptors into archives or replace the model
integration to bypass transport checks.

TLS is a supported configuration route only where the container can actually
reach the advertised listener. Validate in this order, without model credentials:

| Check | Required evidence |
|---|---|
| Host listener | Process started successfully; selected port is listening; host request succeeds |
| Container DNS | Advertised name resolves inside a task-equivalent container |
| Container route | Container can connect to that exact listener address and port |
| TLS | Trusted CA, valid certificate and matching hostname/IP SAN |
| Actual execution identity | Same transport works as the official non-root Agent user |
| Relay descriptor | Native pre-inference delivery/probe succeeds without exposing grants |

The configured relay uses an ephemeral port per trial, so a fixed-port diagnostic
alone does not establish that its real ports are reachable. Account for the
actual task network policy. `host.docker.internal` and `host-gateway` mappings are
not universal guarantees under rootless Docker. Changing a certificate cannot
repair DNS or routing. A failed listener launch, occupied port or wrong Python
path invalidates the connectivity test. Stop only listeners owned by this test;
do not terminate an unrelated service to reclaim a port.

Existing [integration checks](../../../tests/integration/README.md#docker-model-access)
use fake upstreams. They do not establish WorkBuddy JobConfig admission, real
host-to-container TLS reachability or model entitlement.

## Keep temporary files and diagnostics in the permitted workspace

Where the server restricts host writes to a workspace/data volume, create a
private temporary root there and export `TMPDIR` before starting the controller.
Use absolute paths. For example, replace the workspace path and export this in
the launching shell before starting Eval:

```bash
mkdir -p /absolute/permitted/workspace/private-tmp
chmod 700 /absolute/permitted/workspace/private-tmp
export TMPDIR=/absolute/permitted/workspace/private-tmp
```

Use a new private directory owned by this workspace. Python may cache its
temporary directory selection inside a long-lived process, so changing the
environment after startup is insufficient.
Runtime-generated temporary files are not controlled by documentation alone;
inspect retained job paths. Keep keys, temporary grants and TLS private keys out
of logs and archives.

Only after the required checks pass, run one authorized smoke with a new output
root. Review Agent failure, verifier outcome, engine aggregation and cleanup
separately. A zero reward following an Agent infrastructure error is not evidence
of model quality. Do not automatically replay failed attempts.
