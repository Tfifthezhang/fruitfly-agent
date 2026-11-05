"""No model work or implementation dispatch in retained document commands."""
from fruitfly_agent.interactive.contracts.commands import CommandResult
from .views import render_state


def retained_handler(*, kind, describe, read, review):
    async def execute(command):
        args = command.arguments
        try:
            if not args:
                return CommandResult(text=render_state(describe(kind)))
            if len(args) == 2 and args[0] == 'read':
                return CommandResult(text=read(kind, args[1]) + '\n')
            if len(args) == 2 and (args[0] in {'commit', 'reject'} or (kind == 'memory' and args[0] == 'retry')):
                status = await review(args[1], args[0])
                return CommandResult(text='Retained update ' + status + '.\n')
        except (ValueError, RuntimeError, StopIteration) as exc:
            return CommandResult(text='Retained state: ' + str(exc) + '\n')
        retry = '|retry OPERATION' if kind == 'memory' else ''
        return CommandResult(text='usage: /' + command.name + ' [read ID|commit UPDATE|reject UPDATE' + retry + ']\n')
    return execute
