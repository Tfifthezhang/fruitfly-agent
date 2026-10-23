# Configuration

[Up: FruitFlyAgent](README.md)

Keep model specifications, secrets, and runtime selections in separate files.

## Files and precedence

| Source | Default location | Contents |
|---|---|---|
| Model template | [models.example.yaml](examples/configuration/models.example.yaml) | DeepSeek Flash profiles for Responses and Messages APIs in one file; configure a key before use |
| Model catalog | `.fruitfly/models.yaml` in the working directory | API protocol, model ID, endpoint, capabilities, limits, and key variable name |
| Secrets | `.fruitfly/secrets.env` or process environment | API keys and SSH account/password values |
| Harness configuration | `.fruitfly/config.yaml` | Profiles, catalog path, model choice, prompt references, and mechanism parameters |
| Default configuration | `.fruitfly/default-config.yaml` | Independent baseline; editable manually, read-only in terminal configuration |
| Default model catalog | `.fruitfly/default-models.yaml` | Baseline model settings; may reference the same key variable as daily models |
| Eval host settings | `.fruitfly/eval-host.yaml` | Machine-local runtime mounts, task source and dependency/cache preparation; see [Harbor settings](eval/harbor/README.md) |
| CLI overrides | Startup arguments | Workspace, configuration, profile, and session selection |

`--cwd`, `--config`, and `--profile` select the process's workspace and configuration. `--approve-tools` explicitly answers tool confirmation requests for a fresh non-interactive task in a trusted isolated environment; protected paths remain denied. A relative `model.catalog` path resolves from the harness configuration file. Saving persists choices. An active runtime changes only through explicit Application replacement, including configuration application or recovery.

The Agent CLI reads `.fruitfly/secrets.env` from the selected workspace, including when using `--cwd`. Process environment values take precedence over that file, including explicit empty values. It does not fall back to another workspace's secret file.

Model discovery prefers `.fruitfly/models.yaml` and accepts root `models.yaml` when the new catalog is absent. A saved or explicitly selected catalog path always takes precedence. Secrets use `.fruitfly/secrets.env`, falling back to root `.env` only when the new file is absent. Files are never merged. The CLI reports when both old and new files exist. Existing workspace-local catalogs and credential files keep their selected locations when edited through the wizard.

## Restore default configuration

The home menu has **Start new session**, **Configure**, and **Exit**. In Configure
or `/config`, **Restore default configuration** is the final action before Back.
It reads `.fruitfly/default-config.yaml` and stages its prompt, mechanisms,
parameters and artifact bindings in the selected daily profile. Existing model
selection, catalog, credentials and other profiles remain unchanged. Experiment
bindings absent from the defaults are removed from the draft.

Review or adjust the draft, then save and apply to this conversation or save only.
Discard restores the previous saved choices. Staging and saving alone leave the
active runtime unchanged. Missing/invalid defaults
leave the draft unchanged; declared auxiliary models must exist in the daily
catalog. Each restoration reloads the file so manual edits are available immediately.

Copy [default-config.example.yaml](examples/configuration/default-config.example.yaml) and
[default-models.example.yaml](examples/configuration/default-models.example.yaml) to their
default paths only when absent. The template enables local execution, basic
read/Bash/edit/write tools and explicitly parameterized compaction. Default files
are edited manually. Explicit `--config .fruitfly/default-config.yaml` selections
have a read-only terminal controller.

[Eval](eval/README.md) uses the complete default profile, including its independent
model catalog, unless the request explicitly selects another configuration. The
two catalogs may reference the same key variable, such as `DEEPSEEK_API_KEY`.
Use distinct `api_key_env` names only for different credentials; updating a shared
key affects subsequent use of both catalogs. Keep values in the secret environment.
Agent configuration does not select an execution-permission policy.

## Apply settings to the current conversation

While idle, `/config` offers these choices after changes:

| Choice | Effect |
|---|---|
| Save and apply to this conversation | Save files, then rebuild using the current Session's recovery path. Keep its path and original messages. |
| Save only | Save files without changing the active runtime. A later start or recovery uses them. |
| Continue configuring | Keep editing the draft. |
| Discard changes | Restore saved choices without changing the active runtime. |

Application constructs and starts the candidate before replacing the incumbent.
Recovery validates recorded history and required artifacts. Changed context
mechanisms rebuild their model projection from canonical messages. Missing
artifacts, invalid settings or startup failures leave the old runtime usable;
configuration files already saved remain saved. No model or tool work is replayed.
The next submitted turn uses the applied model, prompt and components.

Application requires no active/queued task or improvement job. Rebuilding creates
fresh runtime resources and approval services; transient algorithm state and
remembered approval grants are not transferred. Persisted learning state follows
the selected component's own recovery contract. This changes configuration, not
Python source loaded into the process. Manually edited secret files still require
a process restart to reload; the built-in secret forms update the host after save.

## Relocate workspace configuration

Startup does not move existing files. Preview the explicit offline operation, then apply it if the listed paths are correct:

```bash
.venv/bin/python -m fruitfly_agent.run.migrate_configuration --cwd /path/to/workspace
.venv/bin/python -m fruitfly_agent.run.migrate_configuration --cwd /path/to/workspace --apply
```

Use `--config path/to/custom.yaml` to update a custom harness file. The operation moves root `models.yaml` and the entire root `.env` into `.fruitfly/`, removes their originals after successful writes, and updates every matching catalog reference in the selected harness file. Other harness files need separate path updates before relocation. Model and secret file contents remain unchanged; harness comments and unrelated settings remain. Existing destinations and symlinks are rejected. Ordinary failures attempt rollback; concurrent writers and process crashes are not covered. Stop other configuration writers before applying, then restart the CLI to reload secrets. Session recovery still verifies artifacts and the complete manifest.

## Configure a model

Run the interactive CLI. **Add model** opens when no models are available; otherwise use **Configure → model → Add model…**. Choose a supported service, enter the model ID and documented token limits, and enter the key with hidden input. Custom services need a base URL. Review and stage the settings; **Start new session**, **Save and apply to this conversation**, or **Save only** persists them.

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

The wizard adds models with new labels; editing existing model specifications remains a YAML operation. It refuses additions to external or flow-style catalogs rather than rewriting them. Saving alone leaves the active runtime unchanged. Newly saved credentials are available when settings are applied or a session starts in the same process.

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
| Context / Tools / Environment | Visual category of the harness `mechanisms` list; categories are not extra YAML fields |
| Readable mechanism / algorithm name | `mechanisms[].id`; group names such as `reduction` organize alternatives, with the chosen algorithm ID stored |

The capability page uses arrows and Space/Enter to toggle, then **Continue** to confirm. Numbered fallback toggles the selected row and offers a numbered Continue action. Checked means `true`; unchecked means `false`. Required rows remain checked. Esc, `back`, q, or EOF cancels without staging.

## Select a prompt or mechanism

| Selection | Default / behavior | Reference |
|---|---|---|
| Base prompt | `assistant-default`; choose another prompt in **Configure → prompt** or `/config`. | [Base prompt](fruitfly_agent/lab/base_prompt/README.md) |
| Skill catalog | Read `.skills/`; enable in **Context → Context augmentation → Skill catalog** (Space toggles; the phase is a section heading). | [Skills](fruitfly_agent/lab/context_manager/augmentation/skills/README.md) |
| Reduction | Summarizing; inspect the mechanism in Context and edit tuning parameters in YAML. | [Reduction](fruitfly_agent/lab/context_manager/reduction/README.md) |
| Improvement | Choose materials, components, generator, exploration, allocations and scope in `/improvement`; no per-algorithm switch. | [Improvement](fruitfly_agent/lab/improvement/README.md) |
| Reusable skill document | Disabled; Context augmentation. Set `source_path` to one workspace-relative Skill or enter `initial_text`; `max_chars=16000`. | [Skill body](fruitfly_agent/lab/context_manager/augmentation/skills/README.md#optimize-a-skill-body) |
| Learned environment memory | Disabled; Context augmentation. Enter `initial_text`; `max_chars=16000`. Updates require explicit Improvement and adoption. | [Learned memory](fruitfly_agent/lab/context_manager/augmentation/information/file_memory/README.md#learn-environment-memory) |
| Execution workflow | Disabled; a bounded sequence of model stages. One solve-and-answer step until an artifact is selected. | [Workflow](fruitfly_agent/lab/workflow/README.md) |
| Web search / fetch | Disabled; enable **Search the web** and **Fetch web pages** under Tools. Search uses Brave, Tavily or DeepSeek. Fetch uses `direct` (no key) or `deepseek`. Expand either tool and choose **Set up…** to select the service and enter a hidden API key. Save writes the secret file. DeepSeek search/fetch use separate default variables; `api_key_env` can select a shared key. | [Web tools and YAML settings](fruitfly_agent/lab/tools/web/README.md) |
| Programmatic context | Explicitly enable `ipython-tool` or `rlm-ipython`. | [Programmatic context](fruitfly_agent/lab/context_manager/externalization/programmatic_context/README.md) |
| Remote execution | Enable **Remote environment** under Environment to run file and Bash tools through SSH. Complete settings and credentials are reused; missing values open the six-step form. Expand **Set up…** to edit explicitly. Disabling retains saved settings across restarts in the same workspace/profile. Mutually exclusive with local execution, local IPython/RLM and file memory. | [SSH setup and limits](fruitfly_agent/lab/environment/ssh/README.md) |
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
| `artifact_bindings` | Named slots such as `skill-catalog.guidance`, `tool-guidance.<name>`, `execution-workflow`, `skill-document` and `learned-memory`, mapped to text artifact IDs. |
| `RuntimeManifest` | Actual model, normalized mechanisms, implementation identities, prompt hash, and consumed artifacts. |

Create custom text with `DataArtifactStore.put_text`; see the [Run example](fruitfly_agent/run/README.md#text-artifacts). Artifacts are plaintext model instructions. Unknown or unused bindings are rejected; recovery verifies the original contents and manifest. Keep secrets out of artifacts, configuration, sessions, and reports.

`tool-guidance.<name>` replaces an enabled tool description with its owner-validated text. `/improvement` selects one or more editable components. A joint candidate expands into ordinary prompt/artifact bindings; tool schemas, execution and permissions retain their existing contracts. Preview is offline; execution may incur model and external-runner costs.

`execution-workflow` validates bounded stage instructions. `skill-document` and `learned-memory` are retained S documents; adopted artifacts override initial text. `improvement-editor` is a six-field I instruction artifact. The registered editor-comparison execution can modify `invariant`, `domain` and `compose`; `system`, `select` and `reflect` stay fixed during an experiment. Persistent publication requires independent verification and explicit adoption.

## Environment variables

| Variable | Purpose |
|---|---|
| `FRUITFLY_MODEL_PROFILE` | Initial model choice when no harness configuration has been saved; unset, empty, or whitespace-only means unselected |
| `FRUITFLY_EVENT_STREAM_PATH` | Optional JSONL event output in one-shot mode |
| `NO_COLOR` | Disable terminal colors |
| Model-specific `api_key_env` | Name of the variable containing that model's API key |
| `FRUITFLY_SSH_USERNAME` / `FRUITFLY_SSH_PASSWORD` | Secret SSH account/password; `ssh-env.username_env` and `password_env` can select different variable names |
| `BRAVE_SEARCH_API_KEY` / `TAVILY_API_KEY` | Secret used by the selected web search backend; optional `web-search-tool.api_key_env` overrides the variable name |
| `DEEPSEEK_API_KEY` | Model credential used by the DeepSeek model examples |
| `DEEPSEEK_SEARCH_API_KEY` / `DEEPSEEK_FETCH_API_KEY` | Separate default secrets for DeepSeek search and fetch. Each tool's `api_key_env` can select another variable, including the model key when explicit reuse is wanted. |

[Secret template](examples/configuration/.env.example) contains public placeholders. Internal IPython subprocess variables are managed by the runtime and are not user settings.

With no initial choice, a sole catalog entry is selected automatically. Multiple entries open provider-free interactive setup; one-shot startup requires an explicit choice. Unknown nonblank names are rejected with available choices. Saved harness selections take precedence over this variable. Optional Eval installation material is configured separately in [Eval](eval/README.md).

## Results and state

| Data | Location / behavior |
|---|---|
| Sessions | `.fruitfly/sessions/`; canonical messages, context decisions, manifest, and concise run records |
| Experiment history | `.fruitfly/improvement/runs/`; scoped run summaries, including empty, failed and cancelled jobs |
| Candidates | `.fruitfly/improvement/candidates/`; latest complete result per configuration, profile, target, and task pack |
| Text contents | `.fruitfly/artifacts/`; immutable content-addressed artifacts |
| Workflow records | `.fruitfly/improvement/jobs/<job-id>/`; frozen plan, journal and result |
| Experience | `.fruitfly/improvement/experience.json`; explicitly committed library included in S identity |
| Pending lessons | `.fruitfly/improvement/experience-pending/`; review before commit/reject |
| Editor experiments | `.fruitfly/improvement/experiments/<id>/experiment.json`; references disjoint task packages |
| Private-suite claims | `.fruitfly/improvement/verification-uses.json`; completed or uncertain verification consumes a declared use |
| Explicit evolution jobs | `.fruitfly/evolution/`; host-owned phases, policy, and activation evidence |

Referenced results remain protected. Failed or cancelled searches do not replace a complete candidate. Editing a readable export does not change the runtime. See [Improvement](fruitfly_agent/lab/improvement/README.md#results-and-retention) for retention and [Run](fruitfly_agent/run/README.md#recovery) for compatibility rules.

## Host execution policies

The standard interactive host uses its built-in guarded strategy: ordinary
workspace files are accessible, credential paths are protected, and external
file access or code execution requests confirmation. There is no permission
configuration file or menu. Embedded hosts can inject `PermissionPolicy` through
`RunApplicationFactory(permission_policy=...)` or `build_runtime(permission_policy=...)`.
Model/harness YAML cannot select or expand host permissions.

| Launch | Tool execution |
|---|---|
| Normal interactive/headless | Guarded; unavailable confirmation means deny |
| Fresh headless `--approve-tools` | Approve ordinary confirmation requests once; protected checks remain |
| Fresh headless `--unrestricted` | Skip application permission checks, preserve the backend and its task environment |

`--unrestricted` requires a new non-interactive task, rejects resume and conflicts
with `--approve-tools`. It does not detect Docker or create isolation. Eval passes
it explicitly inside Harbor task containers; Harbor/Docker bound filesystem,
process and network access. Timeout, cancellation, cleanup and logging still run.
The unrestricted strategy permits access to files normally protected by the
application, including credential and Session paths. Reports identify this mode.

Host code can construct the same strategy with `PermissionPolicy.unrestricted(workspace)`.
Assembly calls `prepare_environment` and `bind` on the chosen strategy; tools and
Agent algorithms share the same execution path. No benchmark conditions enter
Core. See [Run](fruitfly_agent/run/README.md#bind-host-permission-policy) and
[Environment](fruitfly_agent/lab/environment/README.md#select-an-execution-strategy).

Configuration forms share a credential draft saved alongside harness/model changes.
SSH account/password input uses the same hidden-input and ignored secret-file
storage as API keys. Only variable names enter mechanism parameters. Cancel and
discard do not persist new credentials; ordinary save failures roll back written
files. Restricting model file tools does not disable configuration forms.
Runtime approval is temporary and never saved as a permanent grant. Approved
local code still has current-user permissions; isolation is not implemented.

Host-owned `PermissionPolicy.allow_network=True` allows declared network-read tools; false denies them before execution. This does not restrict Providers, live context or approved shell code. Search/fetch credentials use the same process-over-secret-file precedence as model credentials. Their **Set up…** forms accept hidden keys and share the model credential draft and save transaction. Keys are written only when configuration is saved; manual secret-file/environment setup remains supported. Never put key values in mechanism parameters.

### Bound registered improvement execution

All editor requests and leaf task executions, including nested experiments and
verification, share one root allowance. Child budgets hold quota and charge leaf
work once. Final selection and independent verification retain protected quota;
unspent search allowance can supplement final verification. Missing token/cost
usage remains unknown. Task and parent-operation timeouts bound child operations.
External execution needs an explicitly registered compatible runner; the native
file workspace does not inherit Bash, network tools, containers or live Session.

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

## Choose a candidate generator

`/improvement` selects task materials, components, generator, exploration, feedback
and effect scope. `GeneratorRegistry` declares factories and capabilities;
`WorkflowRequest` freezes each job. Discovery and previews make no model requests.
Retired algorithm selections are rejected, including disabled YAML entries. Remove
them explicitly; there is no automatic equivalence to the new generator contract.
Legacy namespace migration preserves historical data and does not translate those
retired algorithms into the new workflow.

## Configure the component editor

The hidden default `component-improvement` registration has `editor_profile`
(empty reuses the active model), `max_model_calls=64`, `max_executions=32` and
`operation_timeout=120`. Model profiles use the existing catalog and secret
configuration. Registration and previews make no model requests. Per-job component,
generator, exploration, feedback and scope choices belong to `/improvement`.

Python embeddings inject `WorkflowBindings` into `RunApplicationFactory` to replace
stages. Changing an execution backend requires a compatible `TaskRunner`; the
native improvement file workspace does not inherit the active SSH/Bash environment.
No dedicated search-tool API key is needed for component editing; web search/fetch
credentials remain independent tool settings.

## Configure an editor comparison

In `/improvement`, choose **Execution strategy → Editor self-improvement** and an
installed experiment under **Task**. **Execution parameters** declares inner H/S
components, repetitions, inner allocations, development trial limit and fixed
acceptance thresholds. These are per-job settings, not new model credentials or
harness YAML fields. The strategy recommends 512 root model calls and 256 leaf
executions; preview rejects a budget below its calculated minimum. Longer model
latency or larger suites may require a higher operation timeout and allocations.
Actual calls incur cost only after explicit confirmation.

Prepare independent development and verification packages, each with train,
selection and holdout. The exact manifest, parameters, data separation, proof and
limits are documented in [Editor self-improvement](fruitfly_agent/lab/improvement/improver/README.md).
Selecting I alone does not grant execution support; ordinary file trials reject I
and mixed outer H/S/I comparison is unsupported.

Every task execution uses fixed components. Search stopping is recorded separately
from `selected` or `verified` assurance. A task-local result changes no default.
Lessons remain pending until **Results and history → Pending experience** explicitly
commits or rejects them. A library change invalidates a stale pending commit.
Persistent I experiments cannot write production experience.
