# Contributing

[Up: FruitFlyAgent](README.md)

Report problems through Issues and submit focused changes through Pull Requests.

## Set up

| Requirement | Details |
|---|---|
| Platform | macOS or Linux (POSIX); native Windows unsupported, WSL2 unverified |
| Python | 3.11+ for the Agent; 3.12+ for the optional Harbor extra |
| Dependencies | Declared in `pyproject.toml` |
| Platform interfaces | Session file locks, terminal input, subprocess cleanup, and function scoring use POSIX APIs. |

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e .
```

## Verify changes

```bash
.venv/bin/python -m tests --area lab --area workflows
.venv/bin/python -m unittest discover -s tests -t .
```

The development runner checks architecture and contracts before selected tests. Run the complete offline suite before delivery. Real Provider smoke requests require an explicit invocation and may incur charges.

| Change | Required evidence |
|---|---|
| Public behavior, configuration, or errors | Updated behavior tests and documentation |
| Bug fix | A regression that reproduces the defect |
| Module or interface boundary | Architecture and contract checks |
| Documentation or comments only | Link, example, and consistency checks; new behavior tests are optional |
| Online dependency | Installation, cost, and network requirements, plus offline substitutes |

See [Tests](tests/README.md) for groups and [Lab](fruitfly_agent/lab/README.md#develop-an-algorithm) for algorithm integration. Keep reviewed API baselines and dependency rules intact; do not refresh snapshots or weaken assertions to make failures disappear.

## Write code and documentation

| Rule | Apply it this way |
|---|---|
| Preserve module ownership | Follow the [runtime architecture](fruitfly_agent/README.md). |
| Keep examples executable | Use current imports, arguments, model profiles, and commands. |
| Write in English | Use direct sentences and task-oriented headings; prefer tables for options, contracts, and file responsibilities. |
| Maintain navigation | Parent READMEs link to child READMEs; children link back. Cross-links connect related responsibilities. |
| Describe the current system | No changelogs, migration narratives, implementation diaries, or roadmaps in documentation. |
| Identify research sources | Cite papers in the relevant algorithm README and distinguish the implemented scope from the paper. |
| Protect local data | Exclude local `models.yaml`, secrets, `.env`, `.fruitfly/`, caches, and build products. Publish model examples in `models.example.yaml`. |

Describe the problem, resulting behavior, validation, and unverified external paths in each change description. Shared test helpers belong in `tests/support`; do not import helpers or TestCases from another `test_*.py` file.

The ignore rule for local `models.yaml` does not remove an already tracked file. When preparing a source repository for publication, check that only `models.example.yaml` is tracked; local catalogs must stay outside the published source. VCS operations require workspace authorization under [Project rules](AGENTS.md).

## Build and publish

```bash
.venv/bin/python -m pip install build
.venv/bin/python -m build
```

| Check | Expected result |
|---|---|
| Source contents | Root guides and licenses, packaging files, public model examples, runtime, Eval, examples, tests, and workflows |
| Exclusions | Local keys, runtime data, virtual environments, assistant settings, caches, and build artifacts |
| Distribution contents | Source archive retains `assets/logo.svg`, `models.example.yaml`, `.env.example`, and license notices; local `models.yaml` and other `.env.*` files excluded |
| Installed wheel | CLI and default prompt work from outside the checkout |
| Model configuration | Wheel users provide a catalog in their workspace or configure its path. |

[GitHub Actions](.github/workflows/tests.yml) runs offline checks on macOS/Linux with Python 3.11–3.13 and checks built distributions with harmless secret/state probes. Dependency installation uses the network; tests do not call model services or run benchmark containers. Public CI results are available on the repository's Actions page.

| Reference | Purpose |
|---|---|
| [Project rules](AGENTS.md) | Workspace policy and engineering constraints |
| [Tests](tests/README.md) | Verification commands and ownership |
| [Third-party notices](THIRD_PARTY_NOTICES.md) | Attribution and upstream license |
