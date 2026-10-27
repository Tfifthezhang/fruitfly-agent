# Configuration Templates

[Up: Examples](../README.md)

Use the interactive model wizard for first setup, or copy the single model catalog below for DeepSeek Flash examples using two API protocols.

For H/S/I authoring, follow [Component documents](../../fruitfly_agent/runtime_spec/COMPONENTS.md).
For your own implementation, follow [Catalog registration](../../fruitfly_agent/lab/catalog/CONFIGURATION.md).
The [configuration overview](../../CONFIGURATION.md#navigate-the-configuration-tree)
is the navigation root; this page owns template setup rather than another schema table.

For independent experiments, `fruitfly-agent-lab init` creates the default
Agent/component files and a minimal experiment from installed templates. It creates
the shared `models.yaml` only when absent, preserves daily files and existing
regular model catalogs/secrets, and rejects other conflicting configuration files.
Use `--source task-set --benchmark terminal-bench-4` for benchmark request/host
templates as well. See [native setup](../experiments/README.md#start-a-native-experiment)
or the [remote Linux walkthrough](../experiments/TB4_SERVER.md). No model or
container starts during initialization.

| Template | Workspace destination | Contents |
|---|---|---|
| [models.example.yaml](models.example.yaml) | `.fruitfly/models.yaml` | Both DeepSeek Flash protocol profiles in one file |
| [additional-models.example.yaml](additional-models.example.yaml) | Merge into `.fruitfly/models.yaml` | Qwen3.8-Flash and GLM-4.5-Air; keep existing aliases and model roles |
| [.env.example](.env.example) | `.fruitfly/secrets.env` | Empty model/search keys and optional SSH account/password variables |
| [ssh.example.yaml](ssh.example.yaml) | `.fruitfly/config.yaml` | Minimal remote profile; addresses are placeholders, credentials stay in the secret file |
| [mcp.example.yaml](mcp.example.yaml) | `.fruitfly/mcp.yaml` | Optional local stdio servers, explicit selected tools and limits; edit placeholders before enabling `mcp-tools` |
| [default-config.example.yaml](default-config.example.yaml) | `.fruitfly/default-config.yaml` | Baseline selecting model roles and referenced H/S/I component files |
| [eval-host.example.yaml](eval-host.example.yaml) | `.fruitfly/eval-host.yaml` | Machine-local Linux runtime mounts and dependency/cache settings; configure path variables before use |

Copy the default configuration and referenced `components/` tree only when their
destinations are absent. Reuse `.fruitfly/models.yaml`, or create it from the model
template if missing. Select aliases separately in daily and baseline
`models.roles`. **Configure → Restore default configuration** stages the
default harness settings while retaining the daily model and credentials. Save
for a new session or discard the draft. Eval uses the complete default profile
unless explicitly overridden, using its aliases from the shared model catalog.
It passes `--unrestricted` inside task containers; no permission configuration
belongs in either Agent file.

The generated tree includes H prompt/execution/environment/context/tool files and
I editor/feedback/search files. S is optional; examples include
[memory](components/S/learned-memory.yaml) and [Skill content](components/S/skill-document.yaml).
Select those files under the profile's S mapping before use. Initialization does
not create placeholder S state. Candidate editing additionally needs an explicit
[experiment grant](../../fruitfly_agent/experiments/CONFIGURATION.md#grant-component-changes).

The Eval host template is independent of daily/default Agent configuration and
contains no model/key preferences. See [Harbor preparation](../../eval/harbor/README.md)
for preparation, path/link changes and verifier cache declarations.
The [server guide](../../eval/SERVER_GUIDE.md) walks through private-file
transfer, Linux runtime installation and machine/request file generation in order.

| Profile | `sdk` | `protocol` | `model` | `base_url` |
|---|---|---|---|---|
| `deepseek-flash-openai` | `openai` | `responses` | `deepseek-flash` | `https://api.deepseek.com` |
| `deepseek-flash-anthropic` | `anthropic` | `messages` | `deepseek-flash` | `https://api.deepseek.com/anthropic` |

Both profiles access DeepSeek, with a DeepSeek key. `sdk` selects the client library and `protocol` selects the API format; neither selects OpenAI or Anthropic's own models. The wizard's **DeepSeek** preset generates Responses with explicit thinking parameters. Author the Messages entry using the template. DeepSeek documents these endpoints in [model details](https://api-docs.deepseek.com/quick_start/pricing/), [Responses](https://api-docs.deepseek.com/api/create-response/), and [Messages compatibility](https://api-docs.deepseek.com/guides/anthropic_api/).

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
under `parameters`; the loader rejects mixed placement and ignored DeepSeek options.

Copying, parsing, and offline construction do not make requests. Live tasks contact DeepSeek and may incur charges. The examples have not been validated with live requests. Keep keys out of the catalog and repository.

## Add Qwen or GLM

Use the named wizard preset, or merge the entries in
[additional-models.example.yaml](additional-models.example.yaml) under your existing
`models` mapping. Do not replace an existing catalog. Add the matching empty
variable from [.env.example](.env.example) to `.fruitfly/secrets.env` and fill its
value locally. Restart after editing that secret file. Adding aliases does not
change the daily executor or any experiment's roles; select the desired alias in
the daily model menu or the relevant config's `models.roles`.

| Alias / API model ID | API / service | Key variable | Working context / output |
|---|---|---|---|
| `Qwen3.8-Flash` / `qwen3.8-flash` | Chat Completions / `qwen` | `DASHSCOPE_API_KEY` | 1,000,000 / 32,768 |
| `GLM-4.5-Air` / `glm-4.5-air` | Chat Completions / `bigmodel` | `ZAI_API_KEY` | 131,072 / 32,768 |

Qwen uses the Beijing address published on the
[official model page](https://www.qianwenai.com/models/qwen3.8-flash).
The key must match that account and region; edit the endpoint for a different
region. It supports text/image input, tools, streaming and thinking. The preset
enables thinking with `medium` effort, a balanced working choice rather than the
service's `xhigh` default, and preserves reasoning across tool conversations.
Its published maximum output is 131,072; the preset uses a smaller shared
thinking/answer allowance. See the [model guide](https://platform.qianwenai.com/docs/developer-guides/getting-started/latest-model)
and [Chat API reference](https://platform.qianwenai.com/docs/api-reference/chat/openai-chat).

GLM uses the China BigModel endpoint, not a Coding Plan or international endpoint.
It supports text input, tools, streaming and dynamic thinking; vision is false.
The published context/output limits are 128K/96K. The preset enables thinking
without the `reasoning_effort` parameter restricted to newer GLM models. See
[GLM-4.5 models](https://docs.bigmodel.cn/cn/guide/models/text/glm-4.5)
and [OpenAI-compatible setup](https://docs.bigmodel.cn/cn/guide/develop/openai/introduction).
All entries remain offline declarations until an explicitly requested live task.

## Configure other services

For an external execution server, follow [SSH environment setup](../../fruitfly_agent/lab/environment/ssh/README.md).
Startup of an SSH profile opens a verified SSH connection; file and Bash tools
operate on the server. Copy the SSH template only when the destination is absent,
or merge its mechanism settings into your existing profile. Keep account and
password values alongside API keys in the ignored local secret file.

See [Configuration](../../CONFIGURATION.md) for precedence and saving, and [Providers](../../fruitfly_agent/providers/README.md) for adapter behavior.

Optional [web tools](../../fruitfly_agent/lab/tools/web/README.md) are disabled by default. Enable search/fetch under Tools and set the selected service's key in the secret environment. Search requests may incur service charges; public page fetching requires no search credential. Model catalog fields are unchanged.

```bash
.venv/bin/python -m unittest tests.providers.test_providers
```
