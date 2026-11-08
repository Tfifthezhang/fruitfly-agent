# Configuration

[Up: FruitFlyAgent](README.md)

Keep model specifications, secrets, and runtime selections in separate files.

## Navigate the configuration tree

```text
Configuration overview (this page)
├── Runtime specification / Component documents: write H/S/I and model roles
├── Catalog / Configurable components: register your own implementation
├── Experiments / Experiment configuration: tasks, edit grants and comparison
└── Configuration and experiment examples: initialize, inspect and run
```

| Task | Authoritative guide |
|---|---|
| Write a system config or H/S/I document | [Component documents](fruitfly_agent/runtime_spec/COMPONENTS.md) |
| Register a component and expose its fields | [Catalog configuration](fruitfly_agent/lab/catalog/CONFIGURATION.md) |
| Write an experiment and authorize changes | [Experiment configuration](fruitfly_agent/experiments/CONFIGURATION.md) |
| Start from installed templates | [Configuration examples](examples/configuration/README.md) and [experiment recipes](examples/experiments/README.md) |
| Inspect or export an existing system | [Run configuration](fruitfly_agent/run/configuration/README.md) |

System files use one component format without a configuration version marker. `config.yaml`, `default-config.yaml` and generated
candidate configs use the same protocol. Each profile selects model aliases and
referenced H/S/I documents. H contains execution instructions/mechanisms, S
retained content, and I editor/evaluator prompts. Short text uses YAML
block scalars; no separate prompt text file is required. Registered definitions
own defaults and legal fields; experiment grants own modification permission.
Unknown fields and obsolete flat profile fields are rejected.

## Files and precedence

| Source | Default location | Contents |
|---|---|---|
| Model template | [models.example.yaml](examples/configuration/models.example.yaml) | DeepSeek Flash profiles for Responses and Messages APIs in one file; configure a key before use |
| Shared model catalog | `.fruitfly/models.yaml` in the working directory | Daily and experiment model definitions: SDK, API protocol, model ID, endpoint, capabilities, limits, and key variable name |
| Secrets | `.fruitfly/secrets.env` or process environment | API keys and SSH account/password values |
| Harness configuration | `.fruitfly/config.yaml` | Profiles, model roles and selected H/S/I component documents |
| Component defaults | Owner YAML resources in `fruitfly_agent/lab/` | One registered default document per parameterized component, including its H/S/I role |
| Optional MCP services | `.fruitfly/mcp.yaml` | Local stdio commands, selected tool names, limits and secret-variable references |
| Default configuration | `.fruitfly/default-config.yaml` | Independent baseline; editable manually, read-only in terminal configuration |
| Eval host settings | `.fruitfly/eval-host.yaml` | Machine-local runtime mounts, task source and dependency/cache preparation; see [Harbor settings](fruitfly_eval/harbor/README.md) |
| Experiment settings | `.fruitfly/experiment.yaml` | Baseline/tasks, edit grants, execution, evidence, evaluation, stopping and RSI |
| Task documents | `.fruitfly/tasks/` | Task sources and material references; comparison settings belong to experiment evaluation |
| CLI overrides | Startup arguments | Workspace, configuration, profile, and session selection |

`--cwd`, `--config`, and `--profile` select the process's workspace and configuration. `--approve-tools` explicitly answers tool confirmation requests for a fresh non-interactive task in a trusted isolated environment; protected paths remain denied. A relative catalog path resolves from the system config; component/task references resolve from their declaring files. Saving persists choices. An active runtime changes only through explicit Application replacement, including configuration application or recovery.

The Agent CLI reads `.fruitfly/secrets.env` from the selected workspace, including when using `--cwd`. Process environment values take precedence over that file, including explicit empty values. It does not fall back to another workspace's secret file.

Model discovery uses `.fruitfly/models.yaml`. An explicitly selected catalog path takes precedence. Secrets use `.fruitfly/secrets.env` and the process environment; root `.env` and root `models.yaml` are not implicit inputs. Explicit custom catalog paths remain supported.

Daily and experiment configs reference the shared `models.yaml`. Each profile's
`models.roles` selects the executor alias and auxiliary aliases or
`{inherit: executor}` references. Auxiliary roles inherit executor by default. To use
different parameters for the same API model, define distinct aliases in the shared
catalog. Editing an entry affects subsequent loads of every config selecting that
alias; an active runtime and frozen experiment inputs retain their loaded values.

## Restore default configuration

The CLI opens an offline startup panel. Choose Configure, use `/config` in chat,
or run `fruitfly-agent --configure` to edit settings. **Restore default configuration**
is the final action before Back.
It reads `.fruitfly/default-config.yaml` and stages its prompt, mechanisms,
parameters, execution limits and artifact bindings in the selected daily profile. Existing model
selection, catalog, credentials and other profiles remain unchanged. Experiment
bindings absent from the defaults are removed from the draft.

Review or adjust the draft, then apply it to this conversation or discard it.
Discard restores the previous saved choices. Staging and saving alone leave the
active runtime unchanged. Missing/invalid defaults
leave the draft unchanged; declared auxiliary models must exist in the daily
catalog. Each restoration reloads the file so manual edits are available immediately.

Initialize the system files, or copy [default-config.example.yaml](examples/configuration/default-config.example.yaml),
[models.example.yaml](examples/configuration/models.example.yaml) only when absent. Registered defaults stay in their owning modules; initialization does not copy a components tree. The template enables local execution, basic
read/Bash/edit/write tools, a shared Tool catalog policy and deterministic layered compaction. Default files
are edited manually. Explicit `--config .fruitfly/default-config.yaml` selections
have a read-only terminal controller.

Alternatively, `fruitfly-agent-lab init` generates these system defaults and an
empty-key secret file; it does not generate an experiment or task executor. Existing
regular model catalogs and secrets are reused unchanged; other existing
configuration destinations are rejected. When reusing a catalog, select its
actual aliases in `default-config.yaml` before checking the experiment.
`init --source task-set --benchmark terminal-bench-4` generates a benchmark
experiment, task collection, request and host template with explicit Linux runtime path variables. Initialization reads no
private project settings and performs no model, Docker or installation work.
See [experiment setup](examples/experiments/README.md).

[Eval](fruitfly_eval/README.md) uses the complete default profile and its selected aliases
from the shared model catalog, unless the request explicitly selects another
configuration. Use distinct `api_key_env` names for different credentials;
updating a shared key affects subsequent use of every model referencing it.
Keep values in the secret environment.
Agent configuration does not select an execution-permission policy.

## Apply settings to the current conversation

While idle, `/config` offers these choices after changes:

| Choice | Effect |
|---|---|
| Save and apply to this conversation | Prepare and start the draft, then commit its files and runtime using the current Session. Keep its path and original messages. |
| Continue configuring | Keep editing the draft. |
| Discard changes | Restore saved choices without changing the active runtime. |

The menu submits draft intent without saving files or constructing algorithms.
Component registration and assembly own interface, dependency and lifecycle
contracts. Application uses the host's `prepare_configuration(session_path=...)`
operation to construct and start the candidate before replacing the incumbent.
Recovery validates recorded history and required artifacts. Changed context
mechanisms rebuild their model projection from canonical messages. Preparation,
startup or commit failure retains the old runtime, restores files written by the
commit, and keeps the draft for editing or retry through `/config`. New model
entries and hidden credentials share this boundary. No model or tool work is
replayed. External service effects and process crashes are not file transactions.
The next submitted turn uses the applied model, prompt and components. Successful
application adds a short confirmation without printing another welcome page.

Application requires no active/queued task or improvement job. Rebuilding creates
fresh runtime resources and approval services; transient algorithm state and
remembered approval grants are not transferred. Persisted learning state follows
the selected component's own recovery contract. This changes configuration, not
Python source loaded into the process. Manually edited secret files still require
a process restart to reload; the built-in secret forms update the host after save.

## Connect MCP tools

Install the optional `fruitfly-agent[mcp]` extra and install each server separately.
Copy [mcp.example.yaml](examples/configuration/mcp.example.yaml) to
`.fruitfly/mcp.yaml` only when absent, then replace its placeholders. Enable
`mcp-tools` under Tools; its `config` parameter defaults to that workspace-local
file. Saving alone starts nothing. Start or apply the profile to review and
authorize each local stdio process before its catalog is frozen.

Keep credentials in the secret environment. `secret_env` maps child variable names
to host variable names; `env` contains non-secret values recorded in identity.
The CLI denies process startup without an interactive TTY; embedders must supply
an explicit startup approval callback. Tool calls then use separate per-tool
approvals. Local execution grants do not authorize MCP calls.

Stdio runs on the local Agent host even when the file/Bash execution environment
is remote. `/lab` shows both independently. Catalog changes and disconnected or
uncertain calls require explicit configuration application; there is no automatic
restart or replay. See [the client guide](fruitfly_agent/lab/mcp/README.md) for
limits, supported schemas, artifacts and recovery, or the independent
[REA example](examples/mcp/rea/README.md). HTTP/OAuth and an outbound FruitFlyAgent
MCP server are not implemented.

## Configure a model

Run the interactive CLI and choose **Configure → model → Add model…**. In chat use **/config → model → Add model…**; `--configure` opens the shared editor first. Choose a service, choose its protocol, then enter the model ID, documented token limits and hidden API key. The SDK is automatic and appears read-only in review. Custom services need a base URL. Review and stage the settings; **Save and return** saves them offline and returns to the startup panel, while **Save and apply to this conversation** commits them after candidate startup succeeds.

| Service | Protocol choices |
|---|---|
| OpenAI | Responses or Chat Completions |
| Anthropic | Native Messages or Chat Completions compatibility |
| DeepSeek | Responses, Messages or Chat Completions |
| Qwen | Responses, Messages or Chat Completions |
| Custom service… | Registered protocols; supply the gateway/server's address and key |

Every service opens a protocol selection before its form. Choices come from
Provider service rules intersected with registered adapters. The protocol determines
request, streaming, and tool-call formats. Choose what your service actually
supports; the model name alone does not establish compatibility. See
[protocol configuration](fruitfly_agent/providers/PROVIDER_GUIDE.md#choose-the-protocol-and-service).

After protocol selection, each field has its own screen with the selected service and step count. `models.<name>` is the catalog entry name shown in menus; `model` is the service model ID. Press Enter to accept a displayed default. After capabilities, edit the complete `parameters` JSON object or accept medium reasoning effort. Enter `{}` for server defaults. Invalid parameter input retries before reading the hidden API key. `back` returns to protocol selection; Back there returns to services. Per-protocol drafts retain edits. The final review displays the exact parameters and transport defaults that will be saved. No connection test runs during setup.

An interactive first run without saved harness configuration or a workspace catalog starts a draft targeting the selected workspace's `.fruitfly/models.yaml`.

| Wizard behavior | Contract |
|---|---|
| Supported services | Four named services and the existing custom entry, declared in the [service table](fruitfly_agent/providers/services.yaml); the protocol page warns that some models may not support the selected protocol. |
| Limits | Enter model ID and documented limits explicitly. Positive integers; output smaller than context. No model-specific defaults or network discovery. |
| Capabilities | Checkbox page: only `tools` and `streaming` are required. Other flags default false and describe declared support; they do not generate or change API options. |
| Request defaults | Editable JSON object: Responses `reasoning.effort`, Messages `output_config.effort`, Chat `reasoning_effort`, all default `medium`. `{}` explicitly uses server defaults. Custom protocols default to `{}`. No vendor/model-specific policy. |
| Transport defaults | All choices display and save the same bounded waiting/retry defaults used by adapters; no manual input. |
| Credentials | Hidden input bypasses readline history. Blank input reuses the named environment variable. Blank variable name generates `FRUITFLY_MODEL_<LABEL>_API_KEY`, replacing label punctuation with underscores. |
| Existing key | The Model menu shows only set/missing status. **Set API key…** supplies a missing key; an already-set different value is rejected. |
| Saving | Append a unique model label to the selected workspace-local catalog, update only supplied credential entries, and save harness selection. `.fruitfly/secrets.env` writes use owner-only permissions. Existing comments/models and unrelated environment lines remain. |
| Field order | All model entries follow service, protocol, automatic SDK, model, base URL, context/output limits, credential variable, capabilities, parameters and transport. Saving reorders existing entries without changing their values or comments; transport is last. |
| Cancellation | `/cancel`, EOF, review cancellation, or configuration discard leaves the corresponding draft unsaved. Exiting startup discards pending changes. |
| Failures | Ordinary save failures attempt to restore model/credential files and retain the draft for retry; no cross-process or crash transaction. |
| Validation | Offline format/required-field checks only; no automatic network requests or connection tests. |

The wizard adds models with new labels; editing existing model specifications remains a YAML operation. It refuses additions to external or flow-style catalogs rather than rewriting them. Saving alone leaves the active runtime unchanged. Newly saved credentials are available when settings are applied or a session starts in the same process.

For manual setup, create `.fruitfly/`, then copy `examples/configuration/models.example.yaml` to `.fruitfly/models.yaml` and `examples/configuration/.env.example` to `.fruitfly/secrets.env` only if the local files do not already exist. The single catalog contains `deepseek-flash-openai` and `deepseek-flash-anthropic`, both using `deepseek-flash` and `DEEPSEEK_API_KEY` with DeepSeek endpoints. Configure your key and select one profile before making requests. See [example setup, budgets, and thinking limits](examples/configuration/README.md). Local `.fruitfly/models.yaml` is excluded from source distributions.

| Field | What to enter |
|---|---|
| Key under `models` | Your profile name, selected in the terminal or via `FRUITFLY_MODEL_PROFILE` |
| `sdk` | Required client library ID; automatically resolved for the chosen protocol in the wizard, still explicitly stored in YAML |
| `protocol` | Required API format: built-in pairs are `openai` + `responses`, `openai` + `chat-completions`, and `anthropic` + `messages` |
| `service` | Registered endpoint rules: `generic` (default), `openai`, `anthropic`, `deepseek`, or `qwen`; never inferred from the URL |
| `model` | Exact model ID accepted by the service |
| `base_url` | Service URL for that protocol; omission uses the registered service/protocol address, or the SDK default for generic services |
| `api_key_env` | Environment variable name; the template uses `DEEPSEEK_API_KEY`, whose value belongs in `.fruitfly/secrets.env` |
| `context_window`, `max_output_tokens` | Actual model limits; template numbers are examples |
| `capabilities` | Actual model and endpoint support, including tools and streaming |
| `parameters` | Protocol-native API options, including thinking and structured output; see the [Provider guide](fruitfly_agent/providers/PROVIDER_GUIDE.md#select-thinking-and-structured-output) |
| `transport` | Client waiting deadlines and retry settings; see [waiting policy](fruitfly_agent/providers/PROVIDER_GUIDE.md#bound-waiting-and-retries) |

Keep only usable profiles. For different credentials, assign distinct `api_key_env` names and add their values to `.fruitfly/secrets.env`. Offline parsing validates the catalog structure; it does not verify remote API compatibility, model access, or declared limits. Requests use the network and may incur charges.

| Reference | Details |
|---|---|
| [Providers](fruitfly_agent/providers/README.md) | Model specifications and request behavior |
| [Provider guide](fruitfly_agent/providers/PROVIDER_GUIDE.md) | Protocol-specific parameters and reasoning limitations |
| [Core runtime rules](fruitfly_agent/core/README.md#runtime-rules) | Tool/turn budget semantics and the fixed three-response truncation ceiling |
| [Harness schema](fruitfly_agent/run/configuration/README.md) | YAML example, validation, and persistence |
| [Run](fruitfly_agent/run/README.md) | CLI, assembly, artifacts, and recovery |

## Match menus to YAML

Mechanism and algorithm menus use readable registered names. Stable IDs remain in
YAML. Model forms retain their documented field names. The table below describes
the current authored component format. Effective runtime values are available
through offline inspection.

| Menu / form name | Stored location |
|---|---|
| `models.<name>` | Entry key under `models` in the model catalog |
| `sdk`, `protocol`, `service`, `model`, `base_url`, `context_window`, `max_output_tokens`, `api_key_env` | Existing catalog fields; the wizard selects protocol first and derives SDK from the registry |
| `capabilities` checkbox names | Boolean fields under the entry's `capabilities` mapping |
| Request and transport defaults in model review | Entry's `parameters` and `transport` mappings, generated by Providers and saved as shown |
| Executor model | Harness profile's `models.roles.executor` selection |
| Base prompt | Selected H `base_prompt` component's `parameters.instructions.system` |
| Context / Tools / Environment | Visual category of registered H components; categories are not extra YAML fields |
| Readable mechanism / algorithm name | Registered component ID under H/S/I; the component declares its implementation |

The capability page uses arrows and Space/Enter to toggle, then **Continue** to confirm. Numbered fallback toggles the selected row and offers a numbered Continue action. Checked means `true`; unchecked means `false`. Required rows remain checked. Esc, `back`, q, or EOF cancels without staging.

## Select a prompt or mechanism

| Selection | Default / behavior | Reference |
|---|---|---|
| Base prompt | `assistant-default`; choose another prompt in **/config → prompt** or `/config`. | [Base prompt](fruitfly_agent/lab/base_prompt/README.md) |
| Skill catalog | Packaged coding procedures plus `.skills/`; enable S `skill-library` and H catalog in **Context → Context augmentation → Skill catalog** (Space toggles; the phase is a section heading). | [Skills](fruitfly_agent/lab/context_manager/augmentation/skills/README.md) |
| Reduction | Layered compaction by default; optional working memory. Both read original history through `read`. Edit policy in H component files. | [Reduction](fruitfly_agent/lab/context_manager/reduction/README.md) |
| Context measurement | Automatically shared internal service; reports precision, input/output reserves and uncertainty. Exact counting requires a declared Provider capability. | [Measurement](fruitfly_agent/lab/context_manager/measurement/README.md) |
| Improvement | Edit I component files for editor/evaluator prompts; use experiment files and the independent experiment CLI for grants, conditions and execution. | [Improvement](fruitfly_agent/lab/improvement/README.md) |
| Reusable skill document | Disabled; Context augmentation. Set `settings.source_path` to one workspace-relative Skill or enter `content.body`; `settings.max_chars=16000`. | [Skill body](fruitfly_agent/lab/context_manager/augmentation/skills/README.md#improve-descriptions-and-bodies) |
| Web search / fetch | Disabled; enable **Search the web** and **Fetch web pages** under Tools. Search uses Brave, Tavily or DeepSeek. Fetch uses `direct` (no key) or `deepseek`. Expand either tool and choose **Set up…** to select the service and enter a hidden API key. Save writes the secret file. DeepSeek search/fetch use separate default variables; `api_key_env` can select a shared key. | [Web tools and YAML settings](fruitfly_agent/lab/tools/web/README.md) |
| Programmatic context | Explicitly enable `ipython-tool` or `rlm-ipython`. | [Programmatic context](fruitfly_agent/lab/context_manager/externalization/methods/programmatic_context/README.md) |
| Remote execution | Enable **Remote environment** under Environment to run file and Bash tools through SSH. Complete settings and credentials are reused; missing values open the six-step form. Expand **Set up…** to edit explicitly. Disabling retains saved settings across restarts in the same workspace/profile. Mutually exclusive with local execution and local IPython/RLM. Host memory and Skill resources remain readable. | [SSH setup and limits](fruitfly_agent/lab/environment/methods/remote/README.md) |
| RSI | Explicit independent CLI or injected host; generation scheduling and independent verification. | [RSI](fruitfly_agent/lab/rsi/README.md) |

Menus show mechanism switches and algorithm choices. Edit `.fruitfly/config.yaml` for detailed parameters. Summaries, improvement, and auxiliary model queries may incur model charges.

## Information sources

| Mechanism | Default | Parameters |
|---|---|---|
| `information-context` | Hidden dependency of knowledge/HTTP | `top_k=5`, `max_chars=4000` |
| `file-memory` | Enabled with automatic maintenance | Bounded directory and usage guidance; see the [memory owner](fruitfly_agent/lab/context_manager/augmentation/memory/methods/file_memory/README.md) |
| `knowledge-files` | Disabled | `root=.fruitfly/knowledge` |
| `live-http` | Disabled | HTTPS `endpoint`, `timeout_seconds=5` |

Source paths resolve within the workspace. Local knowledge and HTTP require `information-context`; File memory has its own directory loader. Live HTTP sends the current query to the configured service. See [Information spaces](fruitfly_agent/lab/context_manager/augmentation/information/README.md).

## Bound task tool calls

Execution count limits, overflow recovery and tool concurrency are fixed host
conditions. They have no component, menu setting or Improvement edit grant.
Daily Core defaults include 512 tool attempts per turn, 32 outer turns and six
context-recovery attempts. Improvement uses independent phase times and removes
count caps for task/editor execution. Actual effective values remain recorded in
the manifest and trial receipts. Embedding code can supply execution conditions
through typed Core/runtime interfaces; YAML selects registered H/S/I content.

## Configure the complete execution policy

[Runtime specification](fruitfly_agent/runtime_spec/README.md) validates host
execution values and recorded identities. Model token limits retain their model
catalog owner. Permissions remain an injected host strategy. Neither becomes an
editable algorithm because it appears in a runtime receipt.

Enabled owners determine available optimization components. Backend capabilities
and explicit grants further restrict them; unsupported targets fail before model
work. The experiment check reports this inventory offline.

## Text artifacts

Editable fields use `parameters.instructions.*`, `parameters.settings.*` and
`parameters.content.*`. Owner descriptions and experiment grants use those exact
paths. Omit experiment `edit` to discover all legal backend/material targets;
`list_targets` and `describe_target` load their metadata on demand.

| Field | Meaning |
|---|---|
| H `base_prompt.parameters.instructions.system` | Exact prompt text; omission of the component uses the registered default. |
| Component `artifacts` | Exported exact text in owner-declared slots, with content identities derived during assembly. |
| `RuntimeManifest` | Actual model, normalized mechanisms, implementation identities, prompt hash, and consumed artifacts. |

Authored text belongs in component parameters. Typed Python hosts can create immutable text with `DataArtifactStore.put_text`; see the [Run example](fruitfly_agent/run/README.md#text-artifacts). Runtime prompt/artifact bindings are internal projections of the same component configuration. Unknown or unused bindings are rejected; recovery verifies the original contents and manifest. Keep secrets out of artifacts, configuration, sessions, and reports.

Native tool owners expose H `instructions.description` and allowed settings.
The Provider receives complete descriptions and parameter schemas directly.
Names, schemas, implementations and permissions remain protected. Tool targets
require explicit selection and a capable isolated backend.

`memory-library` and `skill-library` are S content surfaces attached to their H
owners. They are not selectable mechanisms or independent menu entries. Memory
reading, extraction and consolidation instructions all belong to H `file-memory`.
Skill descriptions, bodies and text resources belong to S; loader guidance belongs
to H `skills`. I `improvement-editor` exposes system/propose/reflect instructions;
I `improvement-evaluator` exposes criteria/assess/compare. These strategies define
how granted H/S changes are proposed and evaluated. Persistent improvement
publication requires independent verification and explicit activation.

## Environment variables

| Variable | Purpose |
|---|---|
| `FRUITFLY_MODEL_PROFILE` | Initial model choice when no harness configuration has been saved; unset, empty, or whitespace-only means unselected |
| `FRUITFLY_EVENT_STREAM_PATH` | Optional JSONL event output in one-shot mode |
| `FRUITFLY_MODEL_USAGE_PATH` | Optional atomic request receipts with status and reported usage |
| `NO_COLOR` | Disable terminal colors |
| Model-specific `api_key_env` | Name of the variable containing that model's API key |
| `FRUITFLY_SSH_USERNAME` / `FRUITFLY_SSH_PASSWORD` | Secret SSH account/password; `remote-env.username_env` and `password_env` can select different variable names |
| `BRAVE_SEARCH_API_KEY` / `TAVILY_API_KEY` | Secret used by the selected web search backend; optional `web-search-tool.api_key_env` overrides the variable name |
| `DEEPSEEK_API_KEY` | Model credential used by the DeepSeek model examples |
| `DEEPSEEK_SEARCH_API_KEY` / `DEEPSEEK_FETCH_API_KEY` | Separate default secrets for DeepSeek search and fetch. Each tool's `api_key_env` can select another variable, including the model key when explicit reuse is wanted. |

[Secret template](examples/configuration/.env.example) contains public placeholders. Internal IPython subprocess variables are managed by the runtime and are not user settings.

With no initial choice, a sole catalog entry is selected automatically. With multiple entries, the startup panel directs interactive users to Configure; one-shot startup requires an explicit choice. Unknown nonblank names are rejected with available choices. Saved harness selections take precedence over this variable. Optional Eval installation material is configured separately in [Eval](fruitfly_eval/README.md).

## Results and state

| Data | Location / behavior |
|---|---|
| Sessions | `.fruitfly/sessions/`; canonical messages, context decisions, manifest, and concise run records |
| Experiment history | `.fruitfly/improvement/runs/`; scoped run summaries, including empty, failed and cancelled jobs |
| Candidates | `.fruitfly/improvement/candidates/`; latest complete result per configuration, profile, target, and task pack |
| Text contents | `.fruitfly/artifacts/`; immutable content-addressed artifacts |
| Workflow records | `.fruitfly/improvement/jobs/<job-id>/`; frozen plan, journal, immediate candidate snapshots, checkpoint and final result |
| Experience | `.fruitfly/improvement/experience.json`; explicitly committed library included in S identity |
| Pending lessons | `.fruitfly/improvement/experience-pending/`; review before commit/reject |
| Editor experiments | `.fruitfly/improvement/experiments/<id>/experiment.json`; references disjoint task packages |
| Private-suite claims | `.fruitfly/improvement/verification-uses.json`; completed or uncertain verification consumes a declared use |
| Explicit evolution jobs | `.fruitfly/evolution/`; host-owned phases, policy, and activation evidence |

Referenced results remain protected. Failed or cancelled searches do not replace a complete candidate. Editing a readable export does not change the runtime. See [Improvement](fruitfly_agent/lab/improvement/README.md#select-editable-surfaces) for retention and [Run](fruitfly_agent/run/README.md#recovery) for compatibility rules.

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

### Time registered improvement execution

Set `execution.organizer_seconds`, `execution.editor_seconds`, `execution.task_seconds` and `evaluation.evaluator_seconds` (defaults 1200, 1200, 3600, 1200). Each invocation starts a separate clock; nested calls within it share that clock. Composite studies time their leaf phases. Usage is recorded without admission quotas. User cancellation covers the job; unconfirmed cleanup stops further scheduling. External execution still requires a registered compatible runner.

### Assess completed executions

The shared model evaluator assesses completed runs and compares candidates through I evaluator prompts. It reports dimensions, process signals, candidate-hypothesis checks, uncertainty and exact supplied citations. Overview/event indexes navigate to immutable originals. Official scores remain observations; their presence, equality or magnitude never gates research stages. Configure shared read/catalog/search limits under `evidence`; the retained incumbent seeds the next round. See [Assessment](fruitfly_agent/lab/improvement/assessment/README.md) and [experiment configuration](fruitfly_agent/experiments/CONFIGURATION.md).

## Choose a candidate generator

The [experiment CLI](fruitfly_agent/experiments/README.md) composes a system config,
referenced tasks, optional narrowing grants and four condition modules. Experiment `execution` supplies the generator. The CLI currently composes
`agent-editor-v1`; other registered generators use the embedding composition API.
The [single-task](examples/experiments/benchmark.example.yaml) and
[joint task-set](examples/experiments/multi-task.example.yaml) examples share the
[experiment grammar](fruitfly_agent/experiments/CONFIGURATION.md).
It uses the built-in Agent editor; embeddings can replace generation through
`GeneratorRegistry`, which declares factories and capabilities;
`WorkflowRequest` freezes each job. Discovery and previews make no model requests.
Unknown generator IDs and unsupported component fields are rejected before execution.

## Configure the component editor

Select organizer/editor/assessor aliases in `models.roles`. I organizer, editor and evaluator components expose model-facing instructions. Fixed experiment configuration owns scheduling, independent phase times and evidence page size. See [component grammar](fruitfly_agent/runtime_spec/COMPONENTS.md). These roles compose the shared Lab Agent runner with separate tools and histories.

Python embeddings inject `StageBindings` into `RunApplicationFactory` to replace
stages. Task execution requires a compatible explicitly registered `TaskRunner`
or episode backend. Material declarations do not inherit the active environment
or provide a built-in local executor.
No dedicated search-tool API key is needed for component editing; web search/fetch
credentials remain independent tool settings.

## Configure independent research stages

Use one editable experiment document for historical inputs, role models,
configuration overrides and the explicitly selected next stage. See the
[Improvement developer guide](fruitfly_agent/lab/improvement/DEVELOPER_GUIDE.md).
Each invocation performs one stage; no automatic baseline/search runner is exposed.

## Follow component sources and activation

Use `{default: true}` to follow a registered component's owner YAML. H/S/I remain
explicit profile groups and every component document declares the same `role`.
Text, numbers, booleans and choices share typed parameter validation and grants.
An explicit file or inline document keeps its authored values; equality with a
default never changes its source intent. Default references may specify
`enabled: false` without copying their parameter values.

Ordinary saving retains default references. Export and candidate materialization
freeze complete effective parameters and exact retained bindings. Improvement
edits isolated `parameters.yaml` documents, then validates protected metadata,
field grants and owner constraints before execution. Verified adoption fixes the
changed component version; unrelated default references stay symbolic.

Use the existing configuration inspection command to see each component's role,
source kind, normalized values and content hash. Active manifests retain compact
configuration-source and tool-contract fingerprints. Python changes require a
new process; parameter and Skill resource changes require a fresh runtime.
Pending default-source changes block stale preparation/application until reload.
Frozen trials do not follow later working-copy defaults. See
[component syntax](fruitfly_agent/runtime_spec/COMPONENTS.md) and
[Run configuration](fruitfly_agent/run/configuration/README.md).

Eval file-capture policy belongs to the [Eval host configuration](fruitfly_eval/harbor/README.md#capture-task-evidence).
It is protected execution infrastructure, separate from selectable Agent H/S/I parameters.

## Maintain cross-session memory

[File memory](fruitfly_agent/lab/context_manager/augmentation/memory/methods/file_memory/README.md)
and automatic maintenance are enabled by default. Extraction uses 8000 new user
characters; consolidation uses 50 completed user turns. Counters accumulate across
sessions. `models.roles.memory_maintenance` inherits executor and constructs its
client only when generation starts. Advanced H instructions and bounds are in the
same File memory component. Retained note text is the attached S surface.

Review pending batches with `/memory`, then commit or reject explicitly. Normal
maintenance is H operating on S and needs no I editor/evaluator. The `memory-learning`
execution compares H candidates with trial-local learning and private downstream
evaluation. One-shot tasks disable workspace retained-state services and consume
only frozen initial content. Skills are also enabled by default; `/skills` lists
installed names and descriptions and `/skills read ID` displays the procedure.


### Continue research under changed configuration

Independent Improvement stages save their own effective configuration and report
differences from input producers. Historical evidence remains consumable after
model, instruction, source or grant changes; old outputs retain their original
production settings. Organization and proposal need no task execution document.
See [research configuration and development](fruitfly_agent/lab/improvement/DEVELOPER_GUIDE.md).

### Select default Improvement targets

Omitting experiment `edit` selects all enabled supported default optimization
components, including native tool targets. File memory and the three I instruction
roles are excluded by default; retained Memory/Skill libraries remain included.
An explicit `edit` map replaces this scope. Inspect the effective field-level table
with `improvement defaults --config EXPERIMENT` before model work. Generation
retains `configuration/optimization.json` and `optimization.md`. See
[experiment configuration](fruitfly_agent/experiments/CONFIGURATION.md#inspect-configuration-before-models).
