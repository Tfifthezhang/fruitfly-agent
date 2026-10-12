"""Launch an optional evaluation through the injected controller."""
from fruitfly_agent.interactive.contracts.commands import CommandResult
from fruitfly_agent.interactive.terminal.features.evaluation.menu import TerminalEvaluationFrontend


def evaluation_handler(*, controller, busy, menu_scope, input_stream, output_stream, line_editor):
    async def handle(command):
        if command.arguments:
            return CommandResult(text="usage: /eval\n")
        if busy():
            return CommandResult(text="finish or /cancel the active run before starting eval\n")
        try:
            with menu_scope():
                result = await TerminalEvaluationFrontend(
                    controller, input_stream=input_stream, output_stream=output_stream,
                    line_editor=line_editor(),
                ).run()
        except (OSError, RuntimeError, TypeError, ValueError) as exc:
            return CommandResult(text=f"could not run evaluation: {exc}\n")
        if result is None:
            return CommandResult()
        return CommandResult(text=(
            f"\n[evaluation {result.status}: {result.evaluation_id}]\n"
            f"report: {result.report_markdown}\njson: {result.report_json}\n"
        ))
    return handle
