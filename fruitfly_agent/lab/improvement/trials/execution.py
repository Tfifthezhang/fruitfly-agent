"""Execute a task-owned Core harness with injected preparation and verification."""
from __future__ import annotations

from dataclasses import dataclass
from inspect import isawaitable
from typing import Any, Callable

from fruitfly_agent.core.config import AgentLoopConfig
from fruitfly_agent.core.context import ContextPipeline, ContextReducer
from fruitfly_agent.core.data_model import AssistantMessage, UserMessage
from fruitfly_agent.core.loop import run_agent_loop
from fruitfly_agent.lab.improvement.tasks.scoring import ScoreResult
from fruitfly_agent.lab.improvement.trials import TrialOutcome


@dataclass
class PreparedTrial:
    """The preparer owns fresh tools, context, resources and verifier closures."""
    config: AgentLoopConfig
    verify: Callable[..., Any]
    start: Callable[..., Any] | None = None
    close: Callable[..., Any] | None = None
    context_pipeline: ContextPipeline | ContextReducer | None = None
    prompt: str | None = None


async def _call(operation, *args):
    if operation is None:
        return None
    result = operation(*args)
    return await result if isawaitable(result) else result


class IsolatedHarnessExecutor:
    """Benchmark/domain hosts inject preparation; all model calls use the shared budget.

    This is an in-process lifecycle boundary, not an OS sandbox. The preparer
    must provide task isolation, declared initial state and matching verifier.
    """
    def __init__(self, prepare):
        self.prepare = prepare

    async def run(self, config, case, *, signal):
        prepared = await _call(self.prepare, config, case)
        if not isinstance(prepared, PreparedTrial):
            raise ValueError("task preparation must return PreparedTrial")
        try:
            if (prepared.config.provider is not config.provider or prepared.config.model != config.model
                    or prepared.config.session is not None):
                raise ValueError("task runtime must retain the budgeted Provider/model and no production Session")
            await _call(prepared.start)
            result = await run_agent_loop(prepared.config,
                [UserMessage(content=prepared.prompt if prepared.prompt is not None else case.input)],
                signal=signal, context_pipeline=prepared.context_pipeline)
            if result.is_error or result.stop_reason == "aborted":
                raise RuntimeError("task harness failed or was aborted")
            score = await _call(prepared.verify, result, case)
            if not isinstance(score, ScoreResult):
                raise ValueError("task verifier must return ScoreResult")
            output = "\n".join(message.text for message in result.messages if isinstance(message, AssistantMessage))
            return TrialOutcome(output, score.score, score.feedback)
        finally:
            await _call(prepared.close)
