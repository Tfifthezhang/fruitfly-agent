# Providers

[Up: Runtime Architecture](../README.md)

Adapt model APIs to Core's Provider protocol. Run resolves model specifications and constructs adapters; Core remains independent of vendor SDKs.

| API | Purpose |
|---|---|
| `AnthropicProvider` | Anthropic Messages |
| `OpenAIProvider` | OpenAI Responses |
| `ChatCompletionsProvider` | OpenAI-compatible Chat Completions |
| `ModelSpec`, `ProviderSpec`, `ModelCapabilities` | Exact model/API identity, limits, parameters, and capabilities |
| `ProviderRegistry`, `default_registry` | Construction using environment keys named by `api_key_env` |
| `ProviderRegistry.registered_pairs()` | Read-only registered SDK/protocol choices for setup; no factory invocation |
| `ProviderRegistry.sdk_for(protocol)` | Automatic setup SDK; unique registration or explicit default adapter |
| `load_env` | Prepare the secret environment |
| `ServiceDefinition`, `register_service` in [services.py](services.py) | Service metadata, client controls and explicit custom extension hooks |
| [services.yaml](services.yaml) | Single built-in service/protocol/address table; no model or parameter policies |

See [Configuration](../../CONFIGURATION.md) for file locations and [Provider guide](PROVIDER_GUIDE.md) for protocol differences and parameter examples.

Use the model wizard or the [public template](../../examples/configuration/models.example.yaml). Keep key values in the secret environment and variable names in the catalog. Offline setup validates declarations, not remote service compatibility.

## Requests and errors

| Concern | Behavior |
|---|---|
| Output limit | Smaller of constructor limit and positive `ProviderView.max_tokens`; nonpositive view limits use the constructor value. |
| SDK retries | Disabled |
| Adapter retries | `retry_max=3`: at most 4 attempts per harness call |
| Cancellation | Observe the signal while waiting for headers, chunks, final messages, and retry delays; task cancellation also releases transports. |
| Error mapping | Core `OverflowError`, `RetryableError`, or `FatalError` |
| Stream cleanup | Bound stream/context and owned SDK-client cleanup separately from request deadlines. |
| Usage | Preserve available receipts; missing usage is unknown. |
| Deadlines | SDK connection/read limits plus first progress, later progress, and total invocation deadlines; keepalive is not progress. |
| Partial delivery | Do not retry after text, thinking, or tool-call content reaches the consumer. |
| Retry activity | Emit Core `StreamActivity` events with attempts, delay, error category, and optional HTTP status; no raw headers. |

Harness call budgets do not count individual adapter retry attempts or guarantee monetary cost. Third-party Providers must enforce their declared request-limit semantics.

## Files and extension

| File | Responsibility |
|---|---|
| [specs.py](specs.py) | Model and Provider specifications |
| [request_options.py](request_options.py), [services.py](services.py), [services.yaml](services.yaml) | Protocol shape validation and data-only service metadata |
| [model_setup.py](model_setup.py) | Supported service descriptions and offline validation of new model entries |
| [registry.py](registry.py), [config.py](config.py) | Registration, construction, and environment loading |
| [anthropic.py](anthropic.py), [anthropic_codec.py](anthropic_codec.py) | Messages requests and codec |
| [openai.py](openai.py), [openai_codec.py](openai_codec.py) | Responses requests and codec |
| [chat_completions.py](chat_completions.py), [chat_codec.py](chat_codec.py) | Chat Completions requests and codec |
| [media.py](media.py) | Fresh-input validation and explicit nonvision history/tool projections |
| [replay.py](replay.py) | Exact ordered continuation, response/context binding and safe rebuild boundaries |
| [error_classification.py](error_classification.py) | Shared error categories |
| [transport.py](transport.py) | Validated deadlines, signal-aware waits, retry hints/jitter, and cleanup |

Implement Core's Provider protocol, register the adapter, and test messages, streaming, errors, limits, cancellation, and cleanup offline. Providers do not read Session, Lab, or Eval state. API keys come from the prepared environment; no Provider-specific `FRUITFLY_*` variables.

The offline type gate checks this complete package and requires annotated codec definitions. Anthropic request fields use a typed SDK wire shape inside the adapter; codecs remain SDK-independent and own message serialization. SDK type descriptions do not validate remote service compatibility.

```bash
.venv/bin/python -m tests --area providers -v
```

Real network checks use the explicit [integration smoke](../../tests/integration/README.md) and may incur charges.

[workspace.py](workspace.py) centralizes model and secret locations for Run and Eval. See [Configuration](../../CONFIGURATION.md#files-and-precedence) for canonical workspace paths and explicit catalog precedence. `load_env()` reads only the selected workspace; an explicit file argument reads that file.

The model wizard offers the exact `capabilities` names from the model catalog. Optional selections are declarations of service support, not connection tests. The Run harness requires `tools` and `streaming`; invalid boolean selections fail before staging.

Four named services and the custom entry select protocol before model fields.
The packaged service table and registered adapters supply choices; the registry
resolves SDK automatically. Setup and adapters share the table's addresses and
client controls. Model ID, limits and optional capabilities are entered explicitly.
The protocol page warns that some models may not support the selected protocol.
The parameters editor offers medium reasoning effort in protocol-native fields
and accepts a complete JSON object or `{}` for server defaults. Custom protocols
use empty defaults. Capability declarations do not change these choices. Built-ins do not validate or
rewrite model-specific options, including options a remote service may ignore.
See [additional examples](../../examples/configuration/additional-models.example.yaml).

`MODEL_FIELD_ORDER` and `ordered_model_entry` in `specs.py` define setup/serialization
order. Service and protocol precede automatic SDK; `parameters` follows capabilities
and `transport` is always last. Field order changes no model identity or values.

`parameters` contains API options; `transport` contains client deadlines/retries.
`service` explicitly selects endpoint metadata without URL guessing. Daily and
experiment aliases use the same validated specification. See the
[Provider guide](PROVIDER_GUIDE.md) for exact replay, signed-context restrictions,
server-tool observations, supported formats and extension limits.

Model entries require separate `sdk` and `protocol` fields. Registry construction
uses both IDs; the combined `provider` configuration field is rejected.
Custom adapters register with `register(sdk, protocol, factory, default=True)`
when designating the setup default. Without a default, SDK resolution requires
exactly one adapter per protocol. Manual YAML retains explicit pair selection.
The same registry supplies protocol choices and the read-only SDK through the injected host, so the terminal has
no SDK or protocol enumeration. Internal continuation records retain their stable
namespace and version independently of configuration field names.

## Expose input measurement

[token_counting.py](token_counting.py) contains count-field and continuation
constraints. `input_count_supported`, `count_input`, `input_count_identity`,
`input_measurement_scope`, `effective_output_limit`, `context_usage_tokens` and
`can_rebase_context` are
optional public capabilities. Transparent wrappers must preserve them using
Core's forwarding helper. Responses counting reuses the actual prepared payload;
unsupported service/protocol combinations do not guess a remote endpoint.
See [measurement precision and limits](../lab/context_manager/measurement/README.md).
