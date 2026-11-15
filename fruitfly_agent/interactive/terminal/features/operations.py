"""Registered background-operation inspection through an injected capability."""
from collections import Counter

from fruitfly_agent.interactive.contracts.commands import CommandPanel, CommandResult, CommandSection
from fruitfly_agent.interactive.terminal.io.text import safe_terminal_text
from fruitfly_agent.interactive.terminal.rendering.formatting import format_duration
from fruitfly_agent.interactive.terminal.rendering.panels import panel_result


def operations_handler(query):
    async def execute(command):
        service = query()
        if service is None:
            return CommandResult(text='Background operations are unavailable.\n')
        arguments = command.arguments
        if arguments and arguments[0] != 'cancel':
            if len(arguments) > 2:
                return CommandResult(text='usage: /operations [HANDLE [OFFSET]|cancel HANDLE]\n')
            try:
                offset = int(arguments[1]) if len(arguments) == 2 else 0
                text = service.output(arguments[0], offset=offset)
            except ValueError as exc:
                return CommandResult(text=f'Could not read background operation: {exc}\n')
            return CommandResult(text=safe_terminal_text(text) + '\n')
        if arguments:
            if len(arguments) != 2 or arguments[0] != 'cancel':
                return CommandResult(text='usage: /operations [cancel HANDLE]\n')
            try:
                value = await service.cancel(arguments[1])
            except ValueError as exc:
                return CommandResult(text=f'Could not cancel background operation: {exc}\n')
            return CommandResult(text=f'{value.handle}: {value.state}\n')
        values = service.statuses()
        counts = Counter(value.state for value in values)
        sections = [
            CommandSection('environment', 'Counts', (('Operations', str(len(values))),)),
            CommandSection('workflow', 'Statuses',
                tuple((state, str(count)) for state, count in counts.items()) or (('States', 'none'),)),
        ]
        for index, value in enumerate(values, 1):
            rows = [('Task', value.description or 'No description supplied.'),
                    ('Handle', value.handle), ('State', value.state),
                    ('Elapsed', format_duration(value.elapsed_seconds))]
            rows.extend((f'Output {number}', line) for number, line in
                        enumerate(value.recent_output.splitlines()[-3:], 1))
            sections.append(CommandSection('tools', f'Task {index} · {value.state}', tuple(rows)))
        footer = '/operations HANDLE [OFFSET] for retained output.'
        if not values:
            footer = 'No background operations. ' + footer
        return panel_result(CommandPanel('Background operations', tuple(sections), footer))
    return execute
