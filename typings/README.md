# Check optional dependency interfaces

[Up: Tests](../tests/README.md#static-types)

This directory supplies development-only partial stubs through `mypy_path`.
It contains no runtime implementations and is not installed with FruitFlyAgent.

| Declaration | Scope |
|---|---|
| `gepa/strategies/instruction_proposal.pyi` | The renderer and extractor consumed by the GEPA reflection adapter |

The signatures match [GEPA 0.1.4](https://github.com/gepa-ai/gepa/blob/v0.1.4/src/gepa/strategies/instruction_proposal.py).
Keep the renderer's multimodal return alternative: FruitFlyAgent deliberately
rejects it at the text-only adapter boundary. Runtime loading still requires
the pinned optional extra. Stubs do not make that dependency available.

Run `.venv/bin/python -m mypy` to check callers without installing GEPA.
