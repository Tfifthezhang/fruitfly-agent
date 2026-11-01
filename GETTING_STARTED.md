# Getting Started

[Up: FruitFlyAgent](README.md)

Install FruitFlyAgent and complete your first terminal session.

| Requirement | Details |
|---|---|
| Python | 3.11+ |
| Platform | macOS or Linux; native Windows is unsupported and WSL2 is unverified |
| Model access | An API key for real requests; the offline example needs no key |
| Docker | Only needed for optional [Eval](fruitfly_eval/README.md) |

## Install

Run from the downloaded source directory:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e .
.venv/bin/python -m fruitfly_agent
```

## Check the Agent offline

After installing from a source checkout, run these commands from that checkout:

```bash
.venv/bin/python -m examples.extensions.offline_guidance
.venv/bin/python -m unittest tests.eval.test_material_resources
```

The first runs the actual Application and Agent loop with a fixed Provider.
Expected output: `Offline response: example-guidance is active.` The second
freezes source and wheel material, imports Providers, loads templates and checks
CLI startup from isolated temporary directories. Both need no keys, model calls,
Docker or network. They validate execution paths, not model quality.

For installed wheels, follow the [installed checks](examples/packaging/README.md).
For real model testing, continue below. Container benchmarks additionally require
[Eval preparation](fruitfly_eval/DEVELOPER_GUIDE.md#check-local-execution-first).

## Choose a model

Editable installation keeps source changes visible without reinstalling. To install a built wheel into a separate environment, see [Contributing](CONTRIBUTING.md#build-and-publish); run `fruitfly-agent` in your workspace to configure a model.

| Step | Action |
|---|---|
| 1 | From the startup panel, choose **Configure → model → Add model…**, then choose OpenAI Responses, Anthropic Messages, or a custom service using one of those protocols. |
| 2 | Enter a menu label, model ID, and the token limits documented by your service. Official services may leave the API address blank; custom services require it. |
| 3 | Leave the existing-key-variable field blank to create a variable for this model, then enter the API key with hidden input. To reuse a key, enter its environment variable name and leave the key input blank. |
| 4 | On **capabilities**, toggle verified optional support; keep required rows checked and choose Continue. |
| 5 | Review the non-secret settings and choose **Stage model**, then **Save and return** to save. Select **Start session** from the panel when ready. Cancellation writes no model or credential files. |

For additional models, use **/config → model → Add model…**, or run `fruitfly-agent --configure`. **Set API key…** supplies a missing key for the selected model. The wizard performs offline checks only; it does not test credentials, model access, or remote API compatibility. Enter `/cancel` at a field to return. Starting a session does not send a model request until you submit a task.

The [model template](examples/configuration/models.example.yaml) provides `deepseek-flash-openai` (Responses API) and `deepseek-flash-anthropic` (Messages API) in one file. Both use `deepseek-flash` and a `DEEPSEEK_API_KEY`; the Provider name selects the protocol. See the [example setup and limits](examples/configuration/README.md). A Chat Completions-only endpoint cannot use the Responses adapter. Keep only profiles you need; rename them if desired. Use separate `api_key_env` names if profiles need different keys.

The wizard writes model specifications to `.fruitfly/models.yaml`, key values to the workspace `.fruitfly/secrets.env`, and selection to `.fruitfly/config.yaml`. These local files are excluded from distributions. Existing models, catalog comments, and unrelated environment entries are retained. Manual configuration with the public templates remains available for advanced model parameters and capabilities; see [Configuration](CONFIGURATION.md).

Leave `FRUITFLY_MODEL_PROFILE` unset or blank to choose interactively. A sole model is selected automatically. Use `--cwd /path/to/workspace` to read that workspace's configuration and `.fruitfly/secrets.env`; process environment variables take precedence.

**Live tasks contact the configured model service and may incur charges. Local file and shell tools use your current user permissions and do not provide a sandbox.**

The standard host allows ordinary workspace file operations, protects known credential paths, and asks before external file access or Bash/IPython execution. In an interactive terminal, choose **1 / Enter** to allow once, **2** for the displayed session scope, or **3 / Esc** to deny. `/permissions clear` revokes remembered approvals. Without an enabled confirmation frontend or injected handler, operations requiring approval are denied. See [terminal permissions](fruitfly_agent/interactive/terminal/README.md#respond-to-permission-requests).

## Run and resume

Use **/config → Restore default configuration** to stage the default tools,
environment, algorithms and prompt. The action retains your model and credentials;
review and apply the draft to this conversation or discard it. Prepare the
[default templates](examples/configuration/README.md) before restoring. Default
files are edited manually. Eval uses their complete profile inside task containers.

After initial configuration:

```bash
.venv/bin/python -m fruitfly_agent "List the Python files here and explain what they do."
.venv/bin/python -m fruitfly_agent --resume
```

| Action | Behavior |
|---|---|
| Start without a task | Open the offline startup panel; choose Configure or Start session. |
| Use `--configure` | Open the shared configuration editor first; save or discard, then return to the panel. |
| Supply a task | Run a single task. |
| Use `--resume` | Show recovery intent in the panel; Start session validates and restores the latest non-empty session. |
| Use `--resume --session PATH` | Show the selected session in the panel; Start session validates and restores it. |
| Enter `/resume` | Choose a compatible session from the idle terminal and display saved chat. |
| Supply a task with `--resume` | Continue saved context for one task without printing old chat; model requests may incur charges. |
| Change configuration | Use `/config` while idle to save and apply to this conversation. |

See [Terminal](fruitfly_agent/interactive/terminal/README.md) for daily controls and [Run](fruitfly_agent/run/README.md) for startup and recovery contracts.

## Add context

| Need | Setup | Guide |
|---|---|---|
| Reusable instructions | Create `.skills/<name>/SKILL.md` and enable Skill catalog. | [Skills](fruitfly_agent/lab/context_manager/augmentation/skills/README.md) |
| Notes across sessions | Add an index at `.fruitfly/memory/MEMORY.md` and topic notes beside it. | [File memory](fruitfly_agent/lab/context_manager/augmentation/information/file_memory/README.md) |
| Local reference documents | Add Markdown or text files to `.fruitfly/knowledge/` and enable Local knowledge. | [Local knowledge](fruitfly_agent/lab/context_manager/augmentation/information/local_knowledge/README.md) |
| A live information service | Configure an HTTPS endpoint and enable Live HTTP. | [Live HTTP](fruitfly_agent/lab/context_manager/augmentation/information/live_http/README.md) |

## Try an offline extension

```bash
.venv/bin/python -m examples.extensions.offline_guidance
```

This uses a temporary workspace and a fixed Provider, with no keys or network. See the [extension example](examples/extensions/README.md) for the complete registration and Application path.

## Try improvement

The [remote Linux TB4 walkthrough](examples/experiments/TB4_SERVER.md) covers an
executable experiment. In an existing workspace, generate its files:

```bash
.venv/bin/fruitfly-agent-lab init --source task-set --benchmark terminal-bench-4
```

Review `.fruitfly/models.yaml`, choose its aliases in `default-config.yaml`, and
put keys privately in `secrets.env` or the process environment. Configure the host
runtime as described in the walkthrough. Initialization starts no models,
downloads or containers. Existing regular model catalogs and secrets are preserved;
other generated destinations must not exist.

```bash
# Preparation can download/build/start containers; it makes no task model calls.
.venv/bin/fruitfly-agent-lab eval prepare --tasks-only
.venv/bin/fruitfly-agent-lab eval prepare
.venv/bin/fruitfly-agent-lab improvement check
# Model requests and benchmark execution; charges may apply.
.venv/bin/fruitfly-agent-lab improvement run --events jsonl
```

Plain `init` creates system configuration only. Instruction/file and task-package
materials require an embedding with a registered task backend; no local task
executor is bundled. `/improvement` uses the same execution requirement. RSI also
requires independent verification material. See [experiment templates](examples/experiments/README.md)
for file ownership and [execution registration](fruitfly_agent/lab/improvement/execution/README.md)
for embedding contracts.

| Next step | Guide |
|---|---|
| Write your own tasks | [Task packs](fruitfly_agent/lab/improvement/tasks/README.md) |
| Review and adopt a candidate | [Improvement](fruitfly_agent/lab/improvement/README.md) |
| Run the offline suite | [Tests](tests/README.md) |
| Make a real Provider smoke request | [Integration smoke](tests/integration/README.md) |
