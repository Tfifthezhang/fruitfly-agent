# Configuration Feature

[Up: Terminal Features](../README.md)

Use `TerminalConfigurationFrontend` as the menu entry and `configuration_handler` to bind the command flow. Public entries are exported by this feature package. Consume [interaction contracts](../../../contracts/README.md) through explicit capabilities.

| File | Responsibility |
|---|---|
| [menu.py](menu.py) | Menu events, injected operations, draft review, and save confirmation |
| [presentation.py](presentation.py) | Pure projection of configuration snapshots into generic menu rows and stable action identities |
| [command.py](command.py) | Busy feedback, menu lending, injected configuration application and saved/active feedback |
| [forms.py](forms.py) | FormIO and shared value/field selection with distinct cancellation |
| [model_setup.py](model_setup.py) | Model fields, capability forms and review |
| [mechanism_setup.py](mechanism_setup.py) | Registration-driven guided settings, hidden credentials, per-field retry and review |

`run()` returns launch intent directly for complete configuration without reading
input or rendering a home menu. `run(configure=True)` opens the configuration
editor before startup. Missing model selection, credentials and enabled mechanism
inputs invoke injected setup services. Cancellation resets staged changes and
returns without starting a Session. Repairs and explicit edits offer Save and
start, Continue or Discard; ready synthesized defaults save without a chooser.
Read-only configuration supports review without saving. An optional
`DefaultConfiguration.restore_defaults()` capability adds **Restore default
configuration** immediately before Back in configuration. It stages a draft through
the host; apply, continue and discard choices apply. Read-only default
controllers expose review only. No permission settings page is supplied.

The host ConfigurationController owns choices and persistence. ModelSetupService owns validation and credential staging. Forms use explicitly supplied selection, rendering, reader, and staging operations; they do not access a menu owner's private methods. Credential values bypass readline/history and are absent from views and review text.

After capabilities, model setup edits host-supplied `parameters` as a complete
JSON object. Blank accepts the displayed medium effort default; `{}` requests
server defaults. Invalid values retry before reading credentials. Back returns to
protocol selection; cancellation stages nothing. Model review displays the exact
edited parameters and transport defaults. ANSI review has Next/Previous pages so
long mappings remain readable; numbered output prints the complete review.
Confirmation stages the defaults through the host. Service metadata stays in Providers.

Model setup selects a host-supplied service option, then always opens a protocol
menu before model fields. Back returns to services; `back` from text fields returns
to protocols. Per-service/protocol drafts retain edits, while new protocol choices
refresh addresses and defaults. SDK is a host-resolved constant, never a question,
and appears in review. Quit or field cancellation leaves no staged model.
The terminal does not classify vendors, map protocols to SDKs, or construct clients.

`ModelSetupService.field` refreshes protocol-dependent field defaults. The host's
protocol description warns that some models may not support the chosen protocol.
There is no model-specific capability enforcement. Protocol IDs and choices come from the host;
unavailable choices never become free-text input. Ambiguous SDK resolution reports
a configuration error without staging.

Optional `MechanismSetupService` supplies backend-neutral forms declared in
Catalog. Enabling a mechanism opens its guided setup only when settings or
credentials are missing. Complete saved or staged settings are reused directly;
disabling a mechanism retains its parameters and credentials. Expansion
offers **Set up…** even when disabled. Staging enables the configured mechanism
and resolves conflicts; cancellation preserves the original selection. Starting
a new session first repairs enabled mechanisms with missing setup information.
Hidden fields use the shared [secret reader](../../io/secret.py), also used for model keys; blank reuses an
existing value, and invalid/missing fields retry without echoing secrets.

In an active conversation, the menu returns application intent without saving.
The confirmation offers **Save and apply to this conversation**, **Continue
configuring**, and **Discard changes**. It omits unchanged prompt labels.
The command restores the chat screen, then requests the injected
`apply_configuration` operation. Application and its host own assembly, recovery,
persistence, replacement and cleanup. A missing operation or application failure
retains the draft and conversation; `/config` opens them for editing or retry.
Success prints a short confirmation without repeating the welcome page or saved
history. Startup retains its separate save-before-start behavior. Model form
inspection makes no Provider requests. No algorithm admission or lifecycle checks
are implemented in the menu.

Input and terminal control come from [I/O](../../io/README.md); display comes from [Rendering](../../rendering/README.md). This feature cannot import other features or Application/Session implementations. No new environment variables.

## Browse components

Component rows show a checkbox, a name, and the selected implementation when a
choice group has multiple options. Enabled/Disabled text is omitted. A fixed
bottom area shows only the focused row's title and concise explanation, using
registration-owned descriptions. Focus and selection remain independent.

| Structure | Enter | Space |
|---|---|---|
| One implementation with declared inputs or setup | Open its settings | Enable/disable through the host |
| One implementation without settings | Keep the current view | Enable/disable through the host |
| Multiple implementations | Expand/collapse inline radio choices | Enable/disable the group |
| Radio option | Select through the host | No change |
| Settings field | Edit the declared value | No change |

A settings arrow appears only when settings exist. Disabled single implementations
can be inspected without enabling them. Multiple implementations expose Settings
for the active option. A disabled group shows a selection hint rather than the
first implementation's description. Required groups cannot be disabled; reenabling
remembers the last selected algorithm. Missing setup still invokes the registered
wizard before activation. Only declared `input_parameters` are editable; internal
tuning remains in YAML. Browsing, expansion and cancellation do not stage changes.

Context uses nonselectable **Context augmentation**, **Context externalization**
and **Context reduction** headings from `display_section`/`context_phase`. Skills,
file memory, knowledge and HTTP remain peers under augmentation. Back returns from
settings, collapses an expanded group, or returns to configuration. Stable action
identities retain focus after selection, editing and snapshot refreshes. Draft
changes show Modified until applied or discarded.

Lab owns descriptions, groups and field declarations. Run projects them into
renderer-neutral configuration contracts. `presentation.py` consumes those values
without a controller, file access or mutations. `menu.py` owns browsing state and
routes confirmed operations to the injected controller. The shared
[I/O renderer](../../io/README.md) knows only generic rows and `MenuHelp`, not
component IDs or Catalog. No new registry, configuration fields or runtime state
are introduced. Registered source/guide paths remain metadata but are not shown
in daily menus; there is no Details row or configuration-path banner.

The bottom explanation is separate from inline values, validation errors and
save feedback. It uses reduced emphasis, not a smaller terminal font. Small ANSI
screens scroll the list and reduce padding; numbered fallback prints complete
focused explanations. NO_COLOR preserves symbols and hierarchy. Declared-field
input retains its menu and focus; Enter submits, blank preserves the value and
Esc or `/cancel` cancels. The host remains authoritative. Prompt previews and
model/default reviews retain their complete text and pagination.

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
