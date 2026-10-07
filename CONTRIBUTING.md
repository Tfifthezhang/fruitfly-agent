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
# Download development dependencies; no model requests.
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/python -m mypy
```

The development runner checks architecture and contracts before selected tests. Run the complete offline suite before delivery. The mypy gate checks the runtime and interface modules listed in `pyproject.toml`; it analyzes imported types without reporting errors from modules outside that list. It is not a whole-project strict typing guarantee. Real Provider smoke requests require an explicit invocation and may incur charges.

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
| Protect local data | Exclude local `models.yaml`, secrets, `.env`, `.fruitfly/`, caches, and build products. Publish model examples under `examples/configuration/`. |

Describe the problem, resulting behavior, validation, and unverified external paths in each change description. Shared test helpers belong in `tests/support`; do not import helpers or TestCases from another `test_*.py` file.

The ignore rule for local `models.yaml` does not remove an already tracked file. When preparing a source repository for publication, check that only public templates under `examples/configuration/` are tracked; local catalogs must stay outside the published source. VCS operations require workspace authorization under [Project rules](AGENTS.md).

## Push source changes to GitHub

For an existing Git checkout, inspect the current branch, remote, and pending changes:

```bash
git status --short
git branch --show-current
git remote -v
git ls-files --cached --ignored --exclude-standard
git add --dry-run --all
```

Run these commands locally; do not paste secret-bearing diffs or credential-bearing remote URLs into public reports. The branch command must show a named branch. The ignored-file check should produce no output; investigate any listed files before staging. Ignore rules do not remove already tracked files. Use `git rm --cached -- PATH` for a tracked local file, or `git rm -r --cached -- DIRECTORY` for local state, after confirming the path. These commands preserve working copies. Removing a file from the current commit does not erase it from earlier history; revoke any exposed credentials before publication.

If `origin` is absent, create an empty GitHub repository and add its URL. Replace `OWNER` and `REPOSITORY` below with your actual names; use a URL without embedded credentials. An SSH remote requires an SSH key configured for GitHub.

```bash
git remote add origin git@github.com:OWNER/REPOSITORY.git
```

Run the checks in [Verify changes](#verify-changes), then stage and review the source changes before committing:

```bash
git add --all
git diff --cached --stat
git diff --cached --name-status
git diff --cached --check
git diff --cached
git commit -m "Improve model setup and restored conversation display"
git push -u origin HEAD
```

Choose a commit message that describes your actual changes. Push the named current branch; open a Pull Request when it is a development branch. If the remote has newer commits and rejects the push, fetch and review that history before integrating it; do not force-push over it. After pushing, check the repository's Actions page for the offline tests and package job.

Publish source, public examples, tests, guides, licenses, and workflows. Keep local `.fruitfly/`, model catalogs, secrets, virtual environments, caches, assistant settings, and `dist/` outside Git. Source publication does not require uploading a wheel or publishing to a package registry.

## Build and publish

```bash
.venv/bin/python -m pip install build
.venv/bin/python -m build
```

| Check | Expected result |
|---|---|
| Source contents | Root guides and licenses, packaging files, public model examples, runtime, Eval, examples, tests, and workflows |
| Exclusions | Local keys, runtime data, virtual environments, assistant settings, caches, and build artifacts |
| Distribution contents | Source archive retains `assets/logo.svg`, `examples/configuration/models.example.yaml`, `examples/configuration/.env.example`, and license notices; local `models.yaml` and other `.env.*` files excluded |
| Installed wheel | CLI, default prompt, registered extension, function worker, IPython subprocess, and Eval installation material preparation work outside the checkout |
| Model configuration | Wheel users provide a catalog in their workspace or configure its path. |

[GitHub Actions](.github/workflows/tests.yml) runs offline checks on macOS/Linux with Python 3.11–3.13 and checks built distributions with harmless secret/state probes. Dependency installation uses the network; tests do not call model services or run benchmark containers. Public CI results are available on the repository's Actions page.

Rebuild from the current source before attaching distribution files to a release. Existing files in `dist/` may predate source changes; their presence is not evidence that they contain the current implementation.

Build a wheel for internal distribution without publishing it. Install into a separate environment, then run the [installed package checks](examples/packaging/README.md) from outside the checkout:

```bash
python3 -m venv /tmp/fruitfly-wheel
/tmp/fruitfly-wheel/bin/python -m pip install dist/*.whl
```

Installation may download dependencies. Keep version `0.1`; record the exact wheel hash and corresponding source for reproducibility. Package version alone is not a source identity. Publishing to a package registry is a separate operation.

| Reference | Purpose |
|---|---|
| [Project rules](AGENTS.md) | Workspace policy and engineering constraints |
| [Tests](tests/README.md) | Verification commands and ownership |
| [Third-party notices](THIRD_PARTY_NOTICES.md) | Attribution and upstream license |
