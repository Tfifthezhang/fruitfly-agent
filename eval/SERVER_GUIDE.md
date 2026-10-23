# Server Evaluation Guide / 服务器测评指引

[Up: Eval / 上级](README.md)

Run these steps in order: clone, transfer private configuration, install the two
Linux environments, create machine/request files, validate, prepare, check, smoke,
then evaluate the intended task set. Examples use Terminal-Bench 4.0.0; other
registered Harbor benchmarks use the same flow.

按顺序执行：克隆代码、传输私有配置、安装两套 Linux 环境、生成机器配置和请求文件、
离线校验、prepare、check、单任务 smoke，最后运行正式任务集。
下面以 Terminal-Bench 4.0.0 为例，其他已注册的 Harbor benchmark 使用相同流程。

**Where to run / 执行位置:** Unless marked **Local computer**, run commands in the
cloned project directory on the Linux server. Replace `SERVER` and the example
`/mnt/data/zhangwei/agents` location before use. Reuse an existing checkout and
runtime when appropriate; do not recreate an environment while evaluations use it.

除标注“本机”外，命令均在 Linux 服务器的项目根目录执行。
先替换 `SERVER` 和示例存储路径；已有仓库、运行环境可以复用，正在评测时不要重建环境。

**External effects / 外部操作:** Installation and preparation can download files,
build images and start containers. Only `run` starts the Agent and official
verifiers and can incur model charges. This guide does not execute those operations
automatically or establish compatibility with your server and task images.

安装和准备可能下载文件、构建镜像、启动容器；只有 `run` 会启动 Agent 和正式验证，
并可能产生模型费用。指南不会自动执行这些操作，也不代表你的服务器和任务镜像已经实测通过。

## 1. Clone the source / 克隆项目

The repository contains code, tests and public templates. Private `.fruitfly/`
state is not supplied by `git clone`.

仓库提供源码、测试和公开模板；`git clone` 不会带上私有的 `.fruitfly/` 状态。

```bash
mkdir -p /mnt/data/zhangwei/agents
cd /mnt/data/zhangwei/agents
git clone https://github.com/Tfifthezhang/fruitfly-agent.git
cd fruitfly-agent
umask 077
mkdir -p .fruitfly
chmod 700 .fruitfly
```

Check the server prerequisites. Install missing prerequisites through your server's
supported process. The commands below assume `uv` is already on `PATH`; see the
[official uv installation instructions](https://docs.astral.sh/uv/getting-started/installation/).
Harbor uses host Python 3.12+ and Docker Engine with Compose v2. The server must
also satisfy each selected task's CPU, memory, GPU, network and disk requirements.

先检查服务器前置条件。缺少的软件按服务器允许的方式安装。
下面假设 `uv` 已加入 `PATH`，安装方式见上面的官方链接。
Harbor 的宿主机 Python 需要 3.12+，并需要 Docker Engine 和 Compose v2。
CPU、内存、GPU、网络和磁盘仍需满足所选任务自己的要求。

```bash
uv --version
docker info
docker compose version
df -h .
```

## 2. Transfer private files / 单独传输配置和凭证

| File / 文件 | Purpose / 用途 | Required for / 使用场景 |
|---|---|---|
| `.fruitfly/secrets.env` | Model and enabled-tool credentials / 模型和已启用工具的凭证 | Evaluation and interaction / 评测和交互 |
| `.fruitfly/default-config.yaml` | Evaluation Agent profile / 评测 Agent 默认配置 | Evaluation / 评测 |
| `.fruitfly/default-models.yaml` | Evaluation model catalog / 评测模型目录 | Evaluation / 评测 |
| `.fruitfly/config.yaml` | Daily interaction settings / 日常交互配置 | Optional interaction / 按需传输 |
| `.fruitfly/models.yaml` | Daily model catalog / 日常模型目录 | Optional interaction / 按需传输 |

**Local computer:** Run from your local project root after creating the server's
`.fruitfly/` directory in step 1. The first three files are sufficient for the
default evaluation path. Transfer the daily pair separately if wanted.

**本机：** 第 1 步创建远端目录后，在本机项目根目录执行。
默认评测只需要前三份；需要保留日常交互配置时，再传另外两份。

```bash
scp .fruitfly/secrets.env \
    .fruitfly/default-config.yaml \
    .fruitfly/default-models.yaml \
    zhangwei@SERVER:/mnt/data/zhangwei/agents/fruitfly-agent/.fruitfly/
```

**Server:** Protect the credentials. Values stay in `secrets.env`; model catalogs
contain only `api_key_env` variable names. Process environment values take precedence,
so review conflicting server exports without printing keys. Do not copy the whole
local `.fruitfly/`, sessions, results, or a macOS `.venv`.

**服务器：** 凭证值只放在 `secrets.env`，模型 YAML 只引用 `api_key_env` 变量名。
进程环境优先于凭证文件，已有同名环境变量时要确认其来源，不要打印密钥。
不需要复制整个 `.fruitfly/`、会话、评测结果或 macOS 的 `.venv`。

```bash
chmod 700 .fruitfly
chmod 600 .fruitfly/secrets.env
```

If the default YAML files do not exist anywhere yet, copy the public
[Agent template](../examples/configuration/default-config.example.yaml) and
[model template](../examples/configuration/default-models.example.yaml) to the
paths above only when absent. Review the model, protocol, endpoint and limits,
and configure the matching key in the private secret file. Preserve existing files.
Daily/default catalogs can share the same key variable. See [Configuration](../CONFIGURATION.md).

如果还没有默认 YAML，可从以上两个公开模板创建，但不要覆盖已有配置。
使用前核对模型、协议、接口地址和 token 限制，在私有凭证文件中填写对应 key。
日常配置和默认配置可以共用一个 key 变量，不需要重新注册密钥。

Configuration references can require additional files: copy the exact referenced
`.fruitfly/artifacts/<hash>` files for `sha256:` prompt/component bindings. A daily
SSH profile remains SSH after transfer; choose local execution on the server if
that is intended. Eval requires a local task-container environment and rejects SSH
execution profiles. The shipped default template already selects local execution.

如果配置引用 `sha256:` 提示词或组件，还需要复制对应的 `.fruitfly/artifacts/<hash>`。
日常 SSH 配置复制后仍然连接 SSH 目标，若要直接操作服务器本地文件，需要在远端选择本地环境。
Eval 必须在任务容器内执行，不能使用 SSH 执行配置；默认模板已经使用本地环境。

## 3. Install the Linux environments / 一次性安装 Linux 环境

| Environment / 环境 | Location / 位置 | Responsibility / 职责 |
|---|---|---|
| Host controller / 宿主机控制环境 | Project `.venv` | Eval CLI, Harbor and orchestration / 运行评测命令和 Harbor |
| Container Agent runtime / 容器内 Agent 运行环境 | Dedicated `agent-venv` plus complete base Python / 独立 venv 和完整 Python 安装 | Mounted read-only into Agent containers / 只读挂载进 Agent 容器 |

Use a dedicated Python installation rather than mounting `/usr`, `/usr/local`,
a whole Conda installation or the whole checkout over task directories. A venv
alone may point to an unmounted system interpreter and libraries. The example
uses [uv-managed Python](https://docs.astral.sh/uv/guides/install-python/) and
[explicit environment installation](https://docs.astral.sh/uv/pip/environments/).
Downloads and package installation happen on the server now, not in each task.

使用独立 Python 安装，避免把宿主机 `/usr`、`/usr/local`、整个 Conda 或项目目录
覆盖到任务容器中。只挂载 venv 可能遗漏它依赖的解释器和动态库。
示例使用 uv 管理的 Python；下载和安装在服务器上完成一次，不在每个任务中重复安装 Agent。

Run the following in the same shell. These are setup variables, not API keys.
The machine-file generator in step 4 saves resolved paths, so subsequent runs do
not need to export these variables again.

在同一个 shell 中顺序执行。下面都是安装路径变量，不是 API key。
第 4 步会把实际路径写入机器 YAML，后续重新登录不需要再次 export 这些变量。

```bash
# Dedicated runtime directories contain no credentials and must be readable by task users.
umask 022
export FRUITFLY_EVAL_ROOT=/mnt/data/zhangwei/agents/fruitfly-eval-runtime
export UV_PYTHON_INSTALL_DIR="$FRUITFLY_EVAL_ROOT/python"
uv python install 3.12
export FRUITFLY_EVAL_BASE_PYTHON="$(uv python find --managed-python --system 3.12)"
export FRUITFLY_EVAL_PYTHON_ROOT="$("$FRUITFLY_EVAL_BASE_PYTHON" -c 'import sys; print(sys.base_prefix)')"
export FRUITFLY_EVAL_VENV="$FRUITFLY_EVAL_ROOT/agent-venv"

uv venv --python "$FRUITFLY_EVAL_BASE_PYTHON" .venv
uv pip install --python .venv/bin/python -e '.[benchmarks]'

uv venv --python "$FRUITFLY_EVAL_BASE_PYTHON" "$FRUITFLY_EVAL_VENV"
uv pip install --python "$FRUITFLY_EVAL_VENV/bin/python" --link-mode copy .
umask 077

.venv/bin/python -m fruitfly_agent --help
.venv/bin/python -m eval catalog --json
```

The host extra pins Harbor to `0.23.0`; the Agent runtime needs only the ordinary
project dependencies. This runtime layout is a starting point, not a promise of
compatibility with every image. Container probes must pass. Missing libraries,
glibc compatibility, or task-user access can require a different Linux Python
build or narrowly scoped additional read-only library mounts.

宿主机的 benchmarks extra 固定 Harbor `0.23.0`，Agent 运行环境只安装项目普通依赖。
这套目录结构只是起点，并不保证兼容所有镜像；仍需通过容器探测。
动态库、glibc 或任务用户访问问题，可能需要更合适的 Linux Python 构建，
或增加范围明确的只读动态库挂载。

## 4. Create the machine YAML / 生成机器配置 YAML

These files have separate roles; their schema versions are independent.

以下文件职责不同，`schema_version` 不能混用。

| File / 文件 | Controls / 控制内容 | Schema |
|---|---|---|
| `default-config.yaml` | Agent mechanisms and model selection / Agent 机制和模型选择 | 1 |
| `default-models.yaml` | Model catalog / 模型目录 | Model catalog format / 模型目录格式 |
| `secrets.env` | Credential values / 凭证值 | Environment assignments / 环境变量格式 |
| `eval-host.yaml` | Linux runtime mounts, task source and caches / 运行环境挂载、任务来源和缓存 | 1 |
| `eval-smoke.json`, `eval-full.json` | Benchmark, attempts, concurrency and job deadline / 任务集、重复次数、并发和整体期限 | 2 |

Generate `.fruitfly/eval-host.yaml` from the maintained template using the paths
from step 3. Existing machine files are preserved: inspect and update their
server paths manually instead of rerunning the generator over them.

使用第 3 步的实际路径和仓库模板生成 `.fruitfly/eval-host.yaml`。
如果文件已经存在，脚本会停止，请手动检查并调整服务器路径，不会自动覆盖。

```bash
.venv/bin/python - <<'PY'
import os
from pathlib import Path
import yaml
from eval.harbor.host import HostConfig

workspace = Path.cwd().resolve()
target = workspace / '.fruitfly/eval-host.yaml'
if target.exists():
    raise SystemExit('eval-host.yaml already exists; review it without overwriting.')
python_root = Path(os.environ['FRUITFLY_EVAL_PYTHON_ROOT']).resolve()
runtime = Path(os.environ['FRUITFLY_EVAL_VENV']).resolve()
if not (python_root / 'bin').is_dir() or not (runtime / 'bin/python').is_file():
    raise SystemExit('Complete step 3 before generating the machine file.')
settings = yaml.safe_load((workspace / 'examples/configuration/eval-host.example.yaml').read_text())
settings['cache'] = str(workspace / '.fruitfly/eval-cache')
settings['agent']['python'] = str(runtime / 'bin/python')
settings['agent']['mounts'] = [{'source': str(python_root)}, {'source': str(runtime)}]
target.parent.mkdir(parents=True, exist_ok=True)
with target.open('x') as handle:
    yaml.safe_dump(settings, handle, sort_keys=False)
HostConfig.read(workspace, target)
print(target)
PY
```

The resulting machine file has this shape. The paths here are illustrative;
the generator writes your actual Python installation path.

生成后的结构如下。此处路径仅用于说明，脚本会写入实际安装路径。

```yaml
schema_version: 1
cache: /mnt/data/zhangwei/agents/fruitfly-agent/.fruitfly/eval-cache
agent:
  python: /mnt/data/zhangwei/agents/fruitfly-eval-runtime/agent-venv/bin/python
  mounts:
    - source: /mnt/data/zhangwei/agents/fruitfly-eval-runtime/python/YOUR_PYTHON_INSTALLATION
    - source: /mnt/data/zhangwei/agents/fruitfly-eval-runtime/agent-venv
  library_paths: []
environment:
  setup: {}
  agent: {}
  verifier: {}
dependencies:
  assets: []
  prepare: []
  offline: false
task_patches: []
```

Keep the cache outside all runtime mount sources. Runtime targets default to the
same absolute host paths, preserving interpreter links. This file contains no
model choice or key values. See [the machine contract](harbor/README.md#configure-a-machine).

缓存必须在运行环境挂载目录之外。省略 `target` 时，容器内使用与宿主机相同的绝对路径，
保留解释器链接关系。这个 YAML 不放模型选择或 API key。

Already downloaded images must match the resolved tasks' actual image references.
`prepare` may still build an image when a task supplies Dockerfiles rather than
matching prebuilt references. Agent and separate verifier images are distinct
roles. A Docker image cache does not replace host-side task definitions.
An exported local task tree can be selected with `task_directory: /absolute/path/to/tasks`;
leave it unset for registry resolution. Keep local subsets explicitly identified
in reports; a local directory is not proof of full official dataset coverage.

预下载镜像必须与任务实际引用匹配；如果任务提供 Dockerfile 而不是匹配的预构建镜像引用，
`prepare` 仍可能构建。Agent 和独立 Verifier 是两个镜像角色，镜像缓存不能替代任务定义。
已有导出的任务目录时，可以设置 `task_directory`；否则保留未设置，让 Harbor 解析数据集。
本地任务子集需要明确标注，不能把目录中的任务数量当作官方全量覆盖的证明。

## 5. Create the smoke JSON / 生成单任务请求 JSON

Choose a registered ID. Benchmark-specific declarations select tasks; the machine
file and shared Harbor execution stay the same.

先选择已注册的 benchmark ID。任务选择属于数据集声明，机器配置和 Harbor 执行逻辑共用。

| ID | Dataset / 数据集 | Smoke task / 单任务 |
|---|---|---|
| `terminal-bench-4` | Terminal-Bench 4.0.0 | `terminal-bench/interleaved-vigenere` |
| `terminal-bench` | Terminal-Bench 2.1 | `terminal-bench/fix-git` |
| `swe-bench` | SWE-bench Verified | `swe-bench/psf__requests-1142` |

This example allows one attempt, one concurrent trial, and a **36,000-second
whole-job budget**. Review that budget before executing: it is not a per-task
timeout or a price limit. TB 4.0 tasks can declare eight-hour Agent limits, so
the generic one-hour request default need not cover their full allowed runtime.
The job timeout does not apply to the preceding `prepare` command.

示例设置单次尝试、并发 1、**整体任务预算 36,000 秒**。运行前按你的预算修改。
这是整个 job 的期限，不是单个任务期限，也不是费用上限。
TB 4.0 部分任务允许 Agent 运行 8 小时，通用请求默认的 1 小时未必能覆盖官方完整时限。
这个整体期限不控制之前单独执行的 `prepare` 命令。

```bash
.venv/bin/python - <<'PY'
import json
from pathlib import Path
from eval.catalog import builtin_catalog
from eval.contracts import EvaluationRequest

workspace = Path.cwd().resolve()
request = EvaluationRequest.from_dict({
    'schema_version': 2,
    'runtime': {'working_directory': str(workspace)},
    'benchmark': {'id': 'terminal-bench-4', 'variant': 'smoke'},
    'execution': {'attempts': 1, 'concurrency': 1, 'timeout_seconds': 36000},
})
builtin_catalog().get(request.benchmark.benchmark_id)
target = workspace / '.fruitfly/eval-smoke.json'
target.parent.mkdir(parents=True, exist_ok=True)
with target.open('x') as handle:
    json.dump(request.to_dict(), handle, indent=2)
    handle.write('\n')
print(target)
PY
```

`runtime.config_path` and `profile` are omitted intentionally: Eval reads
`.fruitfly/default-config.yaml` and its selected default profile. There is no
fallback to daily configuration. Change the benchmark ID in the generator for
another registered benchmark. Existing request files are not overwritten.

没有填写 `config_path` 和 `profile`，表示使用 `.fruitfly/default-config.yaml` 及其默认 profile，
不会回退到日常配置。切换 benchmark 时修改生成脚本中的 ID；已有请求文件不会被覆盖。

## 6. Validate without model calls / 离线校验配置

This checks request fields, machine paths/settings, model/profile references,
enabled mechanisms, required credentials and immutable artifacts. It does not
contact the model or establish endpoint compatibility. Only credential variable
names are printed, never values. Temporary normalized files are removed on exit.

先校验请求字段、机器配置、模型引用、启用机制、所需凭证和不可变文件。
不会请求模型，也不能证明接口可用；只显示凭证变量名，不打印密钥值。
临时规范化文件会在退出时自动清理。

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

## 7. Prepare, check and smoke / 准备、检查、单任务验证

Run sequentially and stop at the first failure. `prepare` freezes source/tasks,
checks the mounted Agent runtime and every effective separate verifier environment,
and prepares declared dependency assets/caches. It can download/build/start
containers, but makes no model requests and runs no scoring assertions.

依次执行，任何一步失败都先排查，不要继续启动正式评测。
`prepare` 冻结源码和任务，探测 Agent 及独立 Verifier 环境，准备声明的资产和缓存。
它可能下载、构建、启动容器，但不会请求模型或执行评分断言。

```bash
.venv/bin/python -m eval prepare --request .fruitfly/eval-smoke.json
.venv/bin/python -m eval check --request .fruitfly/eval-smoke.json
```

`check` should return `available: true`. It does not download or start containers.
`verifier_execution` and `model_connectivity` remain `unverified`; that is expected
until a real trial supplies evidence. Catalog preflight alone is not this check.

`check` 应返回 `available: true`，不会下载或启动容器。
此时验证执行和模型连接仍为 `unverified` 是正常的，需要真实任务验证。
`catalog` 的前置检查不能替代这一步。

**Model requests and charges / 模型调用和费用:** The next command runs the Agent
and official verifier. On disconnect-prone SSH links, use your usual persistent
terminal session and retain the event output. Do not update runtime directories
or prepare into the same cache concurrently with an active evaluation.

下面这条命令开始调用模型并正式验证，可能产生费用。
SSH 容易断开时使用你已有的持久终端会话，并保留事件输出。
评测进行中不要修改运行环境，也不要同时向同一个缓存目录执行 prepare。

```bash
.venv/bin/python -m eval run --request .fruitfly/eval-smoke.json --events jsonl
```

The final `finished` event supplies `evaluation_id` and report paths. Use its
actual ID below. Report `completed` means assembly succeeded, not that the task
earned reward 1. Confirm the Agent and verifier executed, rewards were produced,
coverage is complete, and no infrastructure errors occurred. Reward 0 is distinct
from an execution failure. One smoke task does not validate all task images or GPUs.

结束事件会给出 `evaluation_id` 和报告路径。下面的 ID 要替换为实际值。
报告的 `completed` 不表示 reward 一定为 1。先确认 Agent 和 Verifier 都执行了、
有合法 reward、任务覆盖完整且没有基础设施错误。reward 为 0 与任务未能执行是两回事。
一个 smoke 不能证明所有任务镜像或 GPU 路径均可用。

```bash
.venv/bin/python -m eval report '<EVALUATION_ID>' --json
.venv/bin/python -m eval report '<EVALUATION_ID>'
```

## 8. Prepare dependencies when needed / 按需准备验证依赖

The generated `dependencies` section is an online starting configuration, not
a claim that verifier downloads have been eliminated. Agent installation is
already outside trials. Task image builds and verifier scripts can still install
their own task-specific packages. Shared caches accelerate compatible installers;
they do not skip arbitrary `curl`, apt, pip or uv commands.

默认生成的 `dependencies` 是允许联网的起点，并不代表消除了所有验证依赖下载。
Agent 本身已经不在每个任务内安装，但任务镜像构建和验证脚本仍可能安装任务自己的包。
缓存只能帮助兼容的安装器复用下载，不能自动跳过任意 curl、apt、pip 或 uv 命令。

Use [dependency preparation](harbor/README.md#prepare-verifier-dependencies-separately)
to declare exact assets, SHA-256 checksums and reviewed cache-warming recipes.
Recipe images must already be cached; commands must match the verifier's actual
Python/platform and package versions. Review the task's verifier scripts before
choosing recipes. Keep `offline: false` until the required caches are demonstrated
complete. uv/pip offline flags do not disable other downloaders or model access.

需要时按链接声明资产、SHA-256 和经过检查的预热命令。
预热使用的镜像需要已经缓存，命令必须匹配 Verifier 的 Python、平台和包版本。
先查看验证脚本再写预热配置，不要提前盲目打开 `offline: true`。
uv/pip 离线标志不控制其他下载器，也不代表关闭模型网络访问。

Repeat `prepare`, `check`, and the relevant smoke after changing dependency
settings. Do not edit Harbor's private cache or replace scoring assertions to
work around installation failures. Explicit setup patches remain recorded
evaluation conditions, including when the affected verifier files are built into
an independent image.

修改依赖配置后重新执行 prepare、check 和相关 smoke。
不要直接改 Harbor 私有缓存，也不要通过修改评分断言修复安装问题。
显式 setup 修改会被记录为评测条件；独立验证镜像内的文件修改也需要记录并重新准备。

## 9. Run the intended task set / 运行正式任务集

| Variant | Selection / 任务选择 | Preflight / 前置检查 |
|---|---|---|
| `smoke` | One fixed task / 固定单任务 | Task-dependent / 依任务而定 |
| `starter` | Five fixed TB 2.1 CPU tasks only / 仅 TB 2.1 固定五任务 | No GPU preflight / 不做 GPU 检查 |
| `no_gpu` | All resolved tasks, including GPU tasks / 全部任务，包含 GPU 任务 | No GPU preflight / 不做 GPU 检查 |
| `gpu` | All resolved tasks / 全部任务 | Adds NVIDIA executable detection / 增加 NVIDIA 检查 |

**`no_gpu` is not a CPU-task filter.** Full TB 4.0 includes GPU tasks whose
configurations request H100 GPUs. `nvidia-smi` being present does not establish
GPU type, capacity or concurrent allocation compatibility. A CPU-only server
cannot use `no_gpu` as a declaration of an official CPU-only subset.

**`no_gpu` 不会过滤 GPU 任务。** TB 4.0 全量包含请求 H100 的任务。
存在 `nvidia-smi` 不代表 GPU 型号、容量和并发分配都满足任务要求。
只有 CPU 的服务器不能把 `no_gpu` 当作官方 CPU 子集。

After the relevant smoke passes, create a separate full request. This example
uses one attempt, concurrency 1 and a **seven-day whole-job cap**. Review all
three values; the cap does not guarantee that every task can exhaust its official
limit and finish. Choose concurrency for both Agent and verifier resources.
Full selection preparation may build/probe many environments before any model call.

相关 smoke 跑通后，单独生成正式请求。示例为尝试 1 次、并发 1、整体上限 7 天，
三项都应按实际资源和预算调整；这个上限不保证所有任务都能用满官方时限后结束。
并发需同时考虑 Agent 和 Verifier 的资源，全量 prepare 也可能耗时较长。

```bash
.venv/bin/python - <<'PY'
import json
from pathlib import Path
from eval.contracts import EvaluationRequest

payload = EvaluationRequest.read('.fruitfly/eval-smoke.json').to_dict()
payload['benchmark']['variant'] = 'gpu'
payload['execution'] = {'attempts': 1, 'concurrency': 1, 'timeout_seconds': 604800}
request = EvaluationRequest.from_dict(payload)
target = Path('.fruitfly/eval-full.json')
with target.open('x') as handle:
    json.dump(request.to_dict(), handle, indent=2)
    handle.write('\n')
print(target.resolve())
PY

.venv/bin/python -m eval prepare --request .fruitfly/eval-full.json
.venv/bin/python -m eval check --request .fruitfly/eval-full.json
# Model calls and official verification; charges may apply.
.venv/bin/python -m eval run --request .fruitfly/eval-full.json --events jsonl
```

Preparing `smoke` does not prepare the full task set. Do not relabel a partial
run as full results. Keep the report's exact coverage and preparation evidence.
Other Harbor benchmarks use their own ID/task declarations; there are no
benchmark-specific machine YAML fields or alternate Agent installers.

准备过 smoke 不代表准备过全量任务。部分任务的运行结果不能改名当作全量结果。
保留报告中的实际覆盖和准备记录；切换其他 Harbor benchmark 时只选择对应声明，
不需要新增一套机器 YAML 字段或 Agent 安装流程。

## 10. Stop, inspect and update / 停止、排查和更新

```bash
.venv/bin/python -m eval stop '<EVALUATION_ID>'
```

Use the same `--output-root` for `run`, `report` and `stop` if overriding the
default. Wait for confirmed cleanup; `stop_requested` alone is not confirmation.

如果运行时指定了 `--output-root`，查看报告和停止时也要使用相同目录。
需要等待清理确认；只看到 `stop_requested` 不代表已停止完成。

| Evidence / 排查材料 | Default location / 默认位置 |
|---|---|
| Report / 报告 | `.fruitfly/eval/<id>/report.json`, `report.md` |
| Complete runner output / 完整执行日志 | `.fruitfly/eval/<id>/artifacts/harbor/harbor.log` |
| Prepared identities / 准备身份 | `.fruitfly/eval/<id>/artifacts/harbor/preparation.json`, `readiness.json` |
| Task setup and verifier output / 任务启动和验证输出 | Harbor trial directories beneath that job / 该 job 下的 trial 目录 |
| Probe failures / 环境探测错误 | Configured cache `checks/<key>/<index>-<role>/probe.log` when execution reached the probe command / 探测命令执行后产生的日志 |
| Dependency preparation / 依赖预热 | Configured cache `dependencies/prepare-<index>.log` |

After source updates, rerun `prepare` and `check` to freeze and probe the new
source. If dependencies changed, update the appropriate host/Agent environments
first, outside active jobs. Moving runtime paths, changing symlink destinations,
retagging images, changing task contents or changing dependency settings also
requires preparation again. Existing matching download caches can be retained.
Changes to the current model/default YAML are read for the next job; they do not
alter an already staged running job. Repeat smoke when the evaluated condition changes.

更新源码后重新 prepare、check，确保冻结和探测的是新代码。
依赖变化时先更新相应的宿主机或 Agent 环境，避开正在运行的评测。
移动路径、改变链接、镜像标签、任务内容或依赖配置后，也需要重新准备；不必清空仍匹配的下载缓存。
默认配置或模型 YAML 的修改供下一个 job 读取，不会改变已经启动的 job；评测条件变化后重新 smoke。

The offline configuration checks and documentation examples are not evidence of
task rewards or full remote runtime compatibility. Start with execution health,
then assess Agent quality separately.

离线校验和文档示例不能证明 reward 或全量远程兼容性。先确认任务能正常启动、执行和验证，
再单独分析 Agent 的任务能力。
