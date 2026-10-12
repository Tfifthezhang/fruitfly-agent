"""Bind built-in command handlers without adding branches to the input loop."""
from fruitfly_agent.interactive.contracts.commands import CommandResult
from fruitfly_agent.interactive.terminal.features.configuration.command import configuration_handler
from fruitfly_agent.interactive.terminal.features.evaluation.command import evaluation_handler
from fruitfly_agent.interactive.terminal.features.optimization.command import optimization_handler
from fruitfly_agent.interactive.terminal.features.resume.command import resume_handler


def bind_commands(registry, *, bindings, configuration, evaluation, status, cancel,
                  menu_scope, input_stream, output_stream, line_editor, write,
                  welcome, show_history, optimization_frontend):
    def cancel_command(command):
        if command.arguments:
            return CommandResult(text="usage: /cancel\n")
        return CommandResult(text=(
            "cancellation requested; pending inputs cleared\n" if cancel() else "no active run\n"
        ))

    registry.register("cancel", cancel_command)
    if configuration() is not None:
        registry.register("config", configuration_handler(
            configuration=configuration, status=status, busy=bindings.busy,
            rebuild=bindings.rebuild, menu_scope=menu_scope, input_stream=input_stream,
            output_stream=output_stream, line_editor=line_editor, write=write, welcome=welcome,
        ))
    if evaluation is not None:
        registry.register("eval", evaluation_handler(
            controller=evaluation, busy=bindings.busy, menu_scope=menu_scope,
            input_stream=input_stream, output_stream=output_stream, line_editor=line_editor,
        ))
    if bindings.resume is not None:
        registry.register("resume", resume_handler(
            resume=bindings.resume, discover=bindings.discover, status=status,
            busy=bindings.busy, menu_scope=menu_scope, input_stream=input_stream,
            output_stream=output_stream, line_editor=line_editor, write=write,
            welcome=welcome, show_history=show_history,
        ))
    if optimization_frontend is not None:
        registry.register("optimize", optimization_handler(frontend=optimization_frontend))

    def candidate_command(command):
        return CommandResult(text=f"unknown command: /{command.name}; use /optimize\n")
    for name in ("candidates", "candidate"):
        registry.register(name, candidate_command)
