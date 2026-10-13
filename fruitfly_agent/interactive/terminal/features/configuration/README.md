# Configuration Feature

[Up: Terminal Features](../README.md)

Use `TerminalConfigurationFrontend` as the menu entry and `configuration_handler` to bind the command flow. Public entries are exported by this feature package. Consume [interaction contracts](../../../contracts/README.md) through explicit capabilities.

| File | Responsibility |
|---|---|
| [menu.py](menu.py) | Generic configuration choices, draft review, and save confirmation |
| [command.py](command.py) | Busy feedback, menu lending, rebuild request, and new-session display |
| [model_setup.py](model_setup.py) | ModelFormIO, field/capability forms, review, and hidden secret input |

The host ConfigurationController owns choices and persistence. ModelSetupService owns validation and credential staging. Forms use explicitly supplied selection, rendering, reader, and staging operations; they do not access a menu owner's private methods. Credential values bypass readline/history and are absent from views and review text.

Saving applies to a future session. The command requests rebuild through the injected operation; Application owns replacement and cleanup. Model form inspection makes no Provider requests. Configuration writes and credential effects belong to the host and are not automatically rolled back.

Input and terminal control come from [I/O](../../io/README.md); display comes from [Rendering](../../rendering/README.md). This feature cannot import other features or Application/Session implementations. No new environment variables.

Category layout projects declared selectors and independent capabilities into rows and actions before handling input. The menu retains remembered selections and expansion state; shared I/O navigation handles arrows and numbered choices. Layout construction does not stage or save configuration.

```bash
.venv/bin/python -m unittest tests.interactive.test_terminal_configuration tests.run.test_model_setup tests.interactive.test_extensions -v
```
