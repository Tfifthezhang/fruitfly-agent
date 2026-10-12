"""Configure a future runtime through an injected configuration controller."""
from fruitfly_agent.interactive.contracts.commands import CommandResult
from fruitfly_agent.interactive.terminal.features.configuration.menu import TerminalConfigurationFrontend


def configuration_handler(*, configuration, status, busy, rebuild, menu_scope,
                          input_stream, output_stream, line_editor, write, welcome):
    async def handle(command):
        if command.arguments:
            return CommandResult(text="usage: /config (opens the configuration menu)\n")
        if busy():
            return CommandResult(text="finish or /cancel the active run before changing config\n")
        with menu_scope():
            result = TerminalConfigurationFrontend(
                configuration(), input_stream=input_stream, output_stream=output_stream,
                line_editor=line_editor(), active_prompt_label=status().prompt_label,
            ).run_for_active_session()
            if result.start:
                if rebuild is None:
                    return CommandResult(
                        text="configuration saved; the embedding host must open a new runtime\n",
                        should_exit=True,
                    )
                await rebuild()
        if result.start:
            write("\n[new session]\n")
            welcome(status())
        return CommandResult()
    return handle
