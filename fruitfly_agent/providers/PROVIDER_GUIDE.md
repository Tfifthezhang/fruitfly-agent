# Provider Guide

[Up: Providers](README.md)

`provider` selects an API protocol, not a model vendor. A compatible service can expose the same model through different protocols.

## Protocol differences

| Item | `openai` | `anthropic` |
|---|---|---|
| API | OpenAI Responses | Anthropic Messages |
| SDK | `openai` | `anthropic` |
| System instructions | `instructions` | `system` |
| Tool messages | `function_call` / `function_call_output` | `tool_use` / `tool_result` |
| Extra `parameters` | Unconsumed constructor options forwarded to `responses.create()` | Only explicitly declared constructor options |
| Reasoning | Responses reasoning stream/state not mapped | Thinking can be displayed, but blocks are not preserved for replay |

`capabilities.reasoning: true` declares a model capability; it does not send reasoning parameters or guarantee lossless reasoning-state recovery.

## Model parameters

| Configuration | Result |
|---|---|
| OpenAI `parameters.reasoning.effort: none` | Forwarded as a Responses request option. |
| Anthropic `parameters.reasoning` | Unsupported constructor argument; fails before the request. |
| Anthropic optional adapter settings | `retry_max`, `retry_base_delay` |

Keep nonsecret specifications in `models.yaml` and keys in `.env`. Install both SDKs using the same environment that runs the Agent:

```bash
.venv/bin/python -m pip install -e .
.venv/bin/python -c "import openai, anthropic; print(openai.__version__, anthropic.__version__)"
```

## Configure your service

Copy the public [model template](../../models.example.yaml) to local `models.yaml`. It supplies two protocol examples with placeholder IDs and reserved `.invalid` endpoints:

| Profile | Protocol | Required edits |
|---|---|---|
| `example-responses` | OpenAI Responses | Model ID, Responses-compatible base URL, actual limits, and capabilities |
| `example-messages` | Anthropic Messages | Model ID, Messages-compatible base URL, actual limits, and capabilities |

Keep only usable profiles and rename them if desired. A service offering only Chat Completions cannot use the Responses adapter. Omit `base_url` to use the chosen SDK's default endpoint. Do not infer protocol compatibility from the vendor name.

Both template profiles use `api_key_env: MODEL_API_KEY`. Set that variable in `.env` or the process environment. For different credentials, give each profile its own variable name and set the matching values. Never put key values in the catalog.

The template's numeric limits are illustrative. Check your model's documented limits and set capabilities to match the model and endpoint. Optional `parameters` follow the protocol differences above; omit them unless your service and adapter accept them.

Use a model available to your account. Changing Provider or model requires a new session; recovery checks the actual manifest. Parsing the catalog offline does not verify remote compatibility. Live requests use the network and may incur charges.

| Reference | Purpose |
|---|---|
| [Providers](README.md) | Adapter contracts, limits, and tests |
| [Configuration](../../CONFIGURATION.md#configure-a-model) | Catalog fields and key handling |
| [Integration smoke](../../tests/integration/README.md) | Explicit real Provider checks, requiring network and potentially paid requests |
