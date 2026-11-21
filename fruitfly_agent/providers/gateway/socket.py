"""Private HTTP transport for an explicitly issued model relay grant."""
from __future__ import annotations

import asyncio
from contextlib import suppress
import os
from pathlib import Path
import stat
import ssl

import h11

from .relay import ModelRelay, RelayRejected


class RelaySocket:
    """Own one Unix socket and its active connections."""

    @property
    def port(self) -> int:
        if self._server is None or not self._server.sockets:
            raise RuntimeError('Model relay is not listening')
        return int(self._server.sockets[0].getsockname()[1])

    def __init__(self, path: Path, relay: ModelRelay, *, request_limit: int = 16 * 1024 * 1024,
                 header_timeout: float = 10, max_connections: int = 8,
                 listen: tuple[str, int] | None = None, tls: ssl.SSLContext | None = None):
        if listen is not None and tls is None:
            raise ValueError('Network model relay requires TLS')
        self.listen, self.tls = listen, tls
        self.path = path
        self.relay = relay
        self.request_limit = request_limit
        self.header_timeout = header_timeout
        self.max_connections = max_connections
        self._server: asyncio.Server | None = None
        self._identity: tuple[int, int] | None = None
        self._tasks: set[asyncio.Task[None]] = set()

    async def __aenter__(self) -> RelaySocket:
        parent = self.path.parent.lstat()
        if not stat.S_ISDIR(parent.st_mode) or parent.st_uid != os.getuid() or parent.st_mode & 0o077:
            raise ValueError('Model relay socket needs an owner-only directory')
        if self.path.exists() or self.path.is_symlink():
            raise FileExistsError('Model relay socket path is occupied')
        if self.listen is None:
            self._server = await asyncio.start_unix_server(self._accept, path=self.path, start_serving=False)
        else:
            self._server = await asyncio.start_server(self._accept, host=self.listen[0],
                port=self.listen[1], ssl=self.tls, ssl_handshake_timeout=self.header_timeout,
                start_serving=False)
        try:
            if self.listen is None:
                node = self.path.lstat()
                self._identity = node.st_dev, node.st_ino
                self.path.chmod(0o600)
            await self._server.start_serving()
        except BaseException:
            await self.__aexit__(None, None, None)
            raise
        return self

    async def __aexit__(self, *_exception) -> None:
        if self._server is not None:
            self._server.close()
            tasks = tuple(self._tasks)
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            await self._server.wait_closed()
            self._server = None
        with suppress(FileNotFoundError):
            node = self.path.lstat()
            if stat.S_ISSOCK(node.st_mode) and (node.st_dev, node.st_ino) == self._identity:
                self.path.unlink()

    def _accept(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        if len(self._tasks) >= self.max_connections:
            writer.close()
            return
        task = asyncio.create_task(self._handle(reader, writer))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _read(self, reader: asyncio.StreamReader, connection: h11.Connection):
        request = None
        body = bytearray()
        while True:
            event = connection.next_event()
            if event is h11.NEED_DATA:
                data = await reader.read(65536)
                if not data:
                    raise RelayRejected('Incomplete model relay request')
                connection.receive_data(data)
            elif isinstance(event, h11.Request):
                request = event
                if event.method != b'POST' or not event.target.startswith(b'/') or b'?' in event.target:
                    raise RelayRejected('Unsupported model relay request')
            elif isinstance(event, h11.Data):
                if len(body) + len(event.data) > self.request_limit:
                    raise RelayRejected('Model relay request exceeds its size limit')
                body.extend(event.data)
            elif isinstance(event, h11.EndOfMessage) and request is not None:
                return request, bytes(body)
            else:
                raise RelayRejected('Invalid model relay request')

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        connection = h11.Connection(h11.SERVER, max_incomplete_event_size=16384)

        async def send(event) -> None:
            writer.write(connection.send(event) or b'')
            await writer.drain()

        async def error(status: int) -> None:
            if connection.our_state is h11.SEND_RESPONSE:
                await send(h11.Response(status_code=status, headers=[(b'connection', b'close'),
                    (b'content-type', b'application/json')]))
                await send(h11.Data(data=b'{"error":{"message":"Model relay request failed"}}'))
                await send(h11.EndOfMessage())

        async def forward(request, body: bytes) -> None:
            auth = [value for key, value in request.headers if key == b'authorization']
            sessions = [value for key, value in request.headers if key == b'x-relay-conversation']
            if len(auth) != 1 or not auth[0].startswith(b'Bearer ') or len(sessions) > 1:
                raise RelayRejected('Invalid model relay request authorization')
            async with self.relay.stream(auth[0][7:].decode('ascii'), request.target.decode('ascii'), body,
                                         conversation=sessions[0].decode('ascii') if sessions else '') as response:
                headers = [(b'connection', b'close')]
                for name in ('content-type', 'retry-after'):
                    value = response.headers.get(name)
                    if value is not None:
                        headers.append((name.encode(), value.encode('latin-1')))
                await send(h11.Response(status_code=response.status_code, headers=headers))
                async for chunk in response.aiter_bytes():
                    if chunk:
                        await send(h11.Data(data=chunk))
                await send(h11.EndOfMessage())

        try:
            async with asyncio.timeout(self.header_timeout):
                request, body = await self._read(reader, connection)
            transfer = asyncio.create_task(forward(request, body))
            disconnected = asyncio.create_task(reader.read(1))
            try:
                await asyncio.wait((transfer, disconnected), return_when=asyncio.FIRST_COMPLETED)
                if transfer.done():
                    await transfer
            finally:
                for task in (transfer, disconnected):
                    if not task.done():
                        task.cancel()
                await asyncio.gather(transfer, disconnected, return_exceptions=True)
        except (RelayRejected, UnicodeError, h11.ProtocolError, TimeoutError):
            with suppress(OSError, h11.ProtocolError):
                await error(403)
        except Exception:
            with suppress(OSError, h11.ProtocolError):
                await error(502)
        finally:
            writer.close()
            with suppress(OSError):
                await writer.wait_closed()
