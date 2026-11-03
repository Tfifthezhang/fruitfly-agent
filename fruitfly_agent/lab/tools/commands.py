"""Shell result adaptation over the shared runtime-owned operation service."""
from dataclasses import replace
from fruitfly_agent.runtime_spec.documents import parameter_default

from fruitfly_agent.core.data_model import AgentToolResult, TextBlock
from .managed import ManagedOperations

DEFAULT_MAX_ACTIVE = parameter_default(__package__, 'bash-tool.yaml', 'settings.max_active_commands')
DEFAULT_RETAINED_COMMANDS = parameter_default(__package__, 'bash-tool.yaml', 'settings.retained_commands')


class CommandManager:
    def __init__(self, *, max_active=None, retained_commands=None, output_characters=None):
        max_active = parameter_default(__package__, 'bash-tool.yaml', 'settings.max_active_commands') if max_active is None else max_active
        retained_commands = parameter_default(__package__, 'bash-tool.yaml', 'settings.retained_commands') if retained_commands is None else retained_commands
        output_characters = parameter_default(__package__, 'bash-tool.yaml', 'settings.output_characters') if output_characters is None else output_characters
        self.max_active, self.retained_commands, self.output_characters = max_active, retained_commands, output_characters
        self.operations = ManagedOperations(max_active=max_active, retained=retained_commands, output_characters=output_characters)

    async def start_command(self, execute, context, *, wait_seconds):
        async def work(update):
            return await execute(replace(context, on_update=update))
        handle = await self.operations.submit(work, signal=context.signal, is_error=lambda result: result.is_error)
        return await self.poll(handle, wait_seconds=wait_seconds)

    async def poll(self, handle, *, wait_seconds=0):
        job = await self.operations.wait(handle, wait_seconds)
        task = job['task']
        status = self.operations.status(handle)
        text = job['output']
        details = {'handle': handle, 'elapsed_seconds': status.elapsed_seconds}
        state = 'completed' if status.state == 'succeeded' else status.state
        if task.done() and not task.cancelled():
            error = task.exception()
            if error is not None:
                text = str(error)
            else:
                result = task.result()
                text = '\n'.join(block.text for block in result.content if isinstance(block, TextBlock))
                details.update(result.details)
        details['status'] = state
        return AgentToolResult(content=[TextBlock(f'{handle}: {state}\n' + text[-self.output_characters:])],
            details=details, is_error=status.state in {'failed', 'cancelled', 'cleanup_unconfirmed'})

    async def cancel(self, handle):
        await self.operations.cancel(handle)
        return await self.poll(handle)

    async def aclose(self):
        await self.operations.close()

    async def close(self):
        await self.aclose()
