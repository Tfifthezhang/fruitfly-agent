"""No model work or implementation dispatch in retained document commands."""
from fruitfly_agent.interactive.contracts.commands import CommandResult
from .views import render_state


def retained_handler(*, kind, describe, read, review, run=None):
    async def execute(command):
        args = command.arguments
        try:
            if not args:
                return CommandResult(text=render_state(describe(kind), kind=kind))
            if kind == 'memory' and len(args) == 1 and args[0] == 'details':
                return CommandResult(text=render_state(describe(kind), kind=kind, detailed=True))
            if kind == 'memory' and len(args) in {1, 2} and args[0] == 'run' and run is not None:
                status = await run(kind, args[1] if len(args) == 2 else None)
                return CommandResult(text='Memory maintenance ' + status + '.\n')
            if len(args) == 2 and args[0] == 'read':
                return CommandResult(text=read(kind, args[1]) + '\n')
            if len(args) == 2 and (args[0] in {'commit', 'reject'} or (kind == 'memory' and args[0] in {'retry', 'import', 'discard'})):
                status = await review(args[1], args[0])
                return CommandResult(text='Retained update ' + status + '.\n')
        except (ValueError, RuntimeError, StopIteration) as exc:
            return CommandResult(text='Retained state: ' + str(exc) + '\n')
        retry = '|run [OPERATION]|details|retry OPERATION|discard OPERATION|import WORKSPACE' if kind == 'memory' else ''
        return CommandResult(text='usage: /' + command.name + ' [' + retry.lstrip('|') + ('|' if retry else '') + 'read ID|commit UPDATE|reject UPDATE]\n')
    return execute
