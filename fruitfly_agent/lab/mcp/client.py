"""One SDK context owner per stdio service, with bounded startup and shutdown."""
from __future__ import annotations
import asyncio
import copy
import json
import os
from typing import Any
from contextlib import asynccontextmanager

from fruitfly_agent.lab.catalog.tool_providers import ToolServiceInfo
from .config import ServerConfig


class McpClient:
    def __init__(self, config: ServerConfig, environment: dict[str, str]):
        self.config, self.environment = config, dict(environment)
        self.state = 'not started'
        self.descriptors: tuple[dict[str, Any], ...] = ()
        self.server_info: dict[str, Any] = {}
        self.protocol = ''
        self._client: Any = None
        self._task: asyncio.Task | None = None
        self._ready: asyncio.Future | None = None
        self._stop = asyncio.Event()
        self._calls: set[asyncio.Task] = set()
        self._slots = asyncio.Semaphore(config.max_parallel)

    def status(self) -> ToolServiceInfo:
        return ToolServiceInfo(self.config.name, 'stdio', self.config.cwd, self.state, self.config.tools)

    async def start(self) -> None:
        if self.state == 'ready':
            return
        if self._task is not None:
            raise RuntimeError('MCP service cannot be restarted implicitly; apply configuration again')
        self._ready = asyncio.get_running_loop().create_future()
        self._ready.add_done_callback(lambda ready: ready.exception() if not ready.cancelled() else None)
        self.state = 'starting'
        self._task = asyncio.create_task(self._run(), name='mcp:' + self.config.name)
        try:
            await asyncio.shield(self._ready)
        except BaseException:
            try:
                await self.close()
            finally:
                if self._ready.done() and not self._ready.cancelled():
                    self._ready.exception()
            raise

    async def _run(self) -> None:
        try:
            import anyio
            from mcp import Client, StdioServerParameters
            from mcp.client.stdio import stdio_client
            async def message_handler(message):
                if getattr(message, 'method', '') == 'notifications/tools/list_changed':
                    self.state = 'catalog changed; apply configuration'
            params = StdioServerParameters(command=self.config.command, args=list(self.config.args),
                cwd=self.config.cwd, env=self.environment)
            # stderr is deliberately not copied into model output or Session files.
            with open(os.devnull, 'w') as diagnostics:
                with anyio.CancelScope(deadline=anyio.current_time() + self.config.startup_timeout) as startup:
                    async with Client(stdio_client(params, errlog=diagnostics),
                            read_timeout_seconds=self.config.call_timeout, message_handler=message_handler) as client:
                        self._client = client
                        cursor, seen, descriptors, size = None, set(), [], 0
                        while True:
                            page = await client.list_tools(cursor=cursor, cache_mode='refresh')
                            for tool in page.tools:
                                descriptor = tool.model_dump(mode='json', by_alias=True, exclude_none=True)
                                size += len(json.dumps(descriptor).encode('utf-8'))
                                if size > self.config.max_result_bytes:
                                    raise ValueError('MCP tool catalog exceeds configured byte budget')
                                descriptors.append(descriptor)
                            cursor = page.next_cursor
                            if cursor is None:
                                break
                            if cursor in seen:
                                raise ValueError('MCP tool pagination repeated a cursor')
                            seen.add(cursor)
                        self.descriptors = tuple(descriptors)
                        info = client.server_info
                        self.server_info = info.model_dump(mode='json', by_alias=True) if info is not None else {}
                        self.protocol = client.protocol_version
                        startup.deadline = float('inf')
                        self.state = 'ready'
                        if self._ready is not None and not self._ready.done():
                            self._ready.set_result(None)
                        await self._stop.wait()
                if startup.cancelled_caught:
                    raise TimeoutError('MCP startup deadline exceeded')
        except BaseException as exc:
            self.state = 'failed'
            if self._ready is not None and not self._ready.done():
                message = ("MCP support requires: pip install 'fruitfly-agent[mcp]'" if isinstance(exc, ImportError)
                           else 'MCP startup failed or timed out; check executable, configuration and service compatibility')
                self._ready.set_exception(RuntimeError(message))
        finally:
            self._client = None
            # Do not retain injected credential values beyond the transport lifetime.
            self.environment.clear()
            if self.state != 'failed':
                self.state = 'closed'

    async def call(self, name: str, arguments: dict[str, Any], signal: asyncio.Event | None = None) -> dict[str, Any]:
        if signal is not None and signal.is_set():
            raise asyncio.CancelledError
        if self.state != 'ready' or self._client is None:
            raise RuntimeError('MCP service is unavailable or its catalog changed; apply configuration again')
        async with self._slot(signal):
            if self.state != 'ready' or self._client is None:
                raise RuntimeError('MCP service is unavailable; apply configuration again')
            task = asyncio.create_task(self._client.call_tool(name, copy.deepcopy(arguments),
                read_timeout_seconds=self.config.call_timeout))
            self._calls.add(task)
            abort = asyncio.create_task(signal.wait()) if signal is not None else None
            try:
                watched = {task, abort} if abort is not None else {task}
                done, _ = await asyncio.wait(watched, timeout=self.config.call_timeout, return_when=asyncio.FIRST_COMPLETED)
                if abort is not None and abort in done:
                    raise asyncio.CancelledError
                if task not in done:
                    raise TimeoutError
                result = task.result()
                return result.model_dump(mode='json', by_alias=True, exclude_none=True)
            except asyncio.CancelledError:
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
                raise
            except Exception:
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
                self.state = 'failed; outcome unknown'
                raise RuntimeError('MCP call failed or timed out; effects may have occurred. Do not automatically replay.') from None
            finally:
                self._calls.discard(task)
                if abort is not None:
                    abort.cancel()
                    await asyncio.gather(abort, return_exceptions=True)

    @asynccontextmanager
    async def _slot(self, signal):
        acquire = asyncio.create_task(self._slots.acquire())
        abort = asyncio.create_task(signal.wait()) if signal is not None else None
        try:
            watched = {acquire, abort} if abort is not None else {acquire}
            done, _ = await asyncio.wait(watched, timeout=self.config.call_timeout,
                                         return_when=asyncio.FIRST_COMPLETED)
            if abort is not None and abort in done:
                raise asyncio.CancelledError
            if acquire not in done:
                raise RuntimeError('MCP queue deadline exceeded; no request was dispatched')
            await acquire
            yield
        finally:
            acquire.cancel()
            if abort is not None:
                abort.cancel()
            await asyncio.gather(*(item for item in (acquire, abort) if item is not None), return_exceptions=True)
            if not acquire.cancelled() and acquire.exception() is None and acquire.result():
                self._slots.release()

    async def close(self) -> None:
        for task in tuple(self._calls):
            task.cancel()
        if self._calls:
            await asyncio.gather(*self._calls, return_exceptions=True)
        self._stop.set()
        if self._task is not None:
            if self.state == 'starting':
                self._task.cancel()
            try:
                await asyncio.wait_for(asyncio.shield(self._task), self.config.close_timeout)
            except asyncio.CancelledError:
                if not self._task.cancelled():
                    raise
            except TimeoutError:
                self.state = 'cleanup incomplete'
                raise RuntimeError('MCP cleanup deadline exceeded; service ownership retained') from None
            if self._ready is not None and not self._ready.done():
                self._ready.cancel()
            self.environment.clear()
