# Configuration

[Up: FruitFlyAgent](README.md)

Keep model specifications, secrets, and runtime selections in separate files.

## Files and precedence

| Source | Default location | Contents |
|---|---|---|
| Model template | [models.example.yaml](examples/configuration/models.example.yaml) | DeepSeek Flash profiles for Responses and Messages APIs in one file; configure a key before use |
| Model catalog | `.fruitfly/models.yaml` in the working directory | API protocol, model ID, endpoint, capabilities, limits, and key variable name |
| Secrets | `.fruitfly/secrets.env` or process environment | API key values |
| Harness configuration | `.fruitfly/config.yaml` | Profiles, catalog path, model choice, prompt references, and mechanism parameters |
| CLI overrides | Startup arguments | Workspace, configuration, profile, and session selection |

`--cwd`, `--config`, and `--profile` select the process's workspace and configuration. A relative `model.catalog` path resolves from the harness configuration file. The configuration menu saves choices for the next session; an active or resumed session keeps its validated runtime identity.

The Agent CLI reads `.fruitfly/secrets.env` from the selected workspace, including when using `--cwd`. Process environment values take precedence over that file, including explicit empty values. It does not fall back to another workspace's secret file.

Model discovery prefers `.fruitfly/models.yaml` and accepts root `models.yaml` when the new catalog is absent. A saved or explicitly selected catalog path always takes precedence. Secrets use `.fruitfly/secrets.env`, falling back to root `.env` only when the new file is absent. Files are never merged. The CLI reports when both old and new files exist. Existing workspace-local catalogs and credential files keep their selected locations when edited through the wizard.

## Relocate workspace configuration

Startup does not move existing files. Preview the explicit offline operation, then apply it if the listed paths are correct:

```bash
.venv/bin/python -m fruitfly_agent.run.migrate_configuration --cwd /path/to/workspace
.venv/bin/python -m fruitfly_agent.run.migrate_configuration --cwd /path/to/workspace --apply
```

Use `--config path/to/custom.yaml` to update a custom harness file. The operation moves root `models.yaml` and the entire root `.env` into `.fruitfly/`, removes their originals after successful writes, and updates every matching catalog reference in the selected harness file. Other harness files need separate path updates before relocation. Model and secret file contents remain unchanged; harness comments and unrelated settings remain. Existing destinations and symlinks are rejected. Ordinary failures attempt rollback; concurrent writers and process crashes are not covered. Stop other configuration writers before applying, then restart the CLI to reload secrets. Session recovery still verifies artifacts and the complete manifest.

## Configure a model

Run the interactive CLI. If no models are available, **Add model** opens automatically. Otherwise use **Configure → model → Add model…**. Choose a supported service, enter the model ID and documented token limits, and enter the key with hidden input. Custom services need a base URL. Review and stage the settings; **Start new session** or **Save and start new session** persists them.

| Service option | Use when |
|---|---|
| OpenAI official · Responses API | You use an OpenAI account and key; a blank address uses the SDK's official endpoint. |
| Anthropic official · Messages API | You use an Anthropic account and key; a blank address uses the SDK's official endpoint. |
| Custom · Responses API | Your gateway or self-hosted server supports Responses; enter its API address and key. |
| Custom · Messages API | Your gateway or self-hosted server supports Messages; enter its API address and key. |

The protocol determines request, streaming, and tool-call formats. Choose what your service actually supports; the model name alone does not establish compatibility. See [protocol differences](fruitfly_agent/providers/PROVIDER_GUIDE.md#protocol-differences).

After service selection, each field has its own screen with the selected service and step count. `models.<name>` is the catalog entry name shown in menus; `model` is the service model ID. Press Enter to accept a displayed default. API key input is hidden; review shows only that it was entered or reused. No connection test runs during setup.

An interactive first run without saved harness configuration or a workspace catalog starts a draft targeting the selected workspace's `.fruitfly/models.yaml`.

| Wizard behavior | Contract |
|---|---|
| Supported services | Official or custom Responses and Messages APIs; streaming and tool calls required. Chat Completions-only endpoints are unsupported. |
| Limits | User-supplied positive integers; output limit smaller than context window. No automatic model-limit inference. |
| Capabilities | Checkbox page: `tools` and `streaming` default true and are required; `parallel_tool_calls`, `vision`, and `reasoning` default false and can be toggled. Only declare verified service support. Reasoning selection does not enable request parameters or lossless replay. |
| Credentials | Hidden input bypasses readline history. Blank input reuses the named environment variable. Blank variable name generates `FRUITFLY_MODEL_<LABEL>_API_KEY`, replacing label punctuation with underscores. |
| Existing key | The Model menu shows only set/missing status. **Set API key…** supplies a missing key; an already-set different value is rejected. |
| Saving | Append a unique model label to the selected workspace-local catalog, update only supplied credential entries, and save harness selection. `.fruitfly/secrets.env` writes use owner-only permissions. Existing comments/models and unrelated environment lines remain. |
| Cancellation | `/cancel`, EOF, review cancellation, or configuration discard leaves the corresponding draft unsaved. Exiting startup discards pending changes. |
| Failures | Ordinary save failures attempt to restore model/credential files and retain the draft for retry; no cross-process or crash transaction. |
| Validation | Offline format/required-field checks only; no automatic network requests or connection tests. |

The wizard adds models with new labels; editing existing model specifications remains a YAML operation. It refuses additions to external or flow-style catalogs rather than rewriting them. Active and resumed sessions keep their original runtime identity. Newly saved credentials are available to the next session in the same process.

For manual setup, create `.fruitfly/`, then copy `examples/configuration/models.example.yaml` to `.fruitfly/models.yaml` and `examples/configuration/.env.example` to `.fruitfly/secrets.env` only if the local files do not already exist. The single catalog contains `deepseek-flash-openai` and `deepseek-flash-anthropic`, both using `deepseek-flash` and `DEEPSEEK_API_KEY` with DeepSeek endpoints. Configure your key and select one profile before making requests. See [example setup, budgets, and thinking limits](examples/configuration/README.md). Local `.fruitfly/models.yaml` is excluded from source distributions.

| Field | What to enter |
|---|---|
| Key under `models` | Your profile name, selected in the terminal or via `FRUITFLY_MODEL_PROFILE` |
| `provider` | `openai` for Responses API, or `anthropic` for Messages API; this identifies the protocol, not the vendor |
| `model` | Exact model ID accepted by the service |
| `base_url` | Service URL for that protocol; omit to use the adapter SDK's default endpoint |
| `api_key_env` | Environment variable name; the template uses `DEEPSEEK_API_KEY`, whose value belongs in `.fruitfly/secrets.env` |
| `context_window`, `max_output_tokens` | Actual model limits; template numbers are examples |
| `capabilities` | Actual model and endpoint support, including tools and streaming |
| `parameters` | Optional adapter/request options; see the [Provider guide](fruitfly_agent/providers/PROVIDER_GUIDE.md) |

Keep only usable profiles. For different credentials, assign distinct `api_key_env` names and add their values to `.fruitfly/secrets.env`. Offline parsing validates the catalog structure; it does not verify remote API compatibility, model access, or declared limits. Requests use the network and may incur charges.

| Reference | Details |
|---|---|
| [Providers](fruitfly_agent/providers/README.md) | Model specifications and request behavior |
| [Provider guide](fruitfly_agent/providers/PROVIDER_GUIDE.md) | Protocol-specific parameters and reasoning limitations |
| [Core runtime rules](fruitfly_agent/core/README.md#runtime-rules) | Embedded loop tool/turn budgets and the fixed three-response truncation ceiling; these are not new YAML fields. |
| [Harness schema](fruitfly_agent/run/configuration/README.md) | YAML example, validation, and persistence |
| [Run](fruitfly_agent/run/README.md) | CLI, assembly, artifacts, and recovery |

## Match menus to YAML

Menus use YAML keys and stable IDs. Descriptive text remains beside the identifiers. Existing YAML fields and schema versions are unchanged.

| Menu / form name | Stored location |
|---|---|
| `models.<name>` | Entry key under `models` in the model catalog |
| `provider`, `model`, `base_url`, `context_window`, `max_output_tokens`, `api_key_env` | Fields of that catalog entry; `provider` follows service selection |
| `capabilities` checkbox names | Boolean fields under the entry's `capabilities` mapping |
| `model` / `model.profile` | Harness profile's `model.profile` selection |
| `prompt` | Harness profile's `prompt` reference |
| `mechanisms · <category>` | Visual category of the harness `mechanisms` list; categories are not extra YAML fields |
| Mechanism name / algorithm `id` | `mechanisms[].id`; group names such as `reduction` organize alternatives, with the chosen algorithm ID stored |

The capability page uses arrows and Space/Enter to toggle, then **Continue** to confirm. Numbered fallback toggles the selected row and offers a numbered Continue action. Checked means `true`; unchecked means `false`. Required rows remain checked. Esc, `back`, q, or EOF cancels without staging.

## Select a prompt or mechanism

| Selection | Default / behavior | Reference |
|---|---|---|
| Base prompt | `assistant-default`; choose another prompt in **Configure → prompt**. | [Base prompt](fruitfly_agent/lab/base_prompt/README.md) |
| Skill catalog | Read `.skills/`; enable in **mechanisms · context-manager → skill-catalog**. | [Skills](fruitfly_agent/lab/context_manager/augmentation/skills/README.md) |
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
| `FRUITFLY_MODEL_PROFILE` | Initial model choice when no harness configuration has been saved; unset, empty, or whitespace-only means unselected |
| `FRUITFLY_EVENT_STREAM_PATH` | Optional JSONL event output in one-shot mode |
| `NO_COLOR` | Disable terminal colors |
| Model-specific `api_key_env` | Name of the variable containing that model's API key |

[Secret template](examples/configuration/.env.example) contains public placeholders. Internal IPython subprocess variables are managed by the runtime and are not user settings.

With no initial choice, a sole catalog entry is selected automatically. Multiple entries open provider-free interactive setup; one-shot startup requires an explicit choice. Unknown nonblank names are rejected with available choices. Saved harness selections take precedence over this variable. Optional Eval installation material is configured separately in [Eval](eval/README.md).

## Results and state

| Data | Location / behavior |
|---|---|
| Sessions | `.fruitfly/sessions/`; canonical messages, context decisions, manifest, and concise run records |
| Candidates | `.fruitfly/optimization/candidates/`; latest complete result per configuration, profile, target, and task pack |
| Text contents | `.fruitfly/artifacts/`; immutable content-addressed artifacts |
| Readable task results | `.fruitfly/optimization/task-results/<pack-id>/<config-profile-scope>/<target>/`; `latest.txt` and `latest.json` |
| Explicit evolution jobs | `.fruitfly/evolution/`; host-owned phases, policy, and activation evidence |

Referenced results remain protected. Failed or cancelled searches do not replace a complete candidate. Editing a readable export does not change the runtime. See [Optimization](fruitfly_agent/lab/optimization/README.md#results-and-retention) for retention and [Run](fruitfly_agent/run/README.md#recovery) for compatibility rules.
