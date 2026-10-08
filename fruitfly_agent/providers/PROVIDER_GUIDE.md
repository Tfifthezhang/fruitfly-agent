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
| Reasoning | Text/summary reasoning deltas can be displayed; opaque reasoning items are not preserved for replay | Thinking can be displayed, but blocks are not preserved for replay |

`capabilities.reasoning: true` declares a model capability; it does not send reasoning parameters or guarantee lossless reasoning-state recovery.

Responses represents input and output as typed items, including `function_call` and `function_call_output`; see the [official OpenAI guide](https://developers.openai.com/api/docs/guides/migrate-to-responses). This project's Messages adapter sends `messages` and separate `system` instructions, with `tool_use` and `tool_result` content blocks. The adapters translate these formats into Core messages. Protocol choice does not determine model quality, context limits, or service compatibility.

The setup menu separates official accounts from custom compatible services. Official entries default to the corresponding SDK endpoint; custom entries require a base URL. Keys must belong to the selected service. A Chat Completions-only service cannot use this project's Responses adapter.

## Model parameters

| Configuration | Result |
|---|---|
| OpenAI `parameters.reasoning.effort: none` | Forwarded as a Responses request option. |
| Anthropic `parameters.reasoning` | Unsupported constructor argument; fails before the request. |
| Both adapters | Transport/retry settings below are constructor options, not API body fields. |

## Bound waiting and retries

Set these values under a model's `parameters`. All time values are seconds and must be finite and positive, except `retry_base_delay`, which can be zero. `retry_max` is a nonnegative integer; `retry_jitter` is a finite fraction from 0 to 1.

| Parameter | Default | Behavior |
|---|---:|---|
| `connect_timeout` | 10 | SDK connection timeout |
| `timeout` | 600 | SDK read/write/pool timeout |
| `first_progress_timeout` | 180 | Per-attempt deadline from request start until meaningful output, including header wait |
| `stall_timeout` | 180 | Maximum gap between meaningful output events |
| `total_timeout` | 900 | Deadline for one harness Provider invocation, including attempts and backoff |
| `cleanup_timeout` | 5 | Separate allowance for each transport/client cleanup operation |
| `retry_max` | 3 | At most four attempts by default |
| `retry_base_delay` | 1 | Exponential base delay |
| `retry_jitter` | 0.2 | Add up to this fraction of the delay |

Meaningful output includes nonempty text, thinking, and tool-call starts/arguments. Keepalive and empty deltas do not reset the deadline. A model doing silent internal reasoning can still exceed the first-progress deadline; configure a larger limit when needed. Deadlines report exceeded waiting limits, not proof that the server is busy. Cleanup may extend wall time beyond the request deadline.

Before partial delivery, retry transient failures within the attempt and total limits; honor numeric or HTTP-date `Retry-After` hints. After content delivery, failures are terminal, so already displayed content is not duplicated. No output does not establish that the remote request was unexecuted or free. Usage on failed attempts can be unknown. Core call budgets still count harness invocations rather than adapter attempts.

Adapters publish effective defaults and overrides through `transport_parameters`; Run includes this identity in the full manifest. A resumed session must match it. `StreamActivity` is public Core observation vocabulary; consumers should handle its waiting/retrying/timeout phases or ignore it, and call `AssistantMessageEventStream.aclose()` when stopping consumption.

Keep nonsecret specifications in `.fruitfly/models.yaml` and keys in `.fruitfly/secrets.env`. Install both SDKs using the same environment that runs the Agent:

```bash
.venv/bin/python -m pip install -e .
.venv/bin/python -c "import openai, anthropic; print(openai.__version__, anthropic.__version__)"
```

## Configure your service

Copy the public [model template](../../examples/configuration/models.example.yaml) to local `.fruitfly/models.yaml`. It supplies two profiles for the same `deepseek-flash` model through DeepSeek endpoints:

| Profile | Protocol | API base URL |
|---|---|---|
| `deepseek-flash-openai` | OpenAI Responses | `https://api.deepseek.com` |
| `deepseek-flash-anthropic` | Anthropic Messages | `https://api.deepseek.com/anthropic` |

Keep only usable profiles and rename them if desired. A service offering only Chat Completions cannot use the Responses adapter. Omit `base_url` to use the chosen SDK's default endpoint. Do not infer protocol compatibility from the vendor name.

Both template profiles use `api_key_env: DEEPSEEK_API_KEY`. Set that variable in `.fruitfly/secrets.env` or the process environment. For different credentials, give each profile its own variable name and set the matching values. Never put key values in the catalog.

The template uses conservative working/output budgets. Both profiles need a DeepSeek key. The Responses example disables thinking with `reasoning.effort: none`; the Messages adapter cannot configure thinking and uses the server default. See [example budgets, official sources, and unverified live paths](../../examples/configuration/README.md). Check documented limits and capabilities when customizing. Optional `parameters` follow the protocol differences above; omit them unless your service and adapter accept them.

Use a model available to your account. Changing Provider or model requires a new session; recovery checks the actual manifest. Parsing the catalog offline does not verify remote compatibility. Live requests use the network and may incur charges.

| Reference | Purpose |
|---|---|
| [Providers](README.md) | Adapter contracts, limits, and tests |
| [Configuration](../../CONFIGURATION.md#configure-a-model) | Catalog fields and key handling |
| [Integration smoke](../../tests/integration/README.md) | Explicit real Provider checks, requiring network and potentially paid requests |
