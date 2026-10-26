# Architecture Tests

[Up: Tests](../README.md)

Protect dependency direction, Core SDK independence, generic algorithm hosts, production/test separation, documentation navigation, and test discovery.

| Files | Protects |
|---|---|
| `checks.py` | Static import analysis, including relative/function/TYPE_CHECKING imports and supported literal dynamic imports |
| `test_boundaries.py / test_guard_detection.py` | Production rules and deliberate violation detection |
| `test_documentation.py` | READMEs, file/heading links, root reachability, parent/backlink tree, English text and a dataset-neutral server guide, project identity, and version consistency |
| `test_component_configuration.py` | Pure registered configuration discovery, documented ownership and extension loading without host dispatch |
| `test_ci.py` | Execute the workflow's built-in prompt assertion offline to detect stale packaging checks; installed-wheel checks remain in CI. |
| `test_suite_structure.py / test_runner.py` | Discovery, shared helpers, explicit online isolation, and fail-fast guard execution |

Do not widen dependency allowances to make checks pass. Static checks do not analyze arbitrary reflection or execution.

Run service checks reject dependencies on its composition Factory, whole-controller constructor arguments, foreign private attributes, and reversed internal responsibility edges. Public composition entries can bind concrete services; leaf services consume explicit capabilities.

Interactive checks reject private cross-module access in helpers/feature handlers, feature branches in the terminal input loop, and bundled search/material/candidate contracts. Terminal import checks include all nested feature modules. Directory checks reject reversed responsibility edges, cross-feature dependencies, and implementation imports from Contracts; root layout checks prevent flat module accumulation.

```bash
.venv/bin/python -m unittest discover -s tests/architecture -t . -v
```

`test_improvement_boundaries.py` protects separate editing/assessment ownership,
independent Improvement/RSI direction and the optional Eval boundary. Existing
module dependency allowances are unchanged.
