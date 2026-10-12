"""Dispatch the optimization menu through an injected view factory."""
from fruitfly_agent.interactive.contracts.commands import CommandResult


def optimization_handler(*, frontend):
    async def handle(command):
        await frontend().run(command.arguments)
        return CommandResult()
    return handle
