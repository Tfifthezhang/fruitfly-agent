# Measure request budgets

[Up: Context Manager](../README.md)

Select `context-measurement` to install `MeasurementService` through Catalog.
It operates independently of the selected [reduction](../reduction/README.md).
`MeasurementConfig` owns strict defaults; [registration.py](registration.py)
assembles the service and [improvement.py](improvement.py) exposes its H surface.

| Result | Meaning |
|---|---|
| `exact` | A declared Provider count endpoint measured the encoded request. |
| `tokenizer` | Reserved contract quality for an injected complete tokenizer; no built-in tokenizer claims it. |
| `heuristic` | [Text/image estimator](methods/heuristic/README.md), explicit framing uncertainty and margin. |
| `unknown` | No usable measurement; cannot pass preflight. |

Core measures after request hooks and transformations, checks again after
reduction hooks, and refuses an over-budget main request. The condition is
`input_tokens + effective_output_reserve + margin <= context_window`. Output
allowance is capped by the actual Provider; hidden tools do not consume input.
Tool-result images count just like user images. Replay state is included in
request identity and marked uncertain in heuristic results.

`provider_count=false` is the offline default. When enabled, native OpenAI
Responses with explicit `service: openai` shares the request encoder with
`responses.input_tokens.count`. Generic proxies and Chat Completions do not
inherit that endpoint. Unsupported/failing counting falls back with heuristic
quality; `strict=true` instead requires exact counting and fails closed.
Counting has a separate timeout and cancellation check; an unconfirmed
cancellation is terminal. A bounded cache uses Provider request identity,
including options, tools, replay and output settings. Counting is a network
operation, separate from model generation allowances; remote costs are not
inferred. No real requests run in default tests.

The same service checks auxiliary requests when a reduction installer receives it.
Auxiliary receipts calibrate their own Provider/model/options/tool scope; they do
not replace the main request occupancy.

Reported usage calibrates estimates upward within bounded Provider/model/options/tool/
continuation groups. Calibration never changes quality to exact. Responses input
already includes cache hits; Anthropic input occupancy adds separately reported
cache reads and creation. Missing usage remains unknown. Calibration is runtime
local and is not carried into independent candidates or Sessions.

H grants may tune estimator, character coefficient, margins, count timeout and
sample bound. `provider_count` and `strict` remain protected from parameter
candidates. Exactness, credentials and outer limits are not tunable claims.
Heuristics may undercount unfamiliar encodings; Provider overflow recovery
remains necessary. Exact counting does not prove content quality.

```bash
.venv/bin/python -m unittest tests.lab.test_context_measurement tests.providers.test_token_counting -v
```
