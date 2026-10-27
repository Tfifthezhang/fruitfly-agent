# Provider Guide

[Up: Providers](README.md)

Use one workspace `.fruitfly/models.yaml` for daily and experiment models. Each
system config selects its own `models.roles` aliases. Keep actual keys in
`.fruitfly/secrets.env` or the process environment.

## Choose the protocol and service

| `sdk` | `protocol` | API | Tool messages | Image tool results |
|---|---|---|---|---|
| `openai` | `responses` | Responses | `function_call` / `function_call_output` | Supported |
| `anthropic` | `messages` | Messages | `tool_use` / `tool_result` | Supported |
| `openai` | `chat-completions` | Chat Completions | assistant `tool_calls` / `tool` | Rejected explicitly |

`sdk` identifies the client library; `protocol` identifies the API format.
Both fields are required. The adapter registry selects a factory by the pair and
rejects unregistered combinations before constructing SDK clients. `service` selects registered endpoint
rules: `generic` (default), `openai`, `anthropic`, `deepseek`, `qwen`, or `bigmodel`. Neither is inferred
from the URL or model name. The `generic` rules validate protocol fields without
claiming vendor-specific support. An explicit custom base URL must be HTTP(S)
without embedded credentials, query or fragment. Omit it for the SDK default.

The model wizard offers official Responses/Messages, custom
Responses/Messages/Chat Completions, and explicit Qwen, BigModel and DeepSeek
presets. Official/preset choices set their service; custom choices use `generic`.
The first menu lists service groups. Named services open their preset directly;
custom services open a separate protocol menu. Back returns to service selection.
SDK and protocol fields are selections read from `ProviderRegistry.registered_pairs()`;
protocol choices are filtered by the selected SDK, service and named preset.
Named presets retain their declared endpoint/protocol pairing; custom services
expose all pairs registered for their selected SDK. Setup does not
construct clients to discover choices. Register a pair to expose it in the same
generic form, without adding a terminal branch.
The final review displays generated request parameters and all transport defaults;
confirmation saves exactly those values. Named presets follow the reasoning
checkbox; OpenAI/Anthropic/custom choices use empty request parameters (server
defaults), since thinking controls depend on the chosen model. Other parameters
remain editable in YAML. Adding a model never submits a request.

The package requires `openai>=3.26.0` and `anthropic>=1.12.0`, the SDK baselines
used for the request fields and response preservation checked here. Install the
project dependencies before using the templates; no older SDK fallback rewrites
request parameters.

## Write a model entry

```yaml
models:
  deepseek-high:
    sdk: openai
    protocol: responses
    service: deepseek
    model: deepseek-flash
    base_url: https://api.deepseek.com
    api_key_env: DEEPSEEK_API_KEY
    context_window: 1000000
    max_output_tokens: 32768
    capabilities:
      tools: true
      parallel_tool_calls: true
      vision: true
      reasoning: true
      streaming: true
    parameters:
      reasoning: {effort: high}
    transport:
      connect_timeout: 10.0
      timeout: 600.0
      first_progress_timeout: 180.0
      stall_timeout: 180.0
      total_timeout: 900.0
      cleanup_timeout: 5.0
      retry_jitter: 0.2
      retry_max: 3
      retry_base_delay: 1.0
```

The alias is a local name; `model` is the API model ID. The token numbers are
working budgets, not automatically discovered service limits. Reasoning tokens
share the output allowance with answer tokens. `capabilities` contains strict
booleans describing declared support; it does not enable a request feature.
Run requires tools/streaming where used. Remote support remains unverified offline.

The catalog accepts `models` and optional JSON-mapping `metadata` for local notes.
Model fields are the ones shown above. Unknown fields, duplicate YAML keys,
non-string keys, nonfinite numbers and configuration version markers fail.
`parameters` contains only API request options; `transport` contains only client
waiting/retry options. There is one format and no fallback parser.

## Select thinking and structured output

| Protocol/service | `parameters` excerpt |
|---|---|
| DeepSeek Responses | `reasoning: {effort: high}`; use `none`, `low`, `high`, or `max` |
| DeepSeek Messages | `thinking: {type: enabled}`, `output_config: {effort: high}`; `disabled` turns thinking off |
| DeepSeek Chat Completions | `reasoning_effort: high`, `extra_body: {thinking: {type: enabled}}` |
| Qwen Chat Completions | `extra_body: {enable_thinking: true, preserve_thinking: true, reasoning_effort: medium}` |
| BigModel GLM-4.5-Air Chat Completions | `extra_body: {thinking: {type: enabled}}`; use `disabled` to turn it off |
| Anthropic Messages manual thinking | `thinking: {type: enabled, budget_tokens: 2048}`; budget must be at least 1024 |
| Anthropic Messages adaptive thinking | `thinking: {type: adaptive}`; select supported model-specific `output_config` values |
| Responses structured output | `text: {format: {type: json_object}}` or a `json_schema` format |
| Chat Completions structured output | `response_format: {type: json_object}` or a `json_schema` format |

Choose fields supported by the actual model. Service validation covers known
endpoint constraints; it does not enumerate every remote model's capabilities.
DeepSeek rules reject known ignored options, such as temperature while thinking,
Responses reasoning summaries/verbosity, Messages thinking budgets and top_k.
Flash top_p must be 0.95–1 while thinking and 1 otherwise. Pro ignores top_p while
thinking. DeepSeek parallel-call controls are omitted because the endpoint ignores
them; H tool scheduling still governs actual local execution.

Qwen3.8 Chat accepts `low`, `medium`, or `xhigh` effort under `extra_body`,
or a positive `thinking_budget`, but not both. The preset uses `medium` for a
balanced daily workload; the remote default is `xhigh`. It explicitly preserves
historical reasoning; replay sends it as `reasoning_content`, never visible answer
text. Thinking cannot force a particular tool. The Qwen preset uses the Chat API
shown on its official model page; image user inputs work, while image tool results
retain this adapter's explicit rejection above. Video/audio have no runtime adapter.

BigModel GLM-4.5-Air uses dynamic thinking and text input. It does not accept the
newer GLM `reasoning_effort` or `tool_stream` options. BigModel requests omit
undocumented `parallel_tool_calls` and `stream_options` controls. Available usage
chunks are still recorded; missing receipts remain unknown. Service validation
also rejects forced tool selection and JSON Schema output unsupported by this API.
These rules belong to Providers, not Run or the frontend.

The [additional model catalog](../../examples/configuration/additional-models.example.yaml)
contains Qwen3.8-Flash and GLM-4.5-Air entries with empty-key references and
working budgets. See [setup and official sources](../../examples/configuration/README.md#add-qwen-or-glm).

Unknown protocol request options fail. `extra_body` provides an explicit finite
JSON extension for compatible endpoints; its remote semantics are unverified by
`generic`. It cannot overwrite runtime-owned model, messages, tools, streaming,
output allowances, transport settings or duplicate parameters. DeepSeek only
permits its documented Chat `thinking` extension. `extra_headers` accepts
non-secret feature headers; authentication and cookie headers are rejected.

Sources: [DeepSeek thinking](https://api-docs.deepseek.com/zh-cn/guides/thinking_mode/),
[Responses compatibility](https://api-docs.deepseek.com/zh-cn/guides/responses_api/),
[Messages compatibility](https://api-docs.deepseek.com/zh-cn/guides/anthropic_api/),
[Claude thinking](https://platform.claude.com/docs/en/build-with-claude/thinking).

## Preserve a tool conversation

Providers keep exact ordered output items in `AssistantMessage.provider_state`,
in addition to the portable text/thinking/tool projection. Responses preserves
reasoning items, encrypted content and message phase. Messages preserves complete
thinking, signature and redacted blocks. Chat preserves reasoning_content and
ordered function calls. Empty visible thinking never removes its opaque state.

Session round-trips this JSON data. Replay checks an internal record version,
content/payload digests, model and a nonreversible credential/endpoint identity.
Keys, HTTP headers and complete request bodies are never stored in continuation
data. Signed Messages also binds the preceding wire messages, system and tools.

Changed response content, credentials, model or a signed prefix prevents reuse
inside an active tool turn. The request fails before the SDK call with a reason.
A new user turn can rebuild a portable history without incompatible state.
Missing historical state cannot recreate signatures. Editing or compacting a
signed prefix during an active tool turn requires restarting that turn. Canonical
history remains intact; summaries omit thinking and opaque protocol data.

Only valid replay uses original output items, avoiding duplicate portable text.
Final response items take precedence over deltas. Responses `commentary` and
Messages `pause_turn` continue the model exchange; consecutive non-final replies
are independently bounded by the existing `max_turns` value. Truncation takes
precedence over emitted tools, so Core never executes a truncated tool batch.
Missing terminal responses fail explicitly.

Known server-tool activity is reported and persisted separately from local tool
calls. It never dispatches a host tool or increments the host tool counter. Server
activity prevents automatic request retries after a possible server-side effect.
This does not enable server tools: configured tools remain owned by H/Catalog.
Unknown output item/block types fail rather than becoming a successful empty reply.

[OpenAI conversation state](https://developers.openai.com/api/docs/guides/conversation-state)
and [Claude preserved thinking](https://platform.claude.com/docs/en/build-with-claude/preserved-thinking)
describe why exact protocol state and context boundaries matter.

## Bound waiting and retries

Set these values under `transport`. Time values are seconds and must be finite
and positive, except `retry_base_delay`, which may be zero.

| Parameter | Default | Meaning |
|---|---:|---|
| `connect_timeout` | 10 | SDK connection timeout |
| `timeout` | 600 | SDK read/write/pool timeout |
| `first_progress_timeout` | 180 | Request start until meaningful output |
| `stall_timeout` | 180 | Maximum gap between meaningful output events |
| `total_timeout` | 900 | One invocation, including attempts and backoff |
| `cleanup_timeout` | 5 | Separate allowance for closing each owned resource |
| `retry_max` | 3 | Nonnegative retry count; SDK retries are disabled |
| `retry_base_delay` | 1 | Exponential backoff base |
| `retry_jitter` | 0.2 | Fraction from 0 to 1 |

Keepalive does not reset progress. Text, thinking, signatures and tool activity
can reset it. Silent reasoning can still exceed the first-progress deadline.
Before delivered output/effects, transient failures may retry within both limits
and honor Retry-After. After partial delivery or server-tool activity they fail
without replay. No output proves neither non-execution nor zero cost. Cleanup
may extend the total elapsed time. Run records effective transport values.

Usage records available input/output/cache receipts and optional reasoning-token
counts. Reasoning is a subset of output, not an additional charge in total_tokens;
missing breakdowns remain unknown. Billing conventions remain service-specific.

## Register another service or protocol

For an existing supported service, add another catalog alias. To implement an
endpoint difference, register a distinct `ServiceDefinition` through
`providers.services.register_service` before loading the catalog. Declare supported
protocols, pure parameter validation, prefix-binding requirements and request-control
support. Keep vendor logic inside Providers. Definitions must be installed code;
YAML does not import Python classes.

A new client/protocol pair supplies a Provider factory through
`ProviderRegistry.register(sdk, protocol, factory)`, its own codec, request
validation and offline fixtures. `registered_pairs()` exposes those registrations
to setup without invoking factories. Inject an extended registry into
`RunApplicationFactory` to use its runtime factories and menu choices.
Custom protocol factories
own additional parameter validation. Reuse bounded transport and the Core stream;
Core, terminal and Eval do not dispatch on vendors. Gemini native Interactions,
audio/video/Realtime and background/server-session recovery have no adapter here.
The generic continuation envelope can retain protocol state when such adapters are
implemented; its presence does not establish support.

Use the [public templates](../../examples/configuration/README.md) and
[offline tests](../../tests/providers/README.md). Real integration is explicit,
uses the network and may incur charges; see [Integration](../../tests/integration/README.md).
