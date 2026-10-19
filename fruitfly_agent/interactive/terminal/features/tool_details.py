"""Read retained tool events without acquiring another input reader."""

from fruitfly_agent.interactive.contracts.commands import CommandResult
from fruitfly_agent.interactive.contracts.events import ToolFinished, ToolStarted
from fruitfly_agent.interactive.terminal.io.text import safe_terminal_text
from fruitfly_agent.interactive.terminal.rendering.tools import summarize_arguments


def tool_details_handler(*, trace):
    def handle(command):
        if trace is None:
            return CommandResult(text='Tool result inspection is unavailable in this host.\n')
        if len(command.arguments) > 1:
            return CommandResult(text='usage: /tools [CALL_ID]\n')
        retained = trace(200)
        events = [event for event in retained if isinstance(event, ToolFinished)]
        if command.arguments:
            identity = command.arguments[0]
            event = next((event for event in reversed(events) if event.tool_call_id == identity), None)
            if event is None:
                return CommandResult(text='Tool result unavailable in the retained event window. Use /tools to list available results.\n')
            start = next((start for start in reversed(retained) if isinstance(start, ToolStarted)
                and start.run_id == event.run_id and start.tool_call_id == identity), None)
            arguments = f'Arguments: {summarize_arguments(start.arguments)}\n' if start is not None else ''
            text = (f'{event.description or event.tool_name} · {event.status}\n'
                    f'Tool: {event.tool_name} · Call: {event.tool_call_id}\n{arguments}\n{event.output}\n')
        else:
            rows = [f'{event.tool_call_id} · {event.description or event.tool_name} · {event.status}' for event in events]
            text = '\n'.join(rows) + '\nUse /tools CALL_ID to inspect a retained result.\n' if rows else 'No completed tool results in the retained event window.\n'
        return CommandResult(text=safe_terminal_text(text))
    return handle
