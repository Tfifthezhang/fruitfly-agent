"""Runtime-owned shell jobs with bounded polling and explicit cancellation."""
import asyncio
from dataclasses import replace
from uuid import uuid4

from fruitfly_agent.core.data_model import AgentToolResult, TextBlock


class CommandManager:
    def __init__(self, *, max_active=2, retained_commands=64, output_characters=12000):
        self.max_active, self.retained_commands = max_active, retained_commands
        self.output_characters = output_characters
        self.jobs = {}
        self.closed = False

    async def start_command(self, execute, context, *, wait_seconds):
        if self.closed:
            raise ValueError('command manager is closed')
        if context.signal is not None and context.signal.is_set():
            raise asyncio.CancelledError
        if sum(not job['task'].done() for job in self.jobs.values()) >= self.max_active:
            raise ValueError('active command allowance exhausted; poll or cancel an existing handle')
        while len(self.jobs) >= self.retained_commands:
            key = next((key for key, job in self.jobs.items() if job['task'].done()), None)
            if key is None:
                raise ValueError('command handle allowance exhausted')
            self.jobs.pop(key)
        handle = 'command-' + uuid4().hex
        job = {'output': '', 'task': None, 'watcher': None}
        async def output(text):
            job['output'] = text[-self.output_characters:]
        # Updates remain readable after the initiating tool call has returned.
        job['task'] = asyncio.create_task(execute(replace(context, on_update=output)))
        if context.signal is not None:
            async def watch_cancellation():
                await context.signal.wait()
                if not job['task'].done():
                    job['task'].cancel()
            job['watcher'] = asyncio.create_task(watch_cancellation())
        def finished(task):
            if not task.cancelled():
                task.exception()
            if job['watcher'] is not None:
                job['watcher'].cancel()
        job['task'].add_done_callback(finished)
        self.jobs[handle] = job
        return await self.poll(handle, wait_seconds=wait_seconds)

    async def poll(self, handle, *, wait_seconds=0):
        if handle not in self.jobs:
            raise ValueError('unknown or retired command handle')
        job = self.jobs[handle]
        task = job['task']
        if not task.done() and wait_seconds:
            await asyncio.wait((task,), timeout=wait_seconds)
        status = 'running'
        text = job['output']
        details = {'handle': handle}
        if task.done():
            if task.cancelled():
                status = 'cancelled'
            else:
                error = task.exception()
                if error is not None:
                    status, text = 'failed', str(error)
                else:
                    status = 'completed'
                    result = task.result()
                    text = '\n'.join(block.text for block in result.content if isinstance(block, TextBlock))
                    details.update(result.details or {})
        details['status'] = status
        return AgentToolResult(content=[TextBlock(text=f'{handle}: {status}\n' + text[-self.output_characters:])], details=details)

    async def cancel(self, handle):
        if handle not in self.jobs:
            raise ValueError('unknown or retired command handle')
        task = self.jobs[handle]['task']
        task.cancel()
        await self._retire((task,))
        return await self.poll(handle)

    async def _retire(self, tasks):
        if not tasks:
            return
        done, pending = await asyncio.wait(tasks, timeout=10)
        for task in done:
            if not task.cancelled():
                task.exception()
        if pending:
            raise RuntimeError('command cancellation was not confirmed')

    async def aclose(self):
        self.closed = True
        tasks = tuple(task for job in self.jobs.values() for task in (job['task'], job['watcher']) if task is not None)
        for task in tasks:
            task.cancel()
        await self._retire(tasks)
