# Configuration Feature

[Up: Terminal Features](../README.md)

Use `TerminalConfigurationFrontend` as the menu entry and `configuration_handler` to bind the command flow. Public entries are exported by this feature package. Consume [interaction contracts](../../../contracts/README.md) through explicit capabilities.

| File | Responsibility |
|---|---|
| [menu.py](menu.py) | Generic configuration choices, draft review, and save confirmation |
| [command.py](command.py) | Busy feedback, menu lending, injected configuration application and saved/active feedback |
| [forms.py](forms.py) | FormIO and shared value/field selection with distinct cancellation |
| [model_setup.py](model_setup.py) | Model fields, capability forms and review |
| [mechanism_setup.py](mechanism_setup.py) | Registration-driven guided settings, hidden credentials, per-field retry and review |

The home menu retains Start new session, Configure and Exit. An optional
`DefaultConfiguration.restore_defaults()` capability adds **Restore default
configuration** immediately before Back in Configure. It stages a draft through
the host; save/apply, save-only and discard choices apply. Read-only default
controllers expose review only. No permission settings page is supplied.

The host ConfigurationController owns choices and persistence. ModelSetupService owns validation and credential staging. Forms use explicitly supplied selection, rendering, reader, and staging operations; they do not access a menu owner's private methods. Credential values bypass readline/history and are absent from views and review text.

Optional `MechanismSetupService` supplies backend-neutral forms declared in
Catalog. Enabling a mechanism opens its guided setup only when settings or
credentials are missing. Complete saved or staged settings are reused directly;
disabling a mechanism retains its parameters and credentials. Expansion
offers **Set up…** even when disabled. Staging enables the configured mechanism
and resolves conflicts; cancellation preserves the original selection. Starting
a new session first repairs enabled mechanisms with missing setup information.
Hidden fields use the shared [secret reader](../../io/secret.py), also used for model keys; blank reuses an
existing value, and invalid/missing fields retry without echoing secrets.

Saving persists the draft. In an active conversation, **Save and apply to this conversation** requests the injected `apply_configuration` operation; **Save only** leaves the runtime unchanged. Application owns recovery, replacement and cleanup. A missing operation reports that the host cannot apply settings; it does not exit or create a blank conversation. Application failures return a saved-but-not-applied diagnostic and retain the current conversation. Model form inspection makes no Provider requests. Configuration writes and credential effects belong to the host and are not automatically rolled back.

Input and terminal control come from [I/O](../../io/README.md); display comes from [Rendering](../../rendering/README.md). This feature cannot import other features or Application/Session implementations. No new environment variables.

Each mechanism has one readable row with a checkbox, current algorithm/state and expansion indicator. Enter expands algorithms in place; Space independently enables/disables it. Algorithms show distinguishing descriptions. **Details** expands implementation/guide paths and YAML file/profile/parameter locations without changing the configuration. Paths are hidden until requested; there is no separate configuration-location action. Multiple implementations use radio markers; a sole implementation has no redundant selector. Internal tuning and repeated enabled flags are omitted. The page identifies the configuration file/profile; per-algorithm parameter locations appear in Details. Tune other values in YAML; inspection does not reset them or open an editor.

Context uses nonselectable **Context augmentation**, **Context externalization** and **Context reduction** headings from `display_section`/`context_phase`. Skills, file memory, knowledge and HTTP are peers under augmentation. Headings consume no input indices. Back first collapses open details, then the mechanism, then returns to configuration. PageUp/PageDown pages focused references on small ANSI terminals. Focus follows the mechanism after selection; reenabling remembers the algorithm. Draft edits are marked Modified and retain the save/apply or save-only flow.

Only explicitly declared user inputs, such as paths, initial text and endpoints, remain editable. Their input retains the menu and focused field while showing live text, current values, descriptions and type/range hints. Enter submits, blank preserves the value and Esc or `/cancel` cancels. Invalid values preserve the previous value; the host remains authoritative. Expansion and inspection do not change configuration. Shared I/O styles distinguish focus, enabled and modified states; raw-key menus omit numbers, line-based input retains numbered actions, and small ANSI terminals scroll to the focus. `NO_COLOR` retains symbols and hierarchy. Layout construction does not stage or save configuration.

```bash
.venv/bin/python -m unittest tests.interactive.test_terminal_configuration tests.run.test_model_setup tests.interactive.test_extensions -v
```

Mechanism setup and ordinary parameter editing render enumerated fields through
`forms.py`. Options come from host field metadata, never a terminal-owned service
list. The selected original value remains separate from its display label;
`CANCELLED` differs from false, null and empty values. ANSI menus use arrows and
Enter; line menus use numbered options. Host validation and staging remain the
same. Model and mechanism flows depend on shared forms and I/O; neither imports
the other's helpers.
