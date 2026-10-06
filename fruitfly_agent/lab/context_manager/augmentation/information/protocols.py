"""Narrow read capabilities implemented by Lab information sources."""

from __future__ import annotations

from typing import Awaitable, Protocol, Sequence, runtime_checkable

from fruitfly_agent.core.data_model import AgentMessage

from .models import (
    InformationArtifact,
    InformationEffect,
    InformationHit,
    InformationQuery,
    InformationRef,
)


@runtime_checkable
class InformationReader(Protocol):
    def get(
        self, ref: InformationRef
    ) -> Awaitable[InformationArtifact | None] | InformationArtifact | None: ...


@runtime_checkable
class InformationArtifactSource(Protocol):
    def artifacts(
        self,
    ) -> Awaitable[Sequence[InformationArtifact]] | Sequence[InformationArtifact]: ...


@runtime_checkable
class InformationRetriever(Protocol):
    space_id: str

    def retrieve(
        self, query: InformationQuery
    ) -> Awaitable[Sequence[InformationHit]] | Sequence[InformationHit]: ...


@runtime_checkable
class InformationPostProcessor(Protocol):
    def process(
        self, query: InformationQuery, hits: Sequence[InformationHit]
    ) -> Awaitable[Sequence[InformationHit]] | Sequence[InformationHit]: ...


@runtime_checkable
class InformationApplicator(Protocol):
    def apply(
        self, query: InformationQuery, hits: Sequence[InformationHit]
    ) -> Awaitable[InformationEffect | None] | InformationEffect | None: ...


@runtime_checkable
class InformationQueryBuilder(Protocol):
    def build(
        self, messages: Sequence[AgentMessage]
    ) -> Awaitable[InformationQuery | None] | InformationQuery | None: ...


__all__ = [
    "InformationReader",
    "InformationArtifactSource",
    "InformationRetriever",
    "InformationPostProcessor",
    "InformationApplicator",
    "InformationQueryBuilder",
]
