"""Explicit read-only Information pipeline: query, retrieve, rank and apply."""

from __future__ import annotations

import asyncio
from typing import Sequence

from fruitfly_agent.core.data_model import AgentMessage, UserMessage

from .models import (
    InformationAccessError,
    InformationDescriptor,
    InformationEffect,
    InformationQuery,
    InformationSearchResult,
)
from .protocols import InformationApplicator, InformationPostProcessor
from .spaces import InformationSpaceCatalog, _maybe_await


class LatestUserQueryBuilder:
    def __init__(
        self,
        *,
        scope: str = "workspace",
        space_ids: tuple[str, ...] = (),
        top_k: int = 5,
        max_chars: int = 4_000,
    ) -> None:
        self.scope = scope
        self.space_ids = space_ids
        self.top_k = top_k
        self.max_chars = max_chars

    def build(self, messages: Sequence[AgentMessage]) -> InformationQuery | None:
        for message in reversed(messages):
            if not isinstance(message, UserMessage):
                continue
            if isinstance(message.content, str):
                text = message.content.strip()
            else:
                text = " ".join(
                    block.text for block in message.content if hasattr(block, "text")
                ).strip()
            if text:
                return InformationQuery(
                    text=text,
                    scope=self.scope,
                    space_ids=self.space_ids,
                    top_k=self.top_k,
                    max_chars=self.max_chars,
                )
        return None


class InformationPipeline:
    def __init__(
        self,
        descriptor: InformationDescriptor,
        spaces: InformationSpaceCatalog,
        postprocessor: InformationPostProcessor,
        applicator: InformationApplicator,
    ) -> None:
        self.descriptor = descriptor
        self.spaces = spaces
        self.postprocessor = postprocessor
        self.applicator = applicator

    async def search(self, query: InformationQuery) -> InformationSearchResult:
        hits = []
        errors = []
        for retriever in self.spaces.retrievers(query.space_ids, scope=query.scope):
            try:
                found = await _maybe_await(retriever.retrieve(query))
                hits.extend(found)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                errors.append(
                    InformationAccessError(
                        space_id=retriever.space_id,
                        operation="retrieve",
                        message=f"{type(exc).__name__}: {exc}",
                    )
                )
        return InformationSearchResult(hits=tuple(hits), errors=tuple(errors))

    async def select(self, query: InformationQuery) -> InformationSearchResult:
        raw = await self.search(query)
        hits = await _maybe_await(self.postprocessor.process(query, raw.hits))
        return InformationSearchResult(hits=tuple(hits), errors=raw.errors)

    async def recall(self, query: InformationQuery) -> InformationEffect | None:
        selected = await self.select(query)
        return await _maybe_await(self.applicator.apply(query, selected.hits))


__all__ = ["LatestUserQueryBuilder", "InformationPipeline"]
