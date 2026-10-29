"""Bind built-in command handlers without adding branches to the input loop."""
from fruitfly_agent.interactive.contracts.commands import CommandResult
from fruitfly_agent.interactive.terminal.features.configuration.command import configuration_handler
from fruitfly_agent.interactive.terminal.features.improvement.command import improvement_handler
from fruitfly_agent.interactive.terminal.features.resume.command import resume_handler


def bind_commands(registry, *, bindings, configuration, status, cancel,
                  menu_scope, input_stream, output_stream, line_editor, write,
                  welcome, show_history, improvement_frontend):
    def cancel_command(command):
        if command.arguments:
            return CommandResult(text="usage: /cancel\n")
        return CommandResult(text=(
            "cancellation requested; pending inputs cleared\n" if cancel() else "no active run\n"
        ))

    registry.register("cancel", cancel_command, summary='cooperatively stop the active run')
    if configuration() is not None:
        registry.register("config", configuration_handler(
            configuration=configuration, busy=bindings.busy,
            apply_configuration=bindings.apply_configuration, menu_scope=menu_scope, input_stream=input_stream,
            output_stream=output_stream, line_editor=line_editor, write=write,
        ), summary='open the model and mechanism selection menu')
    if bindings.resume is not None:
        registry.register("resume", resume_handler(
            resume=bindings.resume, discover=bindings.discover, status=status,
            busy=bindings.busy, menu_scope=menu_scope, input_stream=input_stream,
            output_stream=output_stream, line_editor=line_editor, write=write,
            welcome=welcome, show_history=show_history,
        ), summary='continue saved history using current configuration', usage='/resume [PATH]')
    if improvement_frontend is not None:
        registry.register("improvement", improvement_handler(frontend=improvement_frontend, menu_scope=menu_scope),
            summary='run component improvement or review candidates', usage='/improvement [TEXT]')

    def candidate_command(command):
        return CommandResult(text=f"unknown command: /{command.name}; use /improvement\n")
    for name in ("candidates", "candidate"):
        registry.register(name, candidate_command, discoverable=False)
