# Getting Started

[Up: FruitFlyAgent](README.md)

Install FruitFlyAgent and complete your first terminal session.

| Requirement | Details |
|---|---|
| Python | 3.11+ |
| Platform | macOS or Linux; native Windows is unsupported and WSL2 is unverified |
| Model access | An API key for a model in your catalog |
| Docker | Only needed for optional [Eval](eval/README.md) |

## Install

Run from the downloaded source directory:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e .
.venv/bin/python -m fruitfly_agent
```

## Choose a model

Editable installation keeps source changes visible without reinstalling. To install a built wheel into a separate environment, see [Contributing](CONTRIBUTING.md#build-and-publish); run `fruitfly-agent` in your workspace to configure a model.

| Step | Action |
|---|---|
| 1 | In **Add model**, choose OpenAI Responses, Anthropic Messages, or a custom service using one of those protocols. The wizard opens automatically when no models are available. |
| 2 | Enter a menu label, model ID, and the token limits documented by your service. Official services may leave the API address blank; custom services require it. |
| 3 | Leave the existing-key-variable field blank to create a variable for this model, then enter the API key with hidden input. To reuse a key, enter its environment variable name and leave the key input blank. |
| 4 | On **capabilities**, toggle verified optional support; keep required rows checked and choose Continue. |
| 5 | Review the non-secret settings and choose **Stage model**, then **Start new session** to save. Cancellation writes no model or credential files. |

For additional models, use **Configure → model → Add model…**. **Set API key…** supplies a missing key for the selected model. The wizard performs offline checks only; it does not test credentials, model access, or remote API compatibility. Enter `/cancel` at a field to return. Starting a session does not send a model request until you submit a task.

The [model template](examples/configuration/models.example.yaml) provides `deepseek-flash-openai` (Responses API) and `deepseek-flash-anthropic` (Messages API) in one file. Both use `deepseek-flash` and a `DEEPSEEK_API_KEY`; the Provider name selects the protocol. See the [example setup and limits](examples/configuration/README.md). A Chat Completions-only endpoint cannot use the Responses adapter. Keep only profiles you need; rename them if desired. Use separate `api_key_env` names if profiles need different keys.

The wizard writes model specifications to `.fruitfly/models.yaml`, key values to the workspace `.fruitfly/secrets.env`, and selection to `.fruitfly/config.yaml`. These local files are excluded from distributions. Existing models, catalog comments, and unrelated environment entries are retained. Manual configuration with the public templates remains available for advanced model parameters and capabilities; see [Configuration](CONFIGURATION.md).

Leave `FRUITFLY_MODEL_PROFILE` unset or blank to choose interactively. A sole model is selected automatically. Use `--cwd /path/to/workspace` to read that workspace's configuration and `.fruitfly/secrets.env`; process environment variables take precedence.

**Live tasks contact the configured model service and may incur charges. Local file and shell tools use your current user permissions and do not provide a sandbox.**

The standard host allows ordinary workspace file operations, protects known credential paths, and asks before external file access or Bash/IPython execution. In an interactive terminal, choose **1 / Enter** to allow once, **2** for the displayed session scope, or **3 / Esc** to deny. `/permissions clear` revokes remembered approvals. Without an enabled confirmation frontend or injected handler, operations requiring approval are denied. See [terminal permissions](fruitfly_agent/interactive/terminal/README.md#respond-to-permission-requests).

## Run and resume

After initial configuration:

```bash
.venv/bin/python -m fruitfly_agent "List the Python files here and explain what they do."
.venv/bin/python -m fruitfly_agent --resume
```

| Action | Behavior |
|---|---|
| Start without a task | Open the terminal interface. |
| Supply a task | Run a single task. |
| Use `--resume` | Restore the latest non-empty session after validation and display saved chat in interactive mode. |
| Use `--resume --session PATH` | Restore a specific session at startup. |
| Enter `/resume` | Choose a compatible session from the idle terminal and display saved chat. |
| Supply a task with `--resume` | Continue saved context for one task without printing old chat; model requests may incur charges. |
| Change configuration | Apply the selection to a new session. |

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

## Try optimization

Install the [Python task pack](examples/optimization/python_functions/README.md) into a destination that does not already exist:

```bash
mkdir -p .fruitfly/optimization/task-packs
cp -R examples/optimization/python_functions .fruitfly/optimization/task-packs/python-functions
.venv/bin/python -m fruitfly_agent.lab.optimization.verification check .fruitfly/optimization/task-packs/python-functions/pack.json
.venv/bin/python -m fruitfly_agent.lab.optimization.verification self-check .fruitfly/optimization/task-packs/python-functions/pack.json
```

The checks are offline. In **Configure → mechanisms · optimization**, enable **text-optimizer**, select **opro**, save, and start a new session. Use `/optimize` to select the pack and review the model, budget, and execution policy before confirming a paid search. The active target supplies the baseline; `baseline.txt` is an optional reference.

| Next step | Guide |
|---|---|
| Write your own tasks | [Task packs](fruitfly_agent/lab/optimization/TASK_PACKS.md) |
| Review and adopt a candidate | [Optimization](fruitfly_agent/lab/optimization/README.md) |
| Run the offline suite | [Tests](tests/README.md) |
| Make a real Provider smoke request | [Integration smoke](tests/integration/README.md) |
