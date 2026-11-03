"""Shared read path for independently installed information spaces."""

from __future__ import annotations

from fruitfly_agent.runtime_spec.documents import parameter_default

from .application import TextInformationApplicator
from .lexical import BudgetedPostProcessor
from .models import InformationDescriptor
from .pipeline import LatestUserQueryBuilder, InformationPipeline
from .spaces import InformationSpace, InformationSpaceCatalog


class InformationHub:
    """Register a source without coupling it to storage or another source."""

    def __init__(self, *, top_k: int | None = None, max_chars: int | None = None) -> None:
        top_k = parameter_default(__package__, 'information-context.yaml', 'settings.top_k') if top_k is None else top_k
        max_chars = parameter_default(__package__, 'information-context.yaml', 'settings.max_chars') if max_chars is None else max_chars
        self.catalog = InformationSpaceCatalog()
        self.guidance = ""
        self.query_builder = LatestUserQueryBuilder(top_k=top_k, max_chars=max_chars)
        self.pipeline = InformationPipeline(
            InformationDescriptor("information-context", capabilities=frozenset({"retrieve"})),
            self.catalog,
            BudgetedPostProcessor(),
            TextInformationApplicator(),
        )

    def register(self, space: InformationSpace) -> None:
        self.catalog.register(space)

    def add_guidance(self, text: str) -> None:
        self.guidance = f"{self.guidance}\n{text}".strip()


__all__ = ["InformationHub"]
