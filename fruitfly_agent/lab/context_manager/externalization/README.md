# Externalization

[Up: Context Manager](../README.md)

Move large text out of the model projection while keeping a stable way to read it. Canonical Session messages remain intact.

| Mechanism | Behavior |
|---|---|
| `ipython-tool` | Run Python in a persistent workspace. |
| `rlm-ipython` | Also externalize large context into retrievable Session artifacts. |
| [Programmatic context](programmatic_context/README.md) | Artifact access, IPython execution, and budgeted auxiliary model queries |

## Research basis

The design draws on Zhang et al., [Recursive Language Models](https://arxiv.org/abs/2512.24601v3), especially Section 2: keep long inputs in a programmable environment and let the model inspect or transform them through code and sub-model calls.

| Paper idea | FruitFlyAgent scope |
|---|---|
| External input with symbolic access | Content-addressed artifacts and a `context` API |
| Programmable inspection | Persistent IPython workspace |
| Sub-model calls | Budgeted `llm_query`, depth 1 |
| Recursive inference and large outputs | Full recursive scaffolding and unbounded output are not implemented. |

This is an adaptation within the existing Agent loop, not a reproduction of the paper's full system or results.

## Extend externalization

| Concern | Contract |
|---|---|
| Projection | Implement `ContextTransformer`; use read-only input and return a new frame. |
| Access | Make content retrievable before replacing it with a reference. |
| Identity | Stable artifact ID and documented read API |
| Storage | Session paths injected by the host; declare lifetime and cleanup. |
| Composition | Preserve tool-call/result associations and valid source mappings. |
| Assembly | Depend on the `ContextArtifactWriter` component, not concrete IPython internals. |
| Resources | Register newly constructed owned objects with `context.own`. |

Recovery restores artifacts and explicit JSON state, not arbitrary Python objects. IPython inherits user permissions; auxiliary model calls may incur charges. Detailed limits belong to [Programmatic context](programmatic_context/README.md).

```bash
.venv/bin/python -m unittest tests.lab.test_rlm -v
```
