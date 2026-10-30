# Extension Hosting

[Up: Run](../README.md)

Load explicitly selected developer code, compose its contributions and replace
idle runtimes through Application. See [Developer Extensions](../../extensions/README.md)
for the registration API and [component configuration](../../runtime_spec/COMPONENTS.md)
for profile source syntax.

| File | Responsibility |
|---|---|
| `loader.py` | Offline path discovery, explicit local-file/installed-entry loading, source checks and staged registration |
| `commands.py` | Identity inspection and idle replacement through public Application operations |
| `__init__.py` | Public discovery/loading entry points |

`discover_extensions(directory)` lists Python files without executing them.
`load_extensions(sources, workspace=...)` loads only explicit files or
`entrypoint:NAME` in the installed `fruitfly_agent.extensions` entry-point group.
Local files execute their exact hashed bytes. Duplicate sources and registration
errors publish no contributions. Python module side effects remain the extension
owner's responsibility. No network installer runs at startup.

Run loads profile declarations before validating algorithm selections. CLI source
paths resolve from the workspace; profile paths resolve from the profile file.
Configuration inspection in Lab remains pure and needs the caller-supplied
extension catalog. Experiment composition supplies this catalog, bindings and
source checks to materialization, candidate execution and activation. Container
execution rejects unsupported Python extension staging before model work.

Reload constructs a new host and validates its command group before publication.
Application requires idle state and checks the incumbent manifest before activation.
The new host shares the existing Session lease; failed startup retains the old
runtime. Successful replacement retires old contexts and resources. Local source
changes require reload; arbitrary imported dependencies are not frozen.

```bash
.venv/bin/python -m unittest tests.workflows.test_developer_extensions tests.run.test_cli
```
