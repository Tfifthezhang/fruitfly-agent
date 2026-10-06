"""Deterministic lexical retrieval and stable budgeted post-processing."""

from __future__ import annotations

import re
import time
from typing import Sequence

from .models import InformationArtifact, InformationHit, InformationQuery, InformationSpaceDescriptor
from .protocols import InformationArtifactSource
from .spaces import InformationSpace, StaticInformationReader, _maybe_await

_TOKEN_RE = re.compile(r"[A-Za-z0-9_]+|[\u3400-\u9fff]")


def _tokens(text: str) -> set[str]:
    return {token.casefold() for token in _TOKEN_RE.findall(text)}


class LexicalRetriever:
    def __init__(self, space_id: str, source: InformationArtifactSource) -> None:
        self.space_id = space_id
        self._source = source

    async def retrieve(self, query: InformationQuery) -> Sequence[InformationHit]:
        if query.space_ids and self.space_id not in query.space_ids:
            return ()
        query_text = query.text.casefold().strip()
        query_tokens = _tokens(query_text)
        hits: list[InformationHit] = []
        for artifact in await _maybe_await(self._source.artifacts()):
            if artifact.ref.space_id != self.space_id:
                continue
            text = artifact.text.casefold()
            overlap = len(query_tokens & _tokens(text))
            lexical = overlap / max(1, len(query_tokens))
            substring = 1.0 if query_text in text else 0.0
            score = lexical + substring
            if score <= 0:
                continue
            hits.append(
                InformationHit(
                    artifact=artifact,
                    score=score,
                    scores={"lexical": lexical, "substring": substring},
                )
            )
        return tuple(hits)


class BudgetedPostProcessor:
    """Dedupe, rank, and select with deterministic reference tie-breaking."""

    def process(self, query: InformationQuery, hits: Sequence[InformationHit]) -> Sequence[InformationHit]:
        ordered = sorted(
            hits,
            key=lambda hit: (
                -hit.score,
                hit.artifact.ref.space_id,
                hit.artifact.ref.artifact_id,
            ),
        )
        selected: list[InformationHit] = []
        seen = set()
        used_chars = 0
        now = time.time()
        for hit in ordered:
            ref = hit.artifact.ref
            if ref in seen:
                continue
            if hit.artifact.sensitive and not query.filters.get("include_sensitive"):
                continue
            if hit.artifact.valid_from is not None and hit.artifact.valid_from > now:
                continue
            if hit.artifact.valid_until is not None and hit.artifact.valid_until <= now:
                continue
            text_size = len(hit.artifact.text)
            if selected and used_chars + text_size > query.max_chars:
                continue
            selected.append(hit)
            seen.add(ref)
            used_chars += text_size
            if len(selected) >= query.top_k:
                break
        return tuple(selected)


def create_static_lexical_space(
    space_id: str,
    artifacts: Sequence[InformationArtifact],
    *,
    label: str = "",
    scope: str = "workspace",
) -> InformationSpace:
    reader = StaticInformationReader(space_id, artifacts)
    return InformationSpace(
        descriptor=InformationSpaceDescriptor(
            space_id=space_id,
            label=label,
            scope=scope,
            persistent=False,
            writable=False,
        ),
        reader=reader,
        retriever=LexicalRetriever(space_id, reader),
    )


__all__ = ["LexicalRetriever", "BudgetedPostProcessor", "create_static_lexical_space"]
