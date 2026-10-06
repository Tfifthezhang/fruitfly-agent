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

Copy the public [model template](../../models.example.yaml) to local `models.yaml`. Replace placeholder IDs, endpoints, limits, and capabilities before use; keep key values in `.env` or the process environment.

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
| [registry.py](registry.py), [config.py](config.py) | Registration, construction, and environment loading |
| [anthropic.py](anthropic.py), [anthropic_codec.py](anthropic_codec.py) | Messages requests and codec |
| [openai.py](openai.py), [openai_codec.py](openai_codec.py) | Responses requests and codec |
| [error_classification.py](error_classification.py) | Shared error categories |

Implement Core's Provider protocol, register the adapter, and test messages, streaming, errors, limits, cancellation, and cleanup offline. Providers do not read Session, Lab, or Eval state. API keys come from the prepared environment; no Provider-specific `FRUITFLY_*` variables.

```bash
.venv/bin/python -m tests --area providers -v
```

Real network checks use the explicit [integration smoke](../../tests/integration/README.md) and may incur charges.
