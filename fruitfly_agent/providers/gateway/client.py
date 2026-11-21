"""Send scoped SDK requests over a Unix socket without changing model identity."""
from __future__ import annotations

from pathlib import Path
import ssl
from urllib.parse import urlsplit

import httpx


class RelayTransport(httpx.AsyncBaseTransport):
    """Replace network routing and credentials for one explicitly bound model route."""

    def __init__(self, path: Path, *, upstream_url: str, route: str, grant: str,
                 conversation_header: str | None = None,
                 network_url: str | None = None, tls: ssl.SSLContext | None = None):
        self._origin = 'http://localhost'
        if network_url is not None:
            url = urlsplit(network_url)
            if (url.scheme != 'https' or not url.hostname or url.username or url.password
                    or url.path not in ('', '/') or url.query or url.fragment or tls is None
                    or tls.verify_mode != ssl.CERT_REQUIRED or not tls.check_hostname):
                raise ValueError('Network model relay requires verified HTTPS')
            self._origin = network_url.rstrip('/')
            self._transport = httpx.AsyncHTTPTransport(verify=tls, retries=0)
        else:
            self._transport = httpx.AsyncHTTPTransport(uds=str(path), retries=0)
        self._target = httpx.URL(upstream_url.rstrip('/') + route)
        self._route = route
        self._grant = grant
        self._conversation_header = conversation_header

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        if request.method != 'POST' or request.url != self._target:
            raise httpx.UnsupportedProtocol('Request is outside the model relay route', request=request)
        headers = {'Authorization': 'Bearer ' + self._grant, 'Content-Type': 'application/json'}
        session = request.headers.get(self._conversation_header) if self._conversation_header else None
        if session:
            headers['x-relay-conversation'] = session
        redirected = httpx.Request('POST', self._origin + self._route, headers=headers,
                                   content=await request.aread(), extensions=request.extensions)
        return await self._transport.handle_async_request(redirected)

    async def aclose(self) -> None:
        await self._transport.aclose()
