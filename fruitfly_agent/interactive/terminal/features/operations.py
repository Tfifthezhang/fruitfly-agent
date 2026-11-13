"""Registered background-operation inspection through an injected capability."""
from fruitfly_agent.interactive.contracts.commands import CommandResult
from fruitfly_agent.interactive.terminal.io.text import safe_terminal_text


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
        return CommandResult(text=('\n'.join(f'{v.handle} · {v.state} · {v.elapsed_seconds:.1f}s' +
            ('\n  ' + safe_terminal_text(v.description) if v.description else '') +
            ''.join('\n    ' + safe_terminal_text(line) for line in v.recent_output.splitlines()[-3:]) for v in values)
            if values else 'No background operations.') + '\n')
    return execute
