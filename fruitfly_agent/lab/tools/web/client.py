"""Bounded asynchronous HTTP and runtime-local successful-response caching."""
from __future__ import annotations

import asyncio
from collections import OrderedDict
from dataclasses import dataclass
import hashlib
import ipaddress
import json
import math
import socket
import time
from typing import Awaitable, Callable
from urllib.parse import urljoin, urlsplit, urlunsplit

import httpx


class WebError(RuntimeError):
    """A safe, structured error that Core marks as a failed tool result."""

    def __init__(self, code: str, message: str, *, retryable: bool = False, status: int | None = None):
        self.code, self.retryable, self.status = code, retryable, status
        super().__init__(json.dumps({"ok": False, "error": {
            "code": code, "message": message, "retryable": retryable, "status": status,
        }}, ensure_ascii=False))


@dataclass(frozen=True)
class WebConfig:
    timeout_seconds: float = 20
    max_retries: int = 1
    max_response_bytes: int = 2_000_000
    cache_ttl_seconds: float = 300
    cache_entries: int = 32
    max_redirects: int = 5

    def __post_init__(self):
        for name, low, high in (("timeout_seconds", .01, 120), ("cache_ttl_seconds", 0, 3600)):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not low <= value <= high:
                raise ValueError(f"{name} must be a finite number in [{low}, {high}]")
        for name, low, high in (("max_retries", 0, 2), ("max_response_bytes", 1, 10_000_000),
                               ("cache_entries", 0, 128), ("max_redirects", 0, 10)):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
                raise ValueError(f"{name} must be an integer in [{low}, {high}]")


def normalize_url(value: object) -> str:
    if not isinstance(value, str) or len(value) > 8192 or any(ord(c) < 33 or ord(c) == 127 for c in value):
        raise WebError("invalid_url", "Provide an HTTP(S) URL without whitespace or control characters.")
    try:
        parsed = urlsplit(value)
        port = parsed.port
        host = (parsed.hostname or "").rstrip(".").lower()
        if parsed.scheme not in {"http", "https"} or not host or parsed.username is not None or parsed.password is not None:
            raise ValueError
        if port is not None and port not in {80, 443}:
            raise ValueError
        if host == "localhost" or host.endswith((".localhost", ".local", ".internal")):
            raise ValueError
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            pass
        else:
            if not address.is_global or getattr(address, "ipv4_mapped", None) is not None:
                raise ValueError
        return urlunsplit((parsed.scheme, parsed.netloc, parsed.path or "/", parsed.query, ""))
    except (ValueError, AttributeError):
        raise WebError("invalid_url", "Only public HTTP(S) URLs on ports 80/443 without credentials are supported.") from None


async def resolve_public_host(url: str) -> None:
    parsed = urlsplit(url)
    try:
        records = await asyncio.get_running_loop().getaddrinfo(
            parsed.hostname, parsed.port or (443 if parsed.scheme == "https" else 80), type=socket.SOCK_STREAM)
    except OSError:
        raise WebError("network_error", "DNS resolution failed.", retryable=True) from None
    if not records or any(not ipaddress.ip_address(record[4][0]).is_global for record in records):
        raise WebError("blocked_url", "The destination resolves to a non-public address.")


@dataclass(frozen=True)
class WebResponse:
    url: str
    content_type: str
    encoding: str
    body: bytes
    retrieved_at: float


class WebClient:
    """Own the HTTP pool. Inject transports and URL checks for offline tests."""

    def __init__(self, config: WebConfig | None = None, *, transport: httpx.AsyncBaseTransport | None = None,
                 check_url: Callable[[str], Awaitable[None]] = resolve_public_host,
                 clock: Callable[[], float] = time.monotonic):
        self.config = config or WebConfig()
        self._http = httpx.AsyncClient(transport=transport, follow_redirects=False, trust_env=False,
                                       headers={"User-Agent": "FruitFlyAgent/0.1", "Accept-Encoding": "identity"},
                                       limits=httpx.Limits(max_connections=4, max_keepalive_connections=2))
        self._check_url, self._clock = check_url, clock
        self._cache: OrderedDict[str, tuple[float, WebResponse]] = OrderedDict()
        self._lock = asyncio.Lock()
        self._closed = False

    async def close(self):
        self._closed = True
        self._cache.clear()
        await self._http.aclose()

    def discard(self, response: WebResponse):
        """Do not retain successful HTTP responses rejected by an adapter."""
        for key, entry in tuple(self._cache.items()):
            if entry[1] is response:
                self._cache.pop(key, None)

    async def request(self, method: str, url: str, *, headers: dict | None = None, payload: dict | None = None,
                      signal: asyncio.Event | None = None, redirects: bool = False) -> tuple[WebResponse, bool]:
        if signal is not None and signal.is_set():
            raise asyncio.CancelledError
        operation = asyncio.create_task(self._bounded(method, url, headers, payload, redirects))
        cancellation = asyncio.create_task(signal.wait()) if signal is not None else None
        try:
            if cancellation is None:
                return await operation
            done, _ = await asyncio.wait((operation, cancellation), return_when=asyncio.FIRST_COMPLETED)
            if cancellation in done:
                raise asyncio.CancelledError
            return await operation
        finally:
            for task in (operation, cancellation):
                if task is not None and not task.done():
                    task.cancel()
            await asyncio.gather(*(task for task in (operation, cancellation) if task is not None), return_exceptions=True)

    async def _bounded(self, method, url, headers, payload, redirects):
        try:
            # Queueing, DNS, retries, redirects and streaming share this one deadline.
            async with asyncio.timeout(self.config.timeout_seconds):
                async with self._lock:
                    if self._closed:
                        raise WebError("closed", "The web runtime is closed.")
                    url = normalize_url(url)
                    credential_scope = hashlib.sha256(json.dumps(headers or {}, sort_keys=True).encode()).hexdigest()
                    key = json.dumps([method, url, payload, credential_scope, redirects], sort_keys=True)
                    entry = self._cache.get(key)
                    if entry is not None and self._clock() - entry[0] < self.config.cache_ttl_seconds:
                        self._cache.move_to_end(key)
                        return entry[1], True
                    self._cache.pop(key, None)
                    for attempt in range(self.config.max_retries + 1):
                        try:
                            result = await self._request(method, url, headers, payload, redirects)
                            break
                        except WebError as exc:
                            if not exc.retryable or attempt == self.config.max_retries:
                                raise
                            await asyncio.sleep(.25 * (2 ** attempt))
                    if self.config.cache_entries and self.config.cache_ttl_seconds:
                        self._cache[key] = (self._clock(), result)
                        while len(self._cache) > self.config.cache_entries:
                            self._cache.popitem(last=False)
                    return result, False
        except TimeoutError:
            raise WebError("timeout", "The total web request deadline expired.", retryable=True) from None

    async def _request(self, method, url, headers, payload, redirects):
        for hop in range(self.config.max_redirects + 1):
            await self._check_url(url)
            try:
                # Do not replay server-issued cookies between source reads.
                request_headers = {**(headers or {}), "Cookie": ""}
                async with self._http.stream(method, url, headers=request_headers, json=payload,
                                             timeout=self.config.timeout_seconds) as response:
                    status = response.status_code
                    if status in {301, 302, 303, 307, 308}:
                        if not redirects or method != "GET":
                            raise WebError("redirect_blocked", "Search API redirects are disabled.", status=status)
                        if hop == self.config.max_redirects or not response.headers.get("location"):
                            raise WebError("redirect_limit", "The redirect limit was exceeded or Location is missing.", status=status)
                        target = normalize_url(urljoin(url, response.headers["location"]))
                        if urlsplit(url).scheme == "https" and urlsplit(target).scheme != "https":
                            raise WebError("redirect_blocked", "HTTPS to HTTP redirects are disabled.")
                        url = target
                        continue
                    if status >= 400:
                        code = {401: "authentication", 402: "quota_exceeded", 403: "forbidden", 404: "not_found", 429: "rate_limit",
                                432: "quota_exceeded", 433: "quota_exceeded"}.get(status, "http_error")
                        # Never include upstream bodies, request headers or credentials in errors.
                        raise WebError(code, f"The service returned HTTP {status}.",
                                       retryable=status in {408, 429, 500, 502, 503, 504}, status=status)
                    if not 200 <= status < 300:
                        raise WebError("http_error", f"Unexpected HTTP {status}.", status=status)
                    body = bytearray()
                    async for chunk in response.aiter_bytes(chunk_size=16_384):
                        body.extend(chunk)
                        if len(body) > self.config.max_response_bytes:
                            raise WebError("response_too_large", "The response exceeds the configured byte limit; fetch a smaller resource.")
                    return WebResponse(url, response.headers.get("content-type", "").lower(),
                                       response.encoding or "utf-8", bytes(body), time.time())
            except httpx.TimeoutException:
                raise WebError("timeout", "The HTTP connection stalled.", retryable=True) from None
            except httpx.HTTPError:
                raise WebError("network_error", "The HTTP connection failed.", retryable=True) from None
        raise WebError("redirect_limit", "The redirect limit was exceeded.")


__all__ = ["WebClient", "WebConfig", "WebError", "WebResponse", "normalize_url"]
