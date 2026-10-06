"""Project selected information into model context through Core stages or hooks."""

from __future__ import annotations

import dataclasses
from types import SimpleNamespace
from typing import Callable, Literal

from fruitfly_agent.core.config import AgentLoopConfig
from fruitfly_agent.core.data_model import CustomMessage
from fruitfly_agent.core.extensions.hooks import (
    BEFORE_REQUEST,
    BEFORE_RUN,
    HookRegistry,
)
from fruitfly_agent.lab.context_manager.augmentation.information.application import (
    INFORMATION_BLOCK_END,
    INFORMATION_BLOCK_START,
    INFORMATION_CUSTOM_KIND,
    remove_information_block,
)
from fruitfly_agent.lab.context_manager.augmentation.information.models import InformationEffect
from fruitfly_agent.lab.context_manager.augmentation.information.pipeline import LatestUserQueryBuilder, InformationPipeline
from fruitfly_agent.lab.context_manager.augmentation.information.protocols import InformationQueryBuilder
from fruitfly_agent.core.context import ContextFrame, ContextTransform

InformationRecallTiming = Literal["run_start", "every_request"]
_GUIDANCE_START = "<!-- fruitfly:information-guidance:start -->"
_GUIDANCE_END = "<!-- fruitfly:information-guidance:end -->"


def _remove_guidance(prompt: str) -> str:
    start = prompt.find(_GUIDANCE_START)
    end = prompt.find(_GUIDANCE_END, start + len(_GUIDANCE_START))
    if start < 0 or end < 0:
        return prompt
    return (prompt[:start] + prompt[end + len(_GUIDANCE_END):]).strip()


def _without_previous_message(messages):
    return [
        message
        for message in messages
        if not (isinstance(message, CustomMessage) and message.kind == INFORMATION_CUSTOM_KIND)
    ]


def _apply_effect(event, effect: InformationEffect | None):
    event.system_prompt = remove_information_block(event.system_prompt)
    event.messages = _without_previous_message(event.messages)
    if effect is None:
        return event
    if effect.target == "system_prompt":
        block = f"{INFORMATION_BLOCK_START}\n{effect.content}\n{INFORMATION_BLOCK_END}"
        event.system_prompt = (
            f"{event.system_prompt}\n\n{block}" if event.system_prompt else block
        )
    elif effect.target == "messages":
        event.messages = [
            *event.messages,
            CustomMessage(kind=INFORMATION_CUSTOM_KIND, text=effect.content),
        ]
    else:
        raise ValueError("tool InformationEffect cannot be committed by a recall hook")
    return event


class InformationRecallTransformer:
    """Augmentation-stage adapter for one configured Information pipeline."""

    def __init__(
        self,
        pipeline: InformationPipeline,
        *,
        query_builder: InformationQueryBuilder | None = None,
        guidance: Callable[[], str] | None = None,
    ) -> None:
        self.pipeline = pipeline
        self.query_builder = query_builder or LatestUserQueryBuilder()
        self.guidance = guidance

    async def transform(self, frame: ContextFrame) -> ContextTransform:
        projection = _apply_effect(
            SimpleNamespace(
                system_prompt=_remove_guidance(frame.system_prompt),
                messages=list(frame.messages),
            ),
            None,
        )
        query = self.query_builder.build(projection.messages)
        if hasattr(query, "__await__"):
            query = await query
        effect = await self.pipeline.recall(query) if query is not None else None
        projection = _apply_effect(projection, effect)
        guidance = self.guidance() if self.guidance is not None else ""
        if guidance:
            block = f"{_GUIDANCE_START}\n{guidance}\n{_GUIDANCE_END}"
            projection.system_prompt = (
                f"{projection.system_prompt}\n\n{block}"
                if projection.system_prompt else block
            )
        transformed = dataclasses.replace(
            frame,
            system_prompt=projection.system_prompt,
            messages=tuple(projection.messages),
        )
        return ContextTransform(
            transformed,
            dict(effect.metadata) if effect is not None else {"hit_count": 0},
        )


def install_information_recall(
    config: AgentLoopConfig,
    pipeline: InformationPipeline,
    *,
    query_builder: InformationQueryBuilder | None = None,
    timing: InformationRecallTiming = "run_start",
    priority: int = 100,
) -> AgentLoopConfig:
    """Return a new config with one explicit automatic recall policy."""

    if timing not in ("run_start", "every_request"):
        raise ValueError(f"unsupported information recall timing: {timing}")
    builder = query_builder or LatestUserQueryBuilder()

    async def recall(event):
        event = _apply_effect(event, None)
        query = builder.build(event.messages)
        if hasattr(query, "__await__"):
            query = await query
        if query is None:
            return event
        effect = await pipeline.recall(query)
        return _apply_effect(event, effect)

    hooks = (
        config.hooks.clone()
        if config.hooks is not None
        else HookRegistry(session=config.session)
    )
    hook_name = BEFORE_RUN if timing == "run_start" else BEFORE_REQUEST
    hooks.add(hook_name, recall, priority=priority)
    return dataclasses.replace(config, hooks=hooks)



__all__ = ["InformationRecallTiming", "InformationRecallTransformer", "install_information_recall"]
