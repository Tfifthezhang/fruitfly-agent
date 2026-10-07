# Providers

[Up: Runtime Architecture](../README.md)

Adapt model APIs to Core's Provider protocol. Run resolves model specifications and constructs adapters; Core remains independent of vendor SDKs.

| API | Purpose |
|---|---|
| `AnthropicProvider` | Anthropic Messages |
| `OpenAIProvider` | OpenAI Responses |
| `ModelSpec`, `ProviderSpec`, `ModelCapabilities` | Exact model/API identity, limits, parameters, and capabilities |
| `ProviderRegistry`, `default_registry` | Construction using environment keys named by `api_key_env` |
| `load_env` | Prepare the secret environment |

See [Configuration](../../CONFIGURATION.md) for file locations and [Provider guide](PROVIDER_GUIDE.md) for protocol differences and parameter examples.

Use the terminal model wizard or copy the public [model template](../../examples/configuration/models.example.yaml) to local `.fruitfly/models.yaml` for manual setup. The single catalog contains DeepSeek Flash Responses and Messages profiles; configure a DeepSeek key and select a profile before use; keep key values in `.fruitfly/secrets.env` or the process environment. Wizard validation is offline and does not establish remote compatibility or model capability.

## Requests and errors

| Concern | Behavior |
|---|---|
| Output limit | Smaller of constructor limit and positive `ProviderView.max_tokens`; nonpositive view limits use the constructor value. |
| SDK retries | Disabled |
| Adapter retries | `retry_max=3`: at most 4 attempts per harness call |
| Cancellation | Check before requests, at retry boundaries, and during stream events; task cancellation interrupts event waits. |
| Error mapping | Core `OverflowError`, `RetryableError`, or `FatalError` |
| Stream cleanup | Release SDK stream/context before final delivery, including failure and cancellation. |
| Usage | Preserve available receipts; missing usage is unknown. |

Harness call budgets do not count individual adapter retry attempts or guarantee monetary cost. Third-party Providers must enforce their declared request-limit semantics.

## Files and extension

| File | Responsibility |
|---|---|
| [specs.py](specs.py) | Model and Provider specifications |
| [model_setup.py](model_setup.py) | Supported service descriptions and offline validation of new model entries |
| [registry.py](registry.py), [config.py](config.py) | Registration, construction, and environment loading |
| [anthropic.py](anthropic.py), [anthropic_codec.py](anthropic_codec.py) | Messages requests and codec |
| [openai.py](openai.py), [openai_codec.py](openai_codec.py) | Responses requests and codec |
| [error_classification.py](error_classification.py) | Shared error categories |

Implement Core's Provider protocol, register the adapter, and test messages, streaming, errors, limits, cancellation, and cleanup offline. Providers do not read Session, Lab, or Eval state. API keys come from the prepared environment; no Provider-specific `FRUITFLY_*` variables.

```bash
.venv/bin/python -m tests --area providers -v
```

Real network checks use the explicit [integration smoke](../../tests/integration/README.md) and may incur charges.

[workspace.py](workspace.py) centralizes model and secret locations for Run and Eval. See [Configuration](../../CONFIGURATION.md#files-and-precedence) for defaults, legacy fallback, and explicit catalog precedence. `load_env()` reads only the selected workspace; an explicit file argument reads that file.

The model wizard offers the exact `capabilities` names from the model catalog. Optional selections are declarations of service support, not connection tests. The Run harness requires `tools` and `streaming`; invalid boolean selections fail before staging.
