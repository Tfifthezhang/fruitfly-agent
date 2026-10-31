# Provider Guide

[Up: Providers](README.md)

Use one workspace `.fruitfly/models.yaml` for daily and experiment models. Each
system config selects its own `models.roles` aliases. Keep actual keys in
`.fruitfly/secrets.env` or the process environment.

## Choose the protocol and service

| `sdk` | `protocol` | Tool messages | Image tool results |
|---|---|---|---|
| `openai` | `responses` | `function_call` / `function_call_output` | Native image content |
| `anthropic` | `messages` | `tool_use` / `tool_result` | Native image content |
| `openai` | `chat-completions` | assistant `tool_calls` / `tool` | Attributed image observation after the complete tool-result batch |

`sdk` identifies the client library; `protocol` identifies the wire format. Both
remain required catalog fields. The registry dispatches on this pair and rejects
unregistered pairs before constructing a client. The wizard derives SDK from the
selected protocol; multiple adapters require an explicit default registration.

[services.yaml](services.yaml) is the single built-in service/protocol table used
by both setup and runtime endpoint resolution. It contains four named services
and the existing custom entry:

| Service | Responses | Messages | Chat Completions |
|---|---|---|---|
| OpenAI | Supported | Not offered | Supported |
| Anthropic | Not offered | Supported | Supported |
| DeepSeek | Supported | Supported | Supported |
| Qwen | Supported | Supported | Supported |
| Custom (`generic`) | Registered adapters | Registered adapters | Registered adapters |

The table declares each service's label, default protocol, credential variable
name and protocol mappings. Each protocol mapping supplies an API base URL and
optional client controls: `prefix_bound`, `responses_store`, `parallel_control`,
`chat_token_field`, `chat_stream_usage` and `input_count`. Optional `description` is display text.
The loader rejects unknown fields and invalid values. Restart after changing the
packaged table; it is not a second model-catalog format or a live configuration API.

The table contains no model IDs, model allowlists, account restrictions, thinking
rules or parameter policies. Some models may not support the selected protocol;
the protocol page displays this notice above the choices. Check model, region,
account and parameter support with the service. Offline validation does not prove
remote compatibility. Remote errors retain the normal Provider error mapping.

The wizard selects service, then protocol, then model fields. Enter model ID and
token limits explicitly; it does not infer model capabilities or force thinking.
Capabilities are support declarations and do not change parameter choices.
After capabilities, the parameters editor offers a complete editable JSON object
with medium reasoning effort: Responses uses `reasoning.effort`, Messages uses
`output_config.effort`, and Chat uses `reasoning_effort`. These are protocol defaults,
not model policies. Unsupported custom protocols default to `{}`. Enter `{}` to use
server defaults explicitly; blank accepts the displayed mapping. Invalid JSON or
protocol options retry before credential input. Model/service compatibility remains
the caller's responsibility. Existing explicitly authored options are preserved.

Back from text fields returns to protocols; Back there returns to services.
Switching protocols refreshes addresses and keeps separate drafts. SDK appears
read-only in final review along with parameters and transport defaults. Discovery,
review and saving make no model requests.

Model fields serialize in the same order as setup: `service`, `protocol`, `sdk`,
`model`, `base_url`, `context_window`, `max_output_tokens`, `api_key_env`,
`capabilities`, `parameters`, `transport`. The alias is the mapping key; secret key
input is never stored there. Saving an addition also normalizes existing entries'
field order while preserving their values and comments.

`service` is explicit and is never inferred from model name or URL. Omitted
`base_url` uses the table address for that service/protocol; `generic` retains the
SDK default. Explicit URLs take precedence and must be HTTP(S) without embedded
credentials, query or fragment. Messages SDKs append `/v1/messages`, so configure
an API base URL rather than a complete request path.

The package requires `openai>=3.26.0` and `anthropic>=1.12.0`. SDK and protocol
compatibility do not imply identical model behavior or support for every feature.

## Write a model entry

```yaml
models:
  deepseek-high:
    service: deepseek
    protocol: responses
    sdk: openai
    model: deepseek-flash
    base_url: https://api.deepseek.com
    context_window: 1000000
    max_output_tokens: 32768
    api_key_env: DEEPSEEK_API_KEY
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

Write API options explicitly under `parameters`. The following are examples to
check against the selected model's current documentation, not built-in policies:

| Protocol | Example options |
|---|---|
| Responses | `reasoning: {effort: high}` |
| Messages | `thinking: {type: enabled, budget_tokens: 2048}` |
| Chat Completions | `reasoning_effort: high` or an explicit `extra_body` extension |
| Responses structured output | `text: {format: {type: json_object}}` |
| Chat structured output | `response_format: {type: json_object}` |

Built-in services share protocol-level shape validation. They do not reject,
strip or translate parameters because a model may ignore them. For example,
DeepSeek temperature, penalty and effort options remain as authored even when the
remote service ignores them. Changing `capabilities.reasoning` does not change
`parameters`. Model-specific validity is decided by the remote endpoint.

Unknown top-level protocol options fail; use `extra_body` for explicit finite JSON
extensions. It cannot overwrite runtime-owned model, messages, tools, streaming,
output limits, transport controls or duplicate parameters. `extra_headers` accepts
non-secret feature headers; authentication/cookie headers are rejected. Common
numeric/JSON shapes, structured-output shapes and thinking budgets fitting the
output allowance remain validated independently of vendor or model name.

The [additional model examples](../../examples/configuration/additional-models.example.yaml)
show explicit Qwen configurations in three protocols. They are authored examples,
not wizard presets or local capability rules. See [setup instructions](../../examples/configuration/README.md#add-qwen).

Protocol references: [OpenAI Responses](https://developers.openai.com/api/docs/guides/migrate-to-responses),
[Messages thinking](https://platform.claude.com/docs/en/build-with-claude/thinking),
[DeepSeek thinking](https://api-docs.deepseek.com/zh-cn/guides/thinking_mode/),
[Qwen Chat](https://platform.qianwenai.com/docs/api-reference/chat/openai-chat),
[Qwen Responses](https://platform.qianwenai.com/docs/api-reference/chat/openai-responses),
[Qwen Messages](https://platform.qianwenai.com/docs/api-reference/chat/anthropic).

## Send images

Catalog-created Providers use `capabilities.vision`. Fresh image submissions to a
nonvision model fail before message persistence. Existing historical images and
image tool results are projected as explicit unavailable-image notices for a
nonvision model; original Session facts remain intact. Direct adapter construction
can pass `vision=True` or `False`; omission retains the caller-owned declaration.

Responses and Messages preserve native image tool-result structures. Chat keeps
each `tool_call_id` and text result, then appends a multimodal user-role observation
after all results in the batch. The observation names its tool source and preserves
text/image order. It is a wire representation of tool output, not a new human
message or Session record. No vendor/model-name branch or silent API switch is
used. Exact reasoning/continuation items remain replayed. Remote endpoints may
still differ; offline encoding does not establish remote compatibility.

The public submission limits are eight PNG/JPEG/GIF/WebP images, 10 MiB each and
32 MiB combined. Formats accepted by an individual endpoint may be narrower.
Unsupported formats are rejected rather than implicitly converted. Request
identity/counting uses the encoded request where available; heuristic image and
protocol-framing measurements remain uncertain.

Malformed, unsupported or over-limit images in existing tool/history messages
become explicit unavailable-image observations for declared adapters, without
changing the original message. Fresh input validation still rejects these before
persistence. This avoids repeatedly sending the same invalid media on later turns.

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
may extend the total elapsed time. Run records effective transport values. Terminal errors retain bounded structural
diagnostics: up to six causal exception types/categories and eight recent attempt
records with elapsed seconds, HTTP status and partial-delivery state. Raw cause
messages, URLs, headers and credentials are excluded. Core preserves this data
in the result and Session run records, which Eval retains as native evidence.
Retry and timeout policy is unchanged.

Usage records available input/output/cache receipts and optional reasoning-token
counts. Reasoning is a subset of output, not an additional charge in total_tokens;
missing breakdowns remain unknown. Billing conventions remain service-specific.

## Register another service or protocol

For an existing supported service, add another catalog alias. To implement an
endpoint difference, register a distinct `ServiceDefinition` through
`providers.services.register_service` before loading the catalog. Declare supported
protocols, pure parameter validation, prefix-binding requirements and request-control
support. `protocol_overrides` supplies protocol-specific addresses, descriptions
and request/replay controls through the same service resolver used by setup and
adapters. Keep vendor logic inside Providers. Definitions must be installed code;
YAML does not import Python classes.

A new client/protocol pair supplies a Provider factory through
`ProviderRegistry.register(sdk, protocol, factory)`, its own codec, request
validation and offline fixtures. Use `register(..., default=True)` to designate
the setup SDK when several adapters implement that protocol. Manual YAML can
still select another registered SDK explicitly. `registered_pairs()` exposes those registrations
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
