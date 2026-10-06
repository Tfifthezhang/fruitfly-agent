# Configuration

[Up: FruitFlyAgent](README.md)

Keep model specifications, secrets, and runtime selections in separate files.

## Files and precedence

| Source | Default location | Contents |
|---|---|---|
| Model template | [models.example.yaml](models.example.yaml) | Public placeholder profiles for Responses and Messages APIs; copy and customize before use |
| Model catalog | `models.yaml` in the working directory | API protocol, model ID, endpoint, capabilities, limits, and key variable name |
| Secrets | `.env` or process environment | API key values |
| Harness configuration | `.fruitfly/config.yaml` | Profiles, catalog path, model choice, prompt references, and mechanism parameters |
| CLI overrides | Startup arguments | Workspace, configuration, profile, and session selection |

`--cwd`, `--config`, and `--profile` select the process's workspace and configuration. A relative `model.catalog` path resolves from the harness configuration file. The configuration menu saves choices for the next session; an active or resumed session keeps its validated runtime identity.

## Configure a model

Copy `models.example.yaml` to `models.yaml` and `.env.example` to `.env` if those local files do not already exist. The template uses placeholder model IDs, reserved `.invalid` endpoints, and illustrative limits. Replace them before making requests. Local `models.yaml` is ignored by VCS rules and excluded from source distributions.

| Field | What to enter |
|---|---|
| Key under `models` | Your profile name, selected in the terminal or via `FRUITFLY_MODEL_PROFILE` |
| `provider` | `openai` for Responses API, or `anthropic` for Messages API; this identifies the protocol, not the vendor |
| `model` | Exact model ID accepted by the service |
| `base_url` | Service URL for that protocol; omit to use the adapter SDK's default endpoint |
| `api_key_env` | Environment variable name; the template uses `MODEL_API_KEY`, whose value belongs in `.env` |
| `context_window`, `max_output_tokens` | Actual model limits; template numbers are examples |
| `capabilities` | Actual model and endpoint support, including tools and streaming |
| `parameters` | Optional adapter/request options; see the [Provider guide](fruitfly_agent/providers/PROVIDER_GUIDE.md) |

Keep only usable profiles. For different credentials, assign distinct `api_key_env` names and add their values to `.env`. Offline parsing validates the catalog structure; it does not verify remote API compatibility, model access, or declared limits. Requests use the network and may incur charges.

| Reference | Details |
|---|---|
| [Providers](fruitfly_agent/providers/README.md) | Model specifications and request behavior |
| [Provider guide](fruitfly_agent/providers/PROVIDER_GUIDE.md) | Protocol-specific parameters and reasoning limitations |
| [Harness schema](fruitfly_agent/run/configuration/README.md) | YAML example, validation, and persistence |
| [Run](fruitfly_agent/run/README.md) | CLI, assembly, artifacts, and recovery |

## Select a prompt or mechanism

| Selection | Default / behavior | Reference |
|---|---|---|
| Base prompt | `assistant-default`; choose another prompt in **Configure → Base prompt**. | [Base prompt](fruitfly_agent/lab/base_prompt/README.md) |
| Skill catalog | Read `.skills/`; enable in **Context Manager → Skill catalog**. | [Skills](fruitfly_agent/lab/context_manager/augmentation/skills/README.md) |
| Reduction | Summarizing; configure parameters in YAML. | [Reduction](fruitfly_agent/lab/context_manager/reduction/README.md) |
| Text optimizer | Disabled; OPRO is the built-in algorithm. | [Optimization](fruitfly_agent/lab/optimization/README.md) |
| Programmatic context | Explicitly enable `ipython-tool` or `rlm-ipython`. | [Programmatic context](fruitfly_agent/lab/context_manager/externalization/programmatic_context/README.md) |
| RSI | Host-injected capabilities and verification policy; no default CLI switch. | [RSI](fruitfly_agent/lab/rsi/README.md) |

Menus show mechanism switches and algorithm choices. Edit `.fruitfly/config.yaml` for detailed parameters. Summaries, optimization, and auxiliary model queries may incur model charges.

## Information sources

| Mechanism | Default | Parameters |
|---|---|---|
| `information-context` | Enabled, hidden dependency | `top_k=5`, `max_chars=4000` |
| `memory-files` | Enabled | `root=.fruitfly/memory` |
| `knowledge-files` | Disabled | `root=.fruitfly/knowledge` |
| `live-http` | Disabled | HTTPS `endpoint`, `timeout_seconds=5` |

Source paths resolve within the workspace. All three sources require `information-context`. Live HTTP sends the current query to the configured service. See [Information spaces](fruitfly_agent/lab/context_manager/augmentation/information/README.md).

## Text artifacts

| Field | Meaning |
|---|---|
| `prompt` | Built-in prompt ID or `sha256:…` text artifact; omission selects `assistant-default`. |
| `artifact_bindings` | Named text slots, such as `skill-catalog.guidance`, mapped to artifact IDs. |
| `RuntimeManifest` | Actual model, normalized mechanisms, implementation identities, prompt hash, and consumed artifacts. |

Create custom text with `DataArtifactStore.put_text`; see the [Run example](fruitfly_agent/run/README.md#text-artifacts). Artifacts are plaintext model instructions. Unknown or unused bindings are rejected; recovery verifies the original contents and manifest. Keep secrets out of artifacts, configuration, sessions, and reports.

## Environment variables

| Variable | Purpose |
|---|---|
| `FRUITFLY_MODEL_PROFILE` | Initial model choice when no harness configuration has been saved |
| `FRUITFLY_EVENT_STREAM_PATH` | Optional JSONL event output in one-shot mode |
| `NO_COLOR` | Disable terminal colors |
| Model-specific `api_key_env` | Name of the variable containing that model's API key |

`.env.example` contains public placeholders. Internal IPython subprocess variables are managed by the runtime and are not user settings.

## Results and state

| Data | Location / behavior |
|---|---|
| Sessions | `.fruitfly/sessions/`; canonical messages, context decisions, manifest, and concise run records |
| Candidates | `.fruitfly/optimization/candidates/`; latest complete result per configuration, profile, target, and task pack |
| Text contents | `.fruitfly/artifacts/`; immutable content-addressed artifacts |
| Readable task results | `.fruitfly/optimization/task-results/<pack-id>/<config-profile-scope>/<target>/`; `latest.txt` and `latest.json` |
| Explicit evolution jobs | `.fruitfly/evolution/`; host-owned phases, policy, and activation evidence |

Referenced results remain protected. Failed or cancelled searches do not replace a complete candidate. Editing a readable export does not change the runtime. See [Optimization](fruitfly_agent/lab/optimization/README.md#results-and-retention) for retention and [Run](fruitfly_agent/run/README.md#recovery) for compatibility rules.
