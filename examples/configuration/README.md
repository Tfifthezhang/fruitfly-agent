# Configuration Templates

[Up: Examples](../README.md)

Use the interactive model wizard for first setup, or copy the single model catalog below for DeepSeek Flash examples using two API protocols.

For H/S/I authoring, follow [Component documents](../../fruitfly_agent/runtime_spec/COMPONENTS.md).
For your own implementation, follow [Catalog registration](../../fruitfly_agent/lab/catalog/CONFIGURATION.md).
The [configuration overview](../../CONFIGURATION.md#navigate-the-configuration-tree)
is the navigation root; this page owns template setup rather than another schema table.

For independent experiments, `fruitfly-agent-lab init` creates the default
system/model files from installed templates, without an experiment executor. It creates
the shared `models.yaml` only when absent, preserves daily files and existing
regular model catalogs/secrets, and rejects other conflicting configuration files.
Use `--source task-set --benchmark terminal-bench-4` for benchmark request/host
and experiment templates. See [system setup](../experiments/README.md#initialize-system-configuration)
or the [remote Linux walkthrough](../experiments/TB4_SERVER.md). No model or
container starts during initialization.

| Template | Workspace destination | Contents |
|---|---|---|
| [models.example.yaml](models.example.yaml) | `.fruitfly/models.yaml` | Both DeepSeek Flash protocol profiles in one file |
| [additional-models.example.yaml](additional-models.example.yaml) | Merge into `.fruitfly/models.yaml` | Explicit Qwen3.8-Flash examples in three protocols; keep existing aliases and roles |
| [.env.example](.env.example) | `.fruitfly/secrets.env` | Empty model/search keys and optional SSH account/password variables |
| [ssh.example.yaml](ssh.example.yaml) | `.fruitfly/config.yaml` | Minimal remote profile; addresses are placeholders, credentials stay in the secret file |
| [mcp.example.yaml](mcp.example.yaml) | `.fruitfly/mcp.yaml` | Optional local stdio servers, explicit selected tools and limits; edit placeholders before enabling `mcp-tools` |
| [default-config.example.yaml](default-config.example.yaml) | `.fruitfly/default-config.yaml` | Single baseline file selecting model roles and registered H/S/I defaults |
| [eval-host.example.yaml](eval-host.example.yaml) | `.fruitfly/eval-host.yaml` | Machine-local Linux runtime mounts and dependency/cache settings; configure path variables before use |

Copy the single default configuration only when its destination is absent.
Registered defaults resolve through installed owner resources. Reuse `.fruitfly/models.yaml`, or create it from the model
template if missing. Select aliases separately in daily and baseline
`models.roles`. **/config → Restore default configuration** stages the
default harness settings while retaining the daily model and credentials. Save
for a new session or discard the draft. Eval uses the complete default profile
unless explicitly overridden, using its aliases from the shared model catalog.
It passes `--unrestricted` inside task containers; no permission configuration
belongs in either Agent file.

The default system selects H context directories, S `memory-library` and
`skill-library`, and I editor/evaluator instructions through registered defaults.
Four packaged coding Skills are available on demand; memory starts empty.
Initialization does not write learned state or make model calls. Enable H
H `file-memory` automatic maintenance for
threshold-based cross-session updates, then review pending batches with `/memory`.
The lazy `models.roles.memory_maintenance` reference inherits executor by default.
See [memory behavior](../../fruitfly_agent/lab/context_manager/augmentation/memory/methods/file_memory/README.md)
and [Skill optimization](../../fruitfly_agent/lab/context_manager/augmentation/skills/README.md#improve-descriptions-and-bodies).
Candidate editing additionally needs an explicit
[experiment grant](../../fruitfly_agent/experiments/CONFIGURATION.md#grant-component-changes).

The Eval host template is independent of daily/default Agent configuration and
contains no model/key preferences. See [Harbor preparation](../../fruitfly_eval/harbor/README.md)
for preparation, path/link changes and verifier cache declarations.
The [server guide](../../fruitfly_eval/SERVER_GUIDE.md) walks through private-file
transfer, Linux runtime installation and machine/request file generation in order.

| Profile | `sdk` | `protocol` | `model` | `base_url` |
|---|---|---|---|---|
| `deepseek-flash-openai` | `openai` | `responses` | `deepseek-flash` | `https://api.deepseek.com` |
| `deepseek-flash-anthropic` | `anthropic` | `messages` | `deepseek-flash` | `https://api.deepseek.com/anthropic` |

Both profiles access DeepSeek, with a DeepSeek key. `sdk` selects the client library and `protocol` selects the API format; neither selects OpenAI or Anthropic's own models. In the wizard choose **DeepSeek**, then Responses, Messages or Chat Completions; SDK follows automatically. The parameters editor defaults effort to `medium`; these authored templates explicitly select `high`. DeepSeek documents these endpoints in [model details](https://api-docs.deepseek.com/quick_start/pricing/), [Responses](https://api-docs.deepseek.com/api/create-response/), and [Messages compatibility](https://api-docs.deepseek.com/guides/anthropic_api/).

Create `.fruitfly/` and copy templates only if the destinations are absent. Set `DEEPSEEK_API_KEY` in the secret file or process environment. Select one profile in the terminal, or set `FRUITFLY_MODEL_PROFILE` before first one-shot startup. Keep both profiles in the same catalog or remove the one you do not need.

The example uses a 1,000,000-token working window within the documented 1M context,
with output capped at 32768 tokens, including thinking. These are working budgets,
not the service maximum. Both entries select `service: deepseek` and explicitly
enable thinking at `high` effort using their protocol-native `parameters`.
Capabilities describe support; they do not switch server features. See
[protocol rules and continuation limits](../../fruitfly_agent/providers/PROVIDER_GUIDE.md#preserve-a-tool-conversation).

Both examples bound first progress, later stalls and total time under `transport`,
and allow at most three retries before partial output or server-tool activity.
All nine transport fields are written explicitly, including default values, in
both the public example and the installed initialization template.
See [transport settings](../../fruitfly_agent/providers/PROVIDER_GUIDE.md#bound-waiting-and-retries).
Silent reasoning may need a larger first-progress limit. Protocol/API options stay
under `parameters`; the loader checks protocol shapes and rejects mixed placement. Model-specific or ignored options are left to the endpoint.

Copying, parsing, and offline construction do not make requests. Live tasks contact DeepSeek and may incur charges. The examples have not been validated with live requests. Keep keys out of the catalog and repository.

## Add Qwen

Choose Qwen, then the protocol before entering model fields. SDK is automatic;
model ID, limits and optional capabilities are explicit user declarations. The
protocol page warns that some models may not support the selected protocol. New
wizard entries offer medium reasoning effort in an editable parameters JSON field.
Blank accepts the displayed mapping; `{}` selects server defaults explicitly.

For explicit authored examples, merge selected entries from
[additional-models.example.yaml](additional-models.example.yaml) into the existing
`models` mapping. Keep existing aliases and roles. Set `DASHSCOPE_API_KEY` in
`.fruitfly/secrets.env` or the process environment. The key and endpoint must match
your account and region. Select the new alias in the daily model menu or relevant
config's `models.roles`.

| Alias | Protocol | API model ID | Working context / output |
|---|---|---|---|
| `Qwen3.8-Flash` | Chat Completions | `qwen3.8-flash` | 1,000,000 / 32,768 |
| `Qwen3.8-Flash-Responses` | Responses | `qwen3.8-flash` | 1,000,000 / 32,768 |
| `Qwen3.8-Flash-Messages` | Messages | `qwen3.8-flash` | 1,000,000 / 32,768 |

These examples include explicit model-specific API options and conservative
working budgets. They are not wizard defaults or local compatibility rules.
Review them against the [model reference](https://www.qianwenai.com/models/qwen3.8-flash)
and the [Chat](https://platform.qianwenai.com/docs/api-reference/chat/openai-chat),
[Responses](https://platform.qianwenai.com/docs/api-reference/chat/openai-responses)
or [Messages](https://platform.qianwenai.com/docs/api-reference/chat/anthropic)
reference before live use. All examples remain offline declarations; live tasks
use the network and may incur charges.

For another service, use the existing custom entry, supply its supported protocol
and API base URL, and author its model options explicitly. The packaged
[service table](../../fruitfly_agent/providers/services.yaml) owns the four built-in
service definitions; it contains no model-specific policies. See the
[Provider guide](../../fruitfly_agent/providers/PROVIDER_GUIDE.md#choose-the-protocol-and-service).

## Configure other services

For an external execution server, follow [SSH environment setup](../../fruitfly_agent/lab/environment/methods/remote/README.md).
Startup of an SSH profile opens a verified SSH connection; file and Bash tools
operate on the server. Copy the SSH template only when the destination is absent,
or merge its mechanism settings into your existing profile. Keep account and
password values alongside API keys in the ignored local secret file.

See [Configuration](../../CONFIGURATION.md) for precedence and saving, and [Providers](../../fruitfly_agent/providers/README.md) for adapter behavior.

Optional [web tools](../../fruitfly_agent/lab/tools/web/README.md) are disabled by default. Enable search/fetch under Tools and set the selected service's key in the secret environment. Search requests may incur service charges; public page fetching requires no search credential. Model catalog fields are unchanged.

```bash
.venv/bin/python -m unittest tests.providers.test_providers
```

## Select reduction and measurement

The default selects [layered compaction](../../fruitfly_agent/lab/context_manager/reduction/methods/layered_compaction/README.md)
in deterministic mode. It abbreviates old tool results and archives earlier
complete groups with original-message references through `read`.
[Working memory](../../fruitfly_agent/lab/context_manager/reduction/methods/working_memory/README.md) remains optional in
the same Reduction slot. Shared request measurement is automatic and has no
component selection or optimization grant.

To enable hybrid summaries, set `parameters.settings.mode: hybrid` in the selected
layered-compaction component. `profiles.<profile>.models.roles.context_summary`
defaults to `{inherit: executor}`; replace it with a catalog alias for an independent
summary model. Hybrid calls use the network and may incur charges.

A materializing experiment can grant, for example:

```yaml
edit:
  layered-compaction:
    fields: [parameters.instructions.readback, parameters.settings.preview_chars]
    bounds:
      parameters.settings.preview_chars: {minimum: 256, maximum: 2048}
```

Hybrid mode additionally admits `parameters.instructions.summary` and the
`summary_*` size/timeout settings. Deterministic mode rejects those inactive
grants. Mode and model bindings are protected. The baseline must already enable
the method and satisfy grant bounds. Candidate trials require a registered
backend declaring configuration materialization, and receive isolated history.
See [method behavior](../../fruitfly_agent/lab/context_manager/reduction/README.md)
for recovery, cancellation and information-retention limits. Parsing and
configuration inspection are offline; live validation requires explicit invocation.

Default measurement is heuristic with explicit uncertainty and reported-usage
calibration. Embeddings can inject a configured `MeasurementService`; precision
controls are outside model edit grants. See [measurement](../../fruitfly_agent/lab/context_manager/measurement/README.md).

To select working memory, replace the Reduction selection with
`working-memory-reduction: {default: true}` under H, removing or disabling layered compaction. Retain `{inherit: executor}` at
`profiles.<profile>.models.roles.working_memory`, or set an independent catalog alias.
Maintenance starts at 50% of the
available input budget, then normally waits 32 new messages; each update has a
20-second total auxiliary budget and two-page limit. It remains optional.
IPython uses `models.roles.context_query`, which also defaults to
`{inherit: executor}`. All six auxiliary role positions are present in the default
configuration. Replace a reference with a catalog alias only when an independent
model is needed. Auxiliary calls may use the network and incur model charges. See
[role admission](../../fruitfly_agent/lab/catalog/README.md#declare-auxiliary-model-dependencies).

The Eval host example includes bounded [file-capture settings](../../fruitfly_eval/harbor/README.md#capture-task-evidence).
They apply during benchmark execution and do not run when loading this example.
