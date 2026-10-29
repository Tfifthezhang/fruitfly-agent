"""Submit draft application intent through an injected host operation."""
from fruitfly_agent.interactive.contracts.commands import CommandResult
from fruitfly_agent.interactive.terminal.features.configuration.menu import TerminalConfigurationFrontend


def configuration_handler(*, configuration, busy, apply_configuration, menu_scope,
                          input_stream, output_stream, line_editor, write):
    async def handle(command):
        if command.arguments:
            return CommandResult(text="usage: /config (opens the configuration menu)\n")
        if busy():
            return CommandResult(text="finish or /cancel active work before changing config\n")
        with menu_scope():
            result = TerminalConfigurationFrontend(
                configuration(), input_stream=input_stream, output_stream=output_stream,
                line_editor=line_editor(),
            ).run_for_active_session()
        if result.start:
            if apply_configuration is None:
                return CommandResult(text="this host cannot apply configuration; draft retained\n")
            try:
                await apply_configuration()
            except (OSError, TypeError, ValueError, RuntimeError) as exc:
                return CommandResult(text=f"configuration not applied; conversation and draft retained: {exc}\n"
                    "Use /config to edit or retry.\n")
            write("\n[configuration applied; conversation retained]\n")
        return CommandResult()
    return handle
