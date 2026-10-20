"""Small service contracts independent of vendors, HTTP and Agent tools."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class SearchRequest:
    query: str
    count: int = 5
    domains: tuple[str, ...] = ()
    freshness: str = "any"


@dataclass(frozen=True)
class SearchHit:
    title: str
    url: str
    snippet: str


@dataclass(frozen=True)
class SearchResponse:
    results: tuple[SearchHit, ...]
    retrieved_at: float
    cached: bool = False


@dataclass(frozen=True)
class FetchResponse:
    title: str
    text: str
    source_url: str
    final_url: str | None
    content_id: str
    retrieved_at: float
    cached: bool = False
    source_truncated: bool = False


class SearchService(Protocol):
    name: str
    max_query_chars: int
    query_description: str

    async def search(self, request: SearchRequest, *, signal: asyncio.Event | None = None) -> SearchResponse: ...


class FetchService(Protocol):
    description: str

    async def fetch(self, url: str, *, signal: asyncio.Event | None = None) -> FetchResponse: ...
