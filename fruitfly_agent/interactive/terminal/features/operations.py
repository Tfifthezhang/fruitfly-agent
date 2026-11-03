"""Registered background-operation inspection through an injected capability."""
from fruitfly_agent.interactive.contracts.commands import CommandResult


def operations_handler(query):
    async def execute(command):
        service = query()
        if service is None:
            return CommandResult(text='Background operations are unavailable.\n')
        arguments = command.arguments
        if arguments:
            if len(arguments) != 2 or arguments[0] != 'cancel':
                return CommandResult(text='usage: /operations [cancel HANDLE]\n')
            try:
                value = await service.cancel(arguments[1])
            except ValueError as exc:
                return CommandResult(text=f'Could not cancel background operation: {exc}\n')
            return CommandResult(text=f'{value.handle}: {value.state}\n')
        values = service.statuses()
        return CommandResult(text=('\n'.join(f'{v.handle} · {v.state} · {v.elapsed_seconds:.1f}s' for v in values)
            if values else 'No background operations.') + '\n')
    return execute
