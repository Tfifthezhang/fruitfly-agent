# Reduction

[Up: Context Manager](../README.md)

Summarize history to fit the model projection while preserving recent complete turns and canonical conversation facts. The built-in implementation is `SummarizingCompactor`.

## Behavior

| Method / case | Result |
|---|---|
| `estimate(snapshot)` | Estimate prompt, tools, schemas, and projected messages; not a real tokenizer. The optional `estimate_source` property labels built-in or injected estimators for request/status observation. |
| `check_budget(snapshot)` | Propose a summary when over budget; avoid duplicate proactive reduction during overflow recovery. |
| `react_to_overflow(snapshot, error)` | Reduce retained history within algorithm and Core retry limits. |
| Valid summary | Normal `stop`, nonblank text, no tool calls, smaller projection, within estimated budget. |
| Invalid summary or failed request | Return `None`; do not replace history with placeholders or another trimming strategy. |
| Proactive no-op | Keep the projection and let Core request the main model. |
| Failed overflow recovery | Core returns structured `context_overflow`. |

The input budget subtracts `max(main output limit, min(reserve_tokens, window / 4))` from the context window. If fixed prompt/tools, recent turns, or invalid tool associations prevent a legal reduction, no summary request is made.

## Configuration and state

| Concern | Behavior |
|---|---|
| Configuration | `SummarizingCompactorConfig`; Catalog expands effective defaults into the manifest. |
| Attempts / timeout | `summary_attempts`; `summary_timeout_seconds=60.0` per auxiliary request |
| Auxiliary model | Injected Provider, window, and output limit; directly constructed instances without a window only have character/output bounds. |
| Cancellation | Pass the run signal; propagate task cancellation. |
| Projection tail | Retain the current projection's complete turns, not reconstructed canonical content. |
| External references | Append `context://sha256/…` and `sha256:…` references deterministically within the overall budget. |
| State | No private persistent learning state or permanent retry suppression. |

Summary input includes public message content, tool arguments/results, and prior summaries. It omits image bytes and private thinking; oversized content keeps marked head/tail excerpts. Model requests may incur charges. Heuristic budgets and protocol checks do not establish summary fidelity.

## Files and extension

| File | Responsibility |
|---|---|
| [config.py](config.py) | Typed defaults and validation |
| [summarizing.py](summarizing.py) | Summary requests and reducer implementation |
| [cut.py](cut.py) | Complete-turn cuts and tool associations |
| [estimate.py](estimate.py) | Replaceable token estimation |

Implement a new [ContextReducer](../../../core/context/models.py) and register it in [Catalog](../../catalog/README.md). One runtime has one reduction slot. Core validates, persists, and commits decisions. No module-specific environment variables.

```bash
.venv/bin/python -m unittest tests.lab.test_summarizing_compaction tests.lab.test_reduction_safety tests.lab.test_compaction_cut -v
```
