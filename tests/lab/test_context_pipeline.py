"""Composable context stages and ordered overflow recovery."""

from __future__ import annotations

import unittest

from fruitfly_agent.core.data_model import (
    AgentLoopContext,
    AssistantMessage,
    CUSTOM_KIND_COMPACTION,
    ContextDecision,
    ContextItem,
    ContextSnapshot,
    CustomMessage,
    TextBlock,
    UserMessage,
)
from fruitfly_agent.core.context import (
    ContextFrame,
    ContextPipeline,
    ContextStage,
    ContextTransform,
)
from fruitfly_agent.core.loop import run_agent_loop

from tests.support.faux_provider import FauxProvider
from tests.support.loop import make_config


class _Stage:
    def __init__(self, label: str, *, available: bool = True) -> None:
        self.label = label
        self.available = available
        self.calls: list[tuple[str, int]] = []

    def estimate(self, snapshot) -> int:
        return len(snapshot.messages)

    async def check_budget(self, snapshot):
        self.calls.append(("budget", len(snapshot.messages)))
        if not self.available:
            return None
        return ContextDecision(
            messages=(
                *snapshot.messages,
                CustomMessage(kind=CUSTOM_KIND_COMPACTION, text=self.label),
            ),
            mechanism_id=self.label,
            metadata={"label": self.label},
        )

    async def react_to_overflow(self, snapshot, error):
        self.calls.append(("overflow", snapshot.overflow_attempt))
        if not self.available:
            return None
        return ContextDecision(
            messages=(
                CustomMessage(kind=CUSTOM_KIND_COMPACTION, text=self.label),
                *snapshot.messages,
            ),
            retry=True,
            mechanism_id=self.label,
        )


class _Transformer:
    def __init__(self, label: str) -> None:
        self.label = label

    def transform(self, frame: ContextFrame) -> ContextTransform:
        return ContextTransform(
            ContextFrame(
                frame.system_prompt,
                (*frame.messages, CustomMessage(kind="context", text=self.label)),
                frame.tools,
                frame.model,
                frame.max_tokens,
                frame.provenance,
            ),
            {"label": self.label},
        )


class _FailingTransformer:
    def transform(self, frame: ContextFrame) -> ContextTransform:
        raise RuntimeError("stage failed")

def _snapshot(*, attempt: int = 0) -> ContextSnapshot:
    return ContextSnapshot(
        canonical_items=(),
        messages=(UserMessage(content="task"),),
        system_prompt="",
        tools=(),
        context_window=100,
        model="test-model",
        max_tokens=10,
        trigger="overflow" if attempt else "budget",
        overflow_attempt=attempt,
    )


class ContextPipelineTests(unittest.IsolatedAsyncioTestCase):
    def test_selection_is_not_a_context_pipeline_phase(self) -> None:
        with self.assertRaisesRegex(ValueError, "unsupported context stage phase"):
            ContextStage("selection", "selection", _Transformer("select"))  # type: ignore[arg-type]

    async def test_prepare_stages_compose_in_three_stage_order_with_provenance(self) -> None:
        manager = ContextPipeline(
            (
                ContextStage("external", "externalization", _Transformer("external")),
                ContextStage("augment", "augmentation", _Transformer("augment")),
            )
        )
        event = AgentLoopContext(
            system_prompt="",
            messages=[UserMessage(content="task")],
            tools=[],
            env=None,
            session=None,
            context_window=1_000,
            max_context_recovery_attempts=6,
            model="model",
            max_tokens=10,
        )

        await manager.prepare(event)

        self.assertEqual(
            ["augment", "external"],
            [message.text for message in event.messages[1:]],
        )
        self.assertEqual(
            ["augmentation", "externalization"],
            [item.phase for item in manager.last_provenance],
        )

    async def test_prepare_stage_failure_is_isolated_and_later_stages_continue(self) -> None:
        manager = ContextPipeline(
            (
                ContextStage("broken", "augmentation", _FailingTransformer()),
                ContextStage("later", "externalization", _Transformer("later")),
            )
        )
        event = AgentLoopContext(
            system_prompt="",
            messages=[UserMessage(content="task")],
            tools=[],
            env=None,
            session=None,
            context_window=1_000,
            max_context_recovery_attempts=6,
            model="model",
            max_tokens=10,
        )

        await manager.prepare(event)

        self.assertEqual(["later"], [message.text for message in event.messages[1:]])
        self.assertEqual(("later",), tuple(item.stage_id for item in manager.last_provenance))



if __name__ == "__main__":
    unittest.main()
