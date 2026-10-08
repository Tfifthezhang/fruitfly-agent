# Configuration Templates

[Up: Examples](../README.md)

Use the interactive model wizard for first setup, or copy the single model catalog below for DeepSeek Flash examples using two API protocols.

| Template | Workspace destination | Contents |
|---|---|---|
| [models.example.yaml](models.example.yaml) | `.fruitfly/models.yaml` | Both DeepSeek Flash protocol profiles in one file |
| [.env.example](.env.example) | `.fruitfly/secrets.env` | Empty `DEEPSEEK_API_KEY` variable |

| Profile | `provider` | `model` | `base_url` |
|---|---|---|---|
| `deepseek-flash-openai` | `openai` | `deepseek-flash` | `https://api.deepseek.com` |
| `deepseek-flash-anthropic` | `anthropic` | `deepseek-flash` | `https://api.deepseek.com/anthropic` |

Both profiles access DeepSeek, with a DeepSeek key. Provider names select Responses or Messages formats; they do not select OpenAI or Anthropic's own models. In the wizard choose the corresponding **Custom** service. DeepSeek documents these endpoints in [model details](https://api-docs.deepseek.com/quick_start/pricing/), [Responses](https://api-docs.deepseek.com/api/create-response/), and [Messages compatibility](https://api-docs.deepseek.com/guides/anthropic_api/).

Create `.fruitfly/` and copy templates only if the destinations are absent. Set `DEEPSEEK_API_KEY` in the secret file or process environment. Select one profile in the terminal, or set `FRUITFLY_MODEL_PROFILE` before first one-shot startup. Keep both profiles in the same catalog or remove the one you do not need.

The example uses a conservative 1,000,000-token working window within the documented 1M context, with output capped at 4096 tokens. These budgets are not the service's maximum output. Optional capability flags keep text-focused defaults; false flags do not disable server-side features. The Responses example explicitly disables thinking with `parameters.reasoning.effort: none`. The Messages adapter cannot configure thinking and follows the server default. Reasoning stream/state recovery remains limited; see [Provider limitations](../../fruitfly_agent/providers/PROVIDER_GUIDE.md#protocol-differences).

Both examples explicitly bound first progress, later stalls, and total invocation time, and allow at most three retries before partial output. See [transport settings](../../fruitfly_agent/providers/PROVIDER_GUIDE.md#bound-waiting-and-retries). Silent reasoning may need a larger first-progress limit.

Copying, parsing, and offline construction do not make requests. Live tasks contact DeepSeek and may incur charges. The examples have not been validated with live requests. Keep keys out of the catalog and repository.

See [Configuration](../../CONFIGURATION.md) for precedence and saving, and [Providers](../../fruitfly_agent/providers/README.md) for adapter behavior.

```bash
.venv/bin/python -m unittest tests.providers.test_providers
```
