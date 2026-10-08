# Tests

[Up: FruitFlyAgent](../README.md)

Verify public contracts, module boundaries, and observable behavior with offline `unittest` tests. Fake model results are not capability or benchmark scores.

## Run checks

```bash
.venv/bin/python -m tests --area lab --area workflows
.venv/bin/python -m tests --module tests.lab.test_search
.venv/bin/python -m tests --area run --list
.venv/bin/python -m unittest discover -s tests -t .
```

| Runner option | Behavior |
|---|---|
| `--area` | Repeatable group selection |
| `--module` | Test module, class, or method; repeated choices deduplicated |
| `--list` | Import and list selected IDs without executing methods |
| No arguments | Full suite |
| Guard failure | Architecture/contracts run first; import or test failures stop selected behavior tests. |
| Exit codes | Failure 1, invalid arguments 2 |

The development runner rejects integration/support and non-test modules. It does not infer change impact or refresh baselines. Standard `unittest` commands remain available; run the full discovery command before delivery.

## Static types

Install the optional development dependencies with `pip install -e '.[dev]'` (network download), then run `.venv/bin/python -m mypy` offline. The explicit module list in `pyproject.toml` covers Core loop/tool/session contracts, Application ownership, and Run configuration/recovery. The gate also includes authorization contracts, Interactive confirmation, Lab permission/environment wrappers, and Run policy construction. Imported types are analyzed silently outside that list; terminal and algorithm implementations are not covered by this gate.

## Groups

| Group | Responsibility |
|---|---|
| [Architecture](architecture/README.md) | Imports, extension boundaries, documentation navigation, and test discovery |
| [Contracts](contracts/README.md) | Reviewed exports, signatures, persistence, and rejection semantics |
| [Core](core/README.md) | Loop, messages, hooks, tools, Session, failures, and cancellation |
| [Providers](providers/README.md) | Model specifications, codecs, streams, errors, and SDK lifecycle |
| [Lab](lab/README.md) | Algorithms, tools, environments, context, packs, and Catalog |
| [Interactive](interactive/README.md) | Application, events, menus, and terminal behavior |
| [Run](run/README.md) | Configuration, assembly, manifest, candidates, recovery, and subprocess bridges |
| [Workflows](workflows/README.md) | Complete offline user paths across modules |
| [Eval](eval/README.md) | Optional benchmark plans, adapters, artifacts, and reports |
| [Support](support/README.md) | Shared substitutes and temporary material, no TestCases |
| [Integration](integration/README.md) | Explicit real Provider smoke requests |

## Write tests

| Rule | Reason |
|---|---|
| Assert public behavior | Avoid fixing unnecessary implementation details. |
| Give each behavior an owner | Module tests cover detailed rules; Workflows verify real module connections and user outcomes. Similar-looking checks at different boundaries may protect different failures. |
| Use named input cases | Share identical setup and use `subTest` for the same rule with different inputs; retain distinct failure, cancellation, and recovery scenarios. |
| Reproduce bugs | Protect the actual failure path. |
| Preserve reviewed baselines | Do not regenerate expected values from the changed implementation. |
| Keep dependency boundaries | Do not expand allowances to resolve a failure. |
| Share helpers through support | No imports from another `test_*.py`; avoid duplicate discovery. |
| Isolate state | Temporary files, fake Providers/HTTP/runners, and reset learning state |
| Preserve failure/cleanup paths | Cover cancellation, budgets, resource release, and recovery when applicable. |
| Keep fixtures in English | Use fullwidth Latin letters, emoji, and combining marks when testing multibyte UTF-8 or terminal cell widths. Preserve the relevant byte lengths and display widths. |

Contract changes require explicit authorization, independent review, caller/compatibility analysis, and synchronized tests/docs. A static import guard is not an arbitrary Python sandbox, and the same editor can change both implementation and baseline.

## External effects

| Path | Effects |
|---|---|
| Default suite | No real keys, model requests, HTTP service access, benchmark downloads, or Docker jobs |
| IPython / PTY / log tests | Local processes and temporary data |
| Integration smoke | Explicit network/model calls, potentially paid |
| CI | Dependency installation uses the network; type and test stages remain offline. |

Error-isolation tests deliberately log failures; judge the final `OK`/`FAILED` and exit status. [GitHub Actions](../.github/workflows/tests.yml) runs macOS/Linux with Python 3.11–3.13 and `TERM=dumb`. See [Contributing](../CONTRIBUTING.md).
