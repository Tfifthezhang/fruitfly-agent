"""Explicit InformationSpace composition without global discovery or vendor clients."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Callable, Iterable, Sequence

from .models import InformationArtifact, InformationRef, InformationSpaceDescriptor
from .protocols import InformationReader, InformationRetriever


async def _maybe_await(value):
    if hasattr(value, "__await__"):
        return await value
    return value


@dataclass(frozen=True)
class InformationSpace:
    descriptor: InformationSpaceDescriptor
    reader: InformationReader | None = None
    retriever: InformationRetriever | None = None

    def __post_init__(self) -> None:
        if self.retriever is not None and self.retriever.space_id != self.descriptor.space_id:
            raise ValueError("retriever space_id must match its InformationSpace descriptor")


class StaticInformationReader:
    """In-memory deterministic reader used for manual seeds and tests."""

    def __init__(self, space_id: str, artifacts: Iterable[InformationArtifact] = ()) -> None:
        self.space_id = space_id
        self._artifacts: dict[str, InformationArtifact] = {}
        for artifact in artifacts:
            self.add(artifact)

    def add(self, artifact: InformationArtifact) -> None:
        if artifact.ref.space_id != self.space_id:
            raise ValueError("artifact space_id does not match reader")
        if artifact.ref.artifact_id in self._artifacts:
            raise ValueError(f"duplicate artifact id: {artifact.ref.artifact_id}")
        self._artifacts[artifact.ref.artifact_id] = artifact

    def get(self, ref: InformationRef) -> InformationArtifact | None:
        if ref.space_id != self.space_id:
            return None
        return self._artifacts.get(ref.artifact_id)

    def artifacts(self) -> Sequence[InformationArtifact]:
        return tuple(self._artifacts[key] for key in sorted(self._artifacts))


class CallbackInformationReader:
    """Adapt an injected local or external get callback without owning its client."""

    def __init__(self, callback: Callable[[InformationRef], object]) -> None:
        self._callback = callback

    async def get(self, ref: InformationRef) -> InformationArtifact | None:
        return await _maybe_await(self._callback(ref))


class CallbackInformationRetriever:
    """Adapt an injected query callback; network policy remains with the caller."""

    def __init__(self, space_id: str, callback: Callable[[object], object]) -> None:
        self.space_id = space_id
        self._callback = callback

    async def retrieve(self, query):
        return await _maybe_await(self._callback(query))


class InformationSpaceCatalog:
    def __init__(self, spaces: Iterable[InformationSpace] = ()) -> None:
        self._spaces: dict[str, InformationSpace] = {}
        for space in spaces:
            self.register(space)

    def register(self, space: InformationSpace) -> None:
        space_id = space.descriptor.space_id
        if space_id in self._spaces:
            raise ValueError(f"duplicate information space: {space_id}")
        self._spaces[space_id] = space

    def spaces(self) -> tuple[InformationSpace, ...]:
        return tuple(self._spaces[key] for key in sorted(self._spaces))

    def descriptors(self) -> tuple[InformationSpaceDescriptor, ...]:
        return tuple(space.descriptor for space in self.spaces())

    def retrievers(
        self, selected: tuple[str, ...] = (), *, scope: str | None = None
    ) -> tuple[InformationRetriever, ...]:
        allowed = set(selected)
        return tuple(
            space.retriever
            for space in self.spaces()
            if space.retriever is not None
            and (not allowed or space.descriptor.space_id in allowed)
            and (scope is None or space.descriptor.scope == scope)
        )

    def has_readers(self) -> bool:
        return any(space.reader is not None for space in self._spaces.values())

    async def get(self, ref: InformationRef) -> InformationArtifact | None:
        space = self._spaces.get(ref.space_id)
        if space is None or space.reader is None:
            return None
        try:
            return await _maybe_await(space.reader.get(ref))
        except asyncio.CancelledError:
            raise


__all__ = [
    "InformationSpace",
    "StaticInformationReader",
    "CallbackInformationReader",
    "CallbackInformationRetriever",
    "InformationSpaceCatalog",
]
