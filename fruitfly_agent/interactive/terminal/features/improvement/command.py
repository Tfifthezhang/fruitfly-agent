"""Restore the chat display before publishing an improvement menu outcome."""
from fruitfly_agent.interactive.contracts.commands import CommandResult


def improvement_handler(*, frontend, menu_scope):
    async def handle(command):
        with menu_scope():
            message = await frontend().run(command.arguments)
        return CommandResult(text=message or "")
    return handle
