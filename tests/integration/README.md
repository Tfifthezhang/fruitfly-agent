# Integration Smoke

[Up: Tests](../README.md)

Explicit real Provider checks. These use the network, may incur charges, and are excluded from default offline discovery.

Copy and customize the [model template](../../examples/configuration/models.example.yaml), configure `.fruitfly/models.yaml` and `.fruitfly/secrets.env`, then choose an available profile. The command below uses the `deepseek-flash-openai` profile and requires a usable `DEEPSEEK_API_KEY`:

```bash
.venv/bin/python -m tests.integration.provider_smoke --models-file .fruitfly/models.yaml --model-profile deepseek-flash-openai --json .fruitfly/smoke/deepseek-flash-openai.json
```

| Input | Meaning |
|---|---|
| Model profile | Must exist and be usable by your account. |
| API key | Read from the environment variable named by `api_key_env`. |
| Output | Local smoke result; keep private runtime data out of source releases. |

See [Configuration](../../CONFIGURATION.md) and [Providers](../../fruitfly_agent/providers/README.md). Do not run this as an automatic documentation check.
