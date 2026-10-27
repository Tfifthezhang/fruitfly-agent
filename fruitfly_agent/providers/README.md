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
| `load_env` | Prepare the secret environment |
| `ServiceDefinition`, `register_service` in [services.py](services.py) | Pure endpoint rules, request controls and continuation constraints |

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
| [request_options.py](request_options.py), [services.py](services.py) | Shared offline parameter validation and explicit service rules |
| [model_setup.py](model_setup.py) | Supported service descriptions and offline validation of new model entries |
| [registry.py](registry.py), [config.py](config.py) | Registration, construction, and environment loading |
| [anthropic.py](anthropic.py), [anthropic_codec.py](anthropic_codec.py) | Messages requests and codec |
| [openai.py](openai.py), [openai_codec.py](openai_codec.py) | Responses requests and codec |
| [chat_completions.py](chat_completions.py), [chat_codec.py](chat_codec.py) | Chat Completions requests and codec |
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

Explicit Qwen, BigModel and DeepSeek presets supply editable model/endpoint/limit
defaults. Providers generate request settings from the reasoning selection and
provide full transport defaults for the final review; staging persists the same
values. Custom services retain empty API options rather than guessing from a URL.
See [additional examples](../../examples/configuration/additional-models.example.yaml).

`parameters` contains API options; `transport` contains client deadlines/retries.
`service` explicitly selects endpoint rules without URL guessing. Daily and
experiment aliases use the same validated specification. See the
[Provider guide](PROVIDER_GUIDE.md) for exact replay, signed-context restrictions,
server-tool observations, supported formats and extension limits.

Model entries require separate `sdk` and `protocol` fields. Registry construction
uses both IDs; the combined `provider` configuration field is rejected.
Custom adapters register with `register(sdk, protocol, factory)`. The same registry
supplies SDK/protocol form choices through the injected host, so the terminal has
no SDK or protocol enumeration. Internal continuation records retain their stable
namespace and version independently of configuration field names.
