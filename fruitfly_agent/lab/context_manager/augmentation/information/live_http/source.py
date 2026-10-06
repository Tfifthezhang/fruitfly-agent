"""Live HTTPS text information source."""

from __future__ import annotations

import asyncio
import time
from typing import Callable, Sequence
from urllib.parse import quote, urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler

from ..models import InformationArtifact, InformationHit, InformationQuery, InformationRef, InformationSpaceDescriptor
from ..spaces import InformationSpace


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        raise ValueError("live information redirects are disabled")


class LiveHttpRetriever:
    """Fetch a configured HTTPS text endpoint for the current question only."""

    space_id = "live-information"

    def __init__(
        self,
        endpoint: str,
        *,
        timeout: float = 5.0,
        fetch: Callable[[str, float], str] | None = None,
    ) -> None:
        if endpoint.count("{query}") != 1 or urlsplit(endpoint).scheme != "https":
            raise ValueError("live endpoint must be HTTPS and contain one {query} placeholder")
        parsed = urlsplit(endpoint)
        if not parsed.hostname or parsed.username or parsed.password or parsed.fragment:
            raise ValueError("live endpoint needs a host and cannot contain credentials or fragments")
        self.endpoint = endpoint
        self.timeout = timeout
        self.fetch = fetch or self._fetch

    async def retrieve(self, query: InformationQuery) -> Sequence[InformationHit]:
        if query.space_ids and self.space_id not in query.space_ids:
            return ()
        url = self.endpoint.replace("{query}", quote(query.text, safe=""))
        text = await asyncio.to_thread(self.fetch, url, self.timeout)
        if not text.strip():
            return ()
        now = time.time()
        return (
            InformationHit(
                InformationArtifact(
                    ref=InformationRef(self.space_id, "current"),
                    payload=f"Live source: {url}\n{text[:4_000]}",
                    provenance={"url": url, "retrieved_at": now},
                    created_at=now,
                    updated_at=now,
                ),
                1.0,
            ),
        )

    @staticmethod
    def _fetch(url: str, timeout: float) -> str:
        opener = build_opener(_NoRedirect())
        with opener.open(Request(url, headers={"Accept": "text/plain, application/json"}), timeout=timeout) as response:
            media_type = response.headers.get_content_type()
            if media_type not in {"text/plain", "application/json"}:
                raise ValueError(f"live response must be text/plain or application/json, got {media_type}")
            data = response.read(64_001)
        if len(data) > 64_000:
            raise ValueError("live response exceeds 64 KB")
        return data.decode("utf-8", errors="replace")


def create_live_http_space(
    endpoint: str, *, timeout: float = 5.0, fetch: Callable[[str, float], str] | None = None
) -> InformationSpace:
    retriever = LiveHttpRetriever(endpoint, timeout=timeout, fetch=fetch)
    return InformationSpace(
        descriptor=InformationSpaceDescriptor(
            retriever.space_id, "Live information", external=True
        ),
        retriever=retriever,
    )
