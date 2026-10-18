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
| `parameters` | Optional adapter/request options, including validated waiting deadlines and retry settings; see the [Provider guide](fruitfly_agent/providers/PROVIDER_GUIDE.md#bound-waiting-and-retries) |

Keep only usable profiles. For different credentials, assign distinct `api_key_env` names and add their values to `.fruitfly/secrets.env`. Offline parsing validates the catalog structure; it does not verify remote API compatibility, model access, or declared limits. Requests use the network and may incur charges.

| Reference | Details |
|---|---|
| [Providers](fruitfly_agent/providers/README.md) | Model specifications and request behavior |
| [Provider guide](fruitfly_agent/providers/PROVIDER_GUIDE.md) | Protocol-specific parameters and reasoning limitations |
| [Core runtime rules](fruitfly_agent/core/README.md#runtime-rules) | Embedded loop tool/turn budgets and the fixed three-response truncation ceiling; these are not new YAML fields. |
| [Harness schema](fruitfly_agent/run/configuration/README.md) | YAML example, validation, and persistence |
| [Run](fruitfly_agent/run/README.md) | CLI, assembly, artifacts, and recovery |

## Match menus to YAML

Mechanism and algorithm menus use readable registered names. Stable IDs remain in implementation details and YAML. Model forms retain their documented field names. Stored fields and schema versions are unchanged.

| Menu / form name | Stored location |
|---|---|
| `models.<name>` | Entry key under `models` in the model catalog |
| `provider`, `model`, `base_url`, `context_window`, `max_output_tokens`, `api_key_env` | Fields of that catalog entry; `provider` follows service selection |
| `capabilities` checkbox names | Boolean fields under the entry's `capabilities` mapping |
| `model` / `model.profile` | Harness profile's `model.profile` selection |
| `prompt` | Harness profile's `prompt` reference |
| Context / Tools / Environment / Learning | Visual category of the harness `mechanisms` list; categories are not extra YAML fields |
| Readable mechanism / algorithm name | `mechanisms[].id`; group names such as `reduction` organize alternatives, with the chosen algorithm ID stored |

The capability page uses arrows and Space/Enter to toggle, then **Continue** to confirm. Numbered fallback toggles the selected row and offers a numbered Continue action. Checked means `true`; unchecked means `false`. Required rows remain checked. Esc, `back`, q, or EOF cancels without staging.

## Select a prompt or mechanism

| Selection | Default / behavior | Reference |
|---|---|---|
| Base prompt | `assistant-default`; choose another prompt in **Configure → prompt**. | [Base prompt](fruitfly_agent/lab/base_prompt/README.md) |
| Skill catalog | Read `.skills/`; enable in **Context → Context augmentation → Skill catalog** (Space toggles; the phase is a section heading). | [Skills](fruitfly_agent/lab/context_manager/augmentation/skills/README.md) |
| Reduction | Summarizing; expand Reduction to edit typed parameters, or use YAML. | [Reduction](fruitfly_agent/lab/context_manager/reduction/README.md) |
| Improvement methods | Select compatible methods directly in `/improvement`; no algorithm enable switch. Workflow search, Skill document optimization and Exploratory memory learning require their object mechanisms. | [Improvement](fruitfly_agent/lab/improvement/README.md) |
| Reusable skill document | Disabled; Context augmentation. Set `source_path` to one workspace-relative Skill or enter `initial_text`; `max_chars=16000`. | [Skill body](fruitfly_agent/lab/context_manager/augmentation/skills/README.md#optimize-a-skill-body) |
| Learned environment memory | Disabled; Context augmentation. Enter `initial_text`; `max_chars=16000`. Updates require explicit Improvement and adoption. | [Learned memory](fruitfly_agent/lab/context_manager/augmentation/information/file_memory/README.md#learn-environment-memory) |
| Execution workflow | Disabled; a bounded sequence of model stages. One solve-and-answer step until an artifact is selected. | [Workflow](fruitfly_agent/lab/workflow/README.md) |
| Failure processing | Optional YAML workflow dependency; benchmark jobs use failed-task replay on demand. | [Failure processing](fruitfly_agent/lab/improvement/failure_processing/README.md) |
| Automatic text search | Benchmark jobs assemble confirmation on demand. Optional YAML `automatic-text-search` also supports saved packages with holdout; adoption requires human review. | [Automatic workflow and parameters](fruitfly_agent/lab/improvement/automatic/README.md) |
| Programmatic context | Explicitly enable `ipython-tool` or `rlm-ipython`. | [Programmatic context](fruitfly_agent/lab/context_manager/externalization/programmatic_context/README.md) |
| RSI | Host-injected capabilities and verification policy; no default CLI switch. | [RSI](fruitfly_agent/lab/rsi/README.md) |

Menus show mechanism switches and algorithm choices. Edit `.fruitfly/config.yaml` for detailed parameters. Summaries, improvement, and auxiliary model queries may incur model charges.

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
| `artifact_bindings` | Named slots such as `skill-catalog.guidance`, `execution-workflow`, `skill-document` and `learned-memory`, mapped to text artifact IDs. |
| `RuntimeManifest` | Actual model, normalized mechanisms, implementation identities, prompt hash, and consumed artifacts. |

Create custom text with `DataArtifactStore.put_text`; see the [Run example](fruitfly_agent/run/README.md#text-artifacts). Artifacts are plaintext model instructions. Unknown or unused bindings are rejected; recovery verifies the original contents and manifest. Keep secrets out of artifacts, configuration, sessions, and reports.

`execution-workflow` validates JSON stage instructions. `skill-document` and `learned-memory` are S documents and enter persistent-state identity rather than H identity. Adopted artifacts take precedence over configured initial text. Each slot must be consumed by its enabled object mechanism. The three methods require task packs with independent holdout; they confirm one selected candidate before publication. See the [offline three-method example](examples/improvement/native_methods/README.md).

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
| Experiment history | `.fruitfly/improvement/runs/`; scoped run summaries, including empty, failed and cancelled jobs |
| Candidates | `.fruitfly/improvement/candidates/`; latest complete result per configuration, profile, target, and task pack |
| Text contents | `.fruitfly/artifacts/`; immutable content-addressed artifacts |
| Readable task results | `.fruitfly/improvement/task-results/<pack-id>/<config-profile-scope>/<target>/`; `latest.txt` and `latest.json` |
| Explicit evolution jobs | `.fruitfly/evolution/`; host-owned phases, policy, and activation evidence |

Referenced results remain protected. Failed or cancelled searches do not replace a complete candidate. Editing a readable export does not change the runtime. See [Improvement](fruitfly_agent/lab/improvement/README.md#results-and-retention) for retention and [Run](fruitfly_agent/run/README.md#recovery) for compatibility rules.

## Configure host permissions

The standard Run host uses a lightweight file and local-execution policy. Additional roots and sensitive paths are supplied through `RunApplicationFactory(permission_policy=...)` or `build_runtime(permission_policy=...)`, using `PermissionPolicy` from `fruitfly_agent.lab.catalog`. They are not YAML model or harness parameters. See [Run permission policy](fruitfly_agent/run/README.md#bind-host-permission-policy) and [Environment permissions](fruitfly_agent/lab/environment/README.md#apply-lightweight-permissions).

Model setup owns credential persistence. Restricting model file tools does not disable Add model or Set API key. Runtime approval is temporary and never saved as a permanent grant. Approved local code still has current-user permissions; isolation is not implemented.

### Configure original-task experiment limits

`automatic-text-search` also accepts `external_trial_model_calls` (24), `external_trial_timeout_seconds` (1800), and `external_timeout_seconds` (14400), all positive integers. They bound each original-task model allocation, individual task deadline and whole benchmark improvement deadline. Original tasks, derived exercises, material preparation and candidate search share the improver root budget. Configuring these values starts no model work. See [Original task experiments](fruitfly_agent/lab/improvement/experiments/README.md).

## Configure daily learning material

Enable **Learning → Learning materials** with Space. Its built-in implementation,
**Record completed tasks**, works without an improver. Expand it to configure `trigger`
(`task`, `session`, or `batch`), `batch_size`, `max_records`, and `max_chars` in
its inline fields or YAML; see [Learning](fruitfly_agent/lab/learning/README.md). Records under
`.fruitfly/learning/materials/` remain pending until a registered method supplies
validated acceptance evidence. Recording does not call a model, change H/S/I,
start a search, or assign observations to independent confirmation.

## Relocate improvement data

Use the explicit offline entry to preview, then apply the namespace migration:

```bash
.venv/bin/python -m fruitfly_agent.run.migrate_improvement --workspace /path/to/workspace
.venv/bin/python -m fruitfly_agent.run.migrate_improvement --workspace /path/to/workspace --apply
```

`/path/to/workspace` is a placeholder. The operation makes no network or model
requests. It rejects conflicting data roots and symlinks, preserves original
configuration and data under `.fruitfly/migration-backups/`, and updates only
supported legacy parameter names and paths. User comments remain intact.
Immutable journals, task snapshots, source snapshots and content-addressed
artifacts retain their original bytes and hashes. Migrated candidate evidence
paths point to the relocated files; pending candidates become stale and need
fresh evaluation before adoption. Historical Session manifests remain unchanged.
The runtime uses only the new namespace and rejects an unmigrated data root.
Custom legacy targets require explicit role classification before migration.
Run one migration coordinator while the Agent is stopped; there is no
cross-process transaction. Repeating a completed migration makes no changes.

## Choose a method for one improvement job

The configuration menu has no improvement category. `/improvement` discovers registered compatible methods, binds the selected method on demand and previews its requirements and budget. The experiment panel offers Target, Task, Budget and Evaluation. Expand Target to select the object and then its algorithm; algorithms show concise descriptions and implementation/guide paths under Target. Internal tuning stays in YAML at the displayed file/profile/mechanism location, or in programmatic previews. Task holds source/material choices and Budget holds limits. Field input preserves the page and focus while showing live text, current values and rules. The terminal offers no internal tuning list or JSON override editor. Search guidance appears only when declared by the method and may be empty; scoring and acceptance remain separate. Confirmed choices persist separately under `.fruitfly/improvement/preferences/`, scoped to configuration/profile/target; they do not change YAML or the parent optimizer version. Existing YAML method entries remain optional parameter defaults; disabled entries do not prevent command selection. Legacy enabled hosts remain supported. The preview shows the selected implementation and normalized parameters. New auxiliary model profiles still require configuration and a new session. See [Method selection](fruitfly_agent/lab/improvement/README.md#select-methods-without-changing-defaults).

## Configure DreamRSI

Tree search registers its I exploration-policy target independently of method enablement. Optional disabled YAML method entries can store replay/confirmation parameter defaults. Registration performs no search. Collect H discovery histories, then explicitly choose DreamRSI for the I policy target. [DreamRSI](fruitfly_agent/lab/improvement/methods/dream_rsi/README.md#configure-method-entries) describes task packs, feedback, history paths and paired confirmation budgets. Generated policy JSON is stored as an I artifact; it is not executed as Python.
