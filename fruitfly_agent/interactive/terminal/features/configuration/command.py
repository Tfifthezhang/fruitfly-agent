"""Save settings and request application through an injected host operation."""
from fruitfly_agent.interactive.contracts.commands import CommandResult
from fruitfly_agent.interactive.terminal.features.configuration.menu import TerminalConfigurationFrontend


def configuration_handler(*, configuration, status, busy, apply_configuration, menu_scope,
                          input_stream, output_stream, line_editor, write, welcome):
    async def handle(command):
        if command.arguments:
            return CommandResult(text="usage: /config (opens the configuration menu)\n")
        if busy():
            return CommandResult(text="finish or /cancel active work before changing config\n")
        with menu_scope():
            result = TerminalConfigurationFrontend(
                configuration(), input_stream=input_stream, output_stream=output_stream,
                line_editor=line_editor(), active_prompt_label=status().prompt_label,
            ).run_for_active_session()
            if result.start:
                if apply_configuration is None:
                    return CommandResult(
                        text="configuration saved; this host cannot apply settings to the current conversation\n",
                    )
                try:
                    await apply_configuration()
                except (OSError, TypeError, ValueError, RuntimeError) as exc:
                    return CommandResult(text=f"configuration saved but not applied; current conversation retained: {exc}\n")
        if result.start:
            write("\n[configuration applied; conversation retained]\n")
            welcome(status())
        elif result.saved:
            write("\n[configuration saved; active runtime unchanged]\n")
        return CommandResult()
    return handle
