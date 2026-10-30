# Tests

[Up: FruitFlyAgent](../README.md)

Verify public contracts, module boundaries, and observable behavior with offline `unittest` tests. Fake model results are not capability or benchmark scores.

## Run checks

```bash
.venv/bin/python -m tests --area lab --area workflows
.venv/bin/python -m tests --module tests.lab.test_improvement_pipeline
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

Install the optional development dependencies with `pip install -e '.[dev]'` (network download), then run `.venv/bin/python -m mypy` offline. Development dependencies include pinned mypy and PyYAML stubs. The module list and per-module rules in `pyproject.toml` define the gate.

The same gate works with or without the optional `benchmarks` extra. When Harbor
is installed, mypy reads its inline annotations despite its missing `py.typed`
marker. CI checks both dependency configurations; it does not run real benchmarks.

| Checked area | Scope |
|---|---|
| Core and Application | Loop/tool/session contracts, lifecycle ownership, authorization, improvement capabilities, and correction materials |
| Lab | Permission/environment wrappers, task packages/scoring, improvement contracts, shared budgets, and editor experiments |
| Providers | The complete package, including message codecs, transport, model setup, and registry |
| Run | Configuration/recovery, improvement jobs, permission construction, storage, and host adapters |
| Terminal | Command registration/bindings, live input, generic menus, and configuration menus |
| Eval | Benchmark adapters, catalog, requests, execution, reports, storage, and installation |

Command routing, command metadata/completion, terminal input/display, screen controls, hidden input and shared configuration choices are also checked with complete function annotations. Copy-view regressions use fake streaming events and a local PTY; they verify frozen output, retained drafts and terminal-mode restoration without model access.

The Core loop, task packages/scoring, message codecs, runtime-description adapter, live input, generic/configuration menus, and Harbor result adapter also reject definitions with missing annotations. Policy-defined case mappings and SDK/JSON boundaries retain dynamic data where needed; this is not a fully strict whole-project check. Imported types outside the selected modules are analyzed silently. Terminal rendering, other feature menus, most algorithm implementations, the Eval CLI, and the optional installed Harbor Agent bridge remain outside the gate.

## Groups

| Group | Responsibility |
|---|---|
| [Architecture](architecture/README.md) | Imports, extension boundaries, documentation navigation, and test discovery |
| [Contracts](contracts/README.md) | Reviewed exports, signatures, persistence, and rejection semantics |
| [Core](core/README.md) | Loop, messages, hooks, tools, Session, failures, and cancellation |
| [Improvement](improvement/README.md) | Reliable stages, optimization admission, budgets and scheduling |
| [RSI](rsi/README.md) | Generation transitions, activation binding and recovery allowances |
| [Providers](providers/README.md) | Model specifications, codecs, streams, errors, and SDK lifecycle |
| [Lab](lab/README.md) | Algorithms, tools, environments, context, packs, and Catalog |
| [Interactive](interactive/README.md) | Application, events, menus, and terminal behavior |
| [Run](run/README.md) | Configuration, assembly, manifest, candidates, recovery, and subprocess bridges |
| [Workflows](workflows/README.md) | Complete offline user paths across modules |
| [Eval](eval/README.md) | Optional single-configuration benchmarks, artifacts, and reports |
| [Experiments](experiments/README.md) | Independent entry points, file defaults, model roles and scoped lifecycle |
| [Support](support/README.md) | Shared substitutes and temporary material, no TestCases |
| [Process fixtures](fixtures/README.md) | Offline child-process protocol peers, no TestCases |
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

Optional MCP protocol tests use a standard-library peer in a local child process,
with no network or real server. Install `.[mcp]` to run them; SDK-dependent cases
skip without that extra. Configuration and default-import isolation checks always
run. [The REA probe](../examples/mcp/rea/README.md) is an explicit external check,
excluded from discovery.

| Path | Effects |
|---|---|
| Default suite | No real keys, model requests, HTTP service access, benchmark downloads, or Docker jobs |
| IPython / PTY / log tests | Local processes and temporary data |
| Integration smoke | Explicit network/model calls, potentially paid |
| CI | Dependency installation uses the network; type and test stages remain offline. |

Error-isolation tests deliberately log failures; judge the final `OK`/`FAILED` and exit status. [GitHub Actions](../.github/workflows/tests.yml) runs macOS/Linux with Python 3.11–3.13 and `TERM=dumb`. See [Contributing](../CONTRIBUTING.md).

Eval checks cover native container commands, installation material, exact task coverage,
Session/ATIF trajectories, explicit non-interactive authorization and official reports.
The [Eval tests](eval/README.md) use fake Providers and local processes. Real model
quality, Harbor containers and Docker image identity require separately authorized
integration work. Generic improvement remains covered independently by the
[workflow tests](workflows/README.md).

Command-completion checks cover registered/hidden/overridden commands, custom help,
range edits, prefix filtering, dismissal, history, paste and permission/copy input.
Local PTY checks exercise the complete frontend: typing shows candidates, Tab edits
without executing, Enter dispatches once, and terminal modes restore on exit.

## Design and maintain tests

Assign each public behavior one detailed test owner. Use Workflows to verify real
connections between those owners. A boundary-specific assertion may remain at
multiple layers when it protects a distinct wiring failure.

| Before adding or changing tests | Required action |
|---|---|
| Choose placement | Match the production owner. Improvement and RSI runtime tests have independent areas; concrete policies remain in Lab. |
| Add another case | Name the failure or outcome it protects. Use `subTest` for input variations of the same rule. |
| Build a fixture | Keep one-use helpers local. Reuse existing support before adding a shared fixture; support owns no product assertions, TestCases or discovery hooks. |
| Start a terminal child | Use `TerminalProcess` or `run_terminal` from [terminal support](support/terminal_process.py), with bounded waits and guaranteed cleanup. |
| Test a terminal flow | Assert observable labels, decisions and effects. Use visible menu labels when row positions are incidental. |
| Remove an assertion | Identify the retired contract or the remaining test that protects the behavior. Keep distinct failure, cancellation, isolation and recovery scenarios. |
| Split a file | Separate independently changing responsibilities and remove repeated setup. File length alone does not establish redundancy. |
| Change an API | Review consumers and update the explicit baseline by hand; never derive expected exports from implementation. |
| Move a group | Update runner areas, discovery, docs and commands together; each case must be discovered exactly once. |

Architecture checks reject overwritten class/method definitions, repeated literal
dictionary keys that could hide contract entries, PTY lifecycle
imports in test modules, cross-test imports, support discovery, duplicate test IDs
and unregistered test areas. Guard-detection tests inject violations to prove the
checks work. These guards do not replace review of behavioral coverage.

Packaging and freezing tests must run the copied artifact in an isolated process
and assert that imports resolve from that artifact. Exercise declared runtime
resources as well as Python modules. Preserve exclusion of secrets and local
state. A `.py`-only file list is not evidence that an Agent runtime is complete.
See [resource regressions](eval/README.md) and the
[developer smoke sequence](../GETTING_STARTED.md#check-the-agent-offline).
