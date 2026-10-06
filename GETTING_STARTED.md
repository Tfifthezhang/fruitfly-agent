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
cp models.example.yaml models.yaml
cp .env.example .env
```

## Choose a model

| Step | Action |
|---|---|
| 1 | Edit `models.yaml`: keep the matching API protocol and replace the placeholder model ID, endpoint, limits, and capabilities with values for your model. |
| 2 | Set the variable named by that model's `api_key_env` in `.env`. |
| 3 | Run `.venv/bin/python -m fruitfly_agent`. |
| 4 | Save your model selection, then choose **Start new session**. |

The [model template](models.example.yaml) provides `example-responses` (OpenAI Responses API) and `example-messages` (Anthropic Messages API). These are placeholder profiles, not working models. A Chat Completions-only endpoint cannot use the Responses adapter. Keep only profiles you need; rename them if desired. Use separate `api_key_env` names if profiles need different keys.

`models.yaml` is local configuration and excluded from source distributions; the public template contains no actual model selection. If you already have `models.yaml` or `.env`, edit the existing files instead of overwriting them. Keep API keys in `.env` or the process environment. See [Configuration](CONFIGURATION.md) for file locations and field meanings.

**Live tasks contact the configured model service and may incur charges. Local file and shell tools use your current user permissions and do not provide a sandbox.**

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
| Use `--resume` | Resume a compatible session after runtime validation. |
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

The checks are offline. In **Configure → Optimization**, enable **Text optimizer**, select **OPRO**, save, and start a new session. Use `/optimize` to select the pack and review the model, budget, and execution policy before confirming a paid search. The active target supplies the baseline; `baseline.txt` is an optional reference.

| Next step | Guide |
|---|---|
| Write your own tasks | [Task packs](fruitfly_agent/lab/optimization/TASK_PACKS.md) |
| Review and adopt a candidate | [Optimization](fruitfly_agent/lab/optimization/README.md) |
| Run the offline suite | [Tests](tests/README.md) |
| Make a real Provider smoke request | [Integration smoke](tests/integration/README.md) |
