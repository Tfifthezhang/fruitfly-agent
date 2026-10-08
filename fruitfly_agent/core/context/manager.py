"""Core-owned ordering and failure isolation for request context stages."""

from __future__ import annotations

import asyncio
from dataclasses import replace
import logging
from typing import Sequence

from ..data_model import ContextDecision, ContextSnapshot
from ..data_model.runtime import AgentLoopContext
from .models import (
    ContextFrame, ContextPipelineProfile, ContextProvenance, ContextReducer,
    ContextStage, ContextTransform,
)

logger = logging.getLogger(__name__)
_PHASE_ORDER = {"augmentation": 0, "externalization": 1, "reduction": 2}


class ContextPipeline:
    """Execute augmentation → externalization → reduction."""

    def __init__(self, stages: Sequence[ContextStage] = ()) -> None:
        ordered = tuple(sorted(stages, key=lambda item: (_PHASE_ORDER[item.phase], item.order, item.stage_id)))
        ids = [item.stage_id for item in ordered]
        duplicates = sorted({item for item in ids if ids.count(item) > 1})
        if duplicates:
            raise ValueError(f"duplicate context stage ids: {', '.join(duplicates)}")
        reductions = [item for item in ordered if item.phase == "reduction"]
        if len(reductions) > 1:
            raise ValueError("context pipeline allows one composite reduction stage")
        self.stages = ordered
        self.prepare_stages = tuple(item for item in ordered if item.phase != "reduction")
        self.reduction_stage = reductions[0] if reductions else None
        self.profile = ContextPipelineProfile.from_stages(ordered)
        self.last_provenance: tuple[ContextProvenance, ...] = ()

    async def prepare(self, ctx: AgentLoopContext) -> None:
        frame = ContextFrame(
            ctx.system_prompt, tuple(ctx.messages), tuple(ctx.tools), ctx.model, ctx.max_tokens
        )
        for stage in self.prepare_stages:
            try:
                candidate = stage.mechanism.transform(frame)
                if hasattr(candidate, "__await__"):
                    candidate = await candidate
                if candidate is None:
                    continue
                metadata = {}
                if isinstance(candidate, ContextTransform):
                    metadata = dict(candidate.metadata)
                    candidate = candidate.frame
                if not isinstance(candidate, ContextFrame):
                    raise TypeError(
                        f"context stage returned {type(candidate).__name__}; "
                        "expected ContextFrame, ContextTransform, or None"
                    )
                frame = replace(
                    candidate,
                    provenance=(*frame.provenance, ContextProvenance(stage.stage_id, stage.phase, metadata)),
                )
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning("context stage %s failed (isolated): %s", stage.stage_id, exc)
        self.last_provenance = frame.provenance
        ctx.system_prompt = frame.system_prompt
        ctx.messages[:] = frame.messages
        ctx.tools[:] = frame.tools
        ctx.model = frame.model
        ctx.max_tokens = frame.max_tokens

    @property
    def estimate_source(self) -> str:
        stage = self.reduction_stage
        if stage is None:
            return ""
        return f"{stage.stage_id}: {getattr(stage.mechanism, 'estimate_source', 'stage estimator')}"

    def estimate(self, snapshot: ContextSnapshot) -> int:
        reduction = self._reduction()
        return reduction.estimate(snapshot) if reduction is not None else 0

    async def check_budget(self, snapshot: ContextSnapshot) -> ContextDecision | None:
        reduction = self._reduction()
        return None if reduction is None else await reduction.check_budget(snapshot)

    async def react_to_overflow(
        self, snapshot: ContextSnapshot, error: Exception
    ) -> ContextDecision | None:
        reduction = self._reduction()
        return None if reduction is None else await reduction.react_to_overflow(snapshot, error)

    def _reduction(self) -> ContextReducer | None:
        if self.reduction_stage is None:
            return None
        mechanism = self.reduction_stage.mechanism
        assert isinstance(mechanism, ContextReducer)
        return mechanism


__all__ = ["ContextPipeline"]
