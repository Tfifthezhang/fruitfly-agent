"""Bind built-in command handlers without adding branches to the input loop."""
from fruitfly_agent.interactive.contracts.commands import CommandResult
from fruitfly_agent.interactive.terminal.features.retained_state.commands import retained_handler
from fruitfly_agent.interactive.terminal.features.operations import operations_handler
from fruitfly_agent.interactive.terminal.features.configuration.command import configuration_handler
from fruitfly_agent.interactive.terminal.features.resume.command import resume_handler


def bind_commands(registry, *, bindings, configuration, status, cancel,
                  menu_scope, input_stream, output_stream, line_editor, write,
                  welcome, show_history):
    if bindings.retained_state is not None:
        for name, kind in (('memory', 'memory'), ('skills', 'skill')):
            registry.register(name, retained_handler(kind=kind, describe=bindings.retained_state,
                read=bindings.retained_document, review=bindings.retained_action),
                summary='inspect retained documents and review pending updates',
                usage='/' + name + ' [read ID|commit UPDATE|reject UPDATE' + ('|retry OPERATION' if kind == 'memory' else '') + ']')
    if bindings.operations is not None:
        registry.register('operations', operations_handler(bindings.operations),
            summary='inspect or cancel background operations', usage='/operations [cancel HANDLE]')

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
