"""Async projection, summary budgets and run cancellation contracts."""

from __future__ import annotations

import asyncio
from dataclasses import replace
import unittest

from fruitfly_agent.core.context import ContextFrame, ContextPipeline, ContextStage, ContextTransform
from fruitfly_agent.core.data_model import (
    AgentLoopContext, AssistantMessage, ContextItem, ContextSnapshot, TextBlock, UserMessage,
)
from fruitfly_agent.core.loop import run_agent_loop
from fruitfly_agent.core.model_stream import AssistantMessageEventStream, StreamDone
from fruitfly_agent.lab.context_manager.reduction import (
    SummarizingCompactor, SummarizingCompactorConfig,
)
from tests.support.faux_provider import FauxProvider
from tests.support.loop import make_config


class _WaitingProvider:
    def __init__(self, *, cooperative=False):
        self.started = asyncio.Event()
        self.cleaned = asyncio.Event()
        self.signals = []
        self.cooperative = cooperative

    def __call__(self, view, *, signal=None):
        self.signals.append(signal)
        async def events():
            self.started.set()
            try:
                if self.cooperative:
                    await signal.wait()
                    raise asyncio.CancelledError
                await asyncio.Event().wait()
                yield StreamDone(AssistantMessage(content=[TextBlock(text="summary")]))
            finally:
                self.cleaned.set()
        return AssistantMessageEventStream(events())


def _snapshot(signal=None):
    messages = (
        UserMessage(content="old context " + "x" * 200),
        AssistantMessage(content=[TextBlock(text="old answer")]),
        UserMessage(content="recent"),
    )
    return ContextSnapshot(
        canonical_items=tuple(ContextItem(str(i), m) for i, m in enumerate(messages)),
        messages=messages, system_prompt="", tools=(), context_window=64,
        model="offline", max_tokens=32, trigger="budget", signal=signal,
    )


def _compactors(provider, *, timeout=60):
    return (
        SummarizingCompactor(SummarizingCompactorConfig(
            reserve_tokens=0, keep_recent_tokens=1, summary_attempts=1, summary_timeout_seconds=timeout,
        ), provider),
    )


class AlgorithmContractTests(unittest.IsolatedAsyncioTestCase):
    async def test_sync_and_async_transformers_compose_with_noop(self):
        class Sync:
            def transform(self, frame):
                return replace(frame, system_prompt=frame.system_prompt + " sync")
        class Async:
            async def transform(self, frame):
                return ContextTransform(replace(frame, system_prompt=frame.system_prompt + " async"))
        class Noop:
            async def transform(self, frame):
                return None
        pipeline = ContextPipeline((
            ContextStage("sync", "augmentation", Sync(), order=1),
            ContextStage("async", "augmentation", Async(), order=2),
            ContextStage("noop", "externalization", Noop()),
        ))
        ctx = AgentLoopContext("base", [], [], None, None, 100, 6, "offline", 32)
        await pipeline.prepare(ctx)
        self.assertEqual("base sync async", ctx.system_prompt)
        self.assertEqual(["sync", "async"], [p.stage_id for p in pipeline.last_provenance])

    async def test_summary_timeout_cleans_up_stream_and_preserves_projection(self):
        provider = _WaitingProvider()
        compactor = _compactors(provider, timeout=0.01)[0]
        decision = await asyncio.wait_for(compactor.check_budget(_snapshot()), 1)
        self.assertTrue(provider.started.is_set())
        self.assertTrue(provider.cleaned.is_set())
        self.assertEqual(1, len(provider.signals))
        self.assertIsNone(decision)  # failed summary retains the projection

    async def test_summary_providers_receive_run_signal_and_cancellation_propagates(self):
        signal = asyncio.Event()
        provider = _WaitingProvider(cooperative=True)
        compactor = _compactors(provider)[0]
        task = asyncio.create_task(compactor.check_budget(_snapshot(signal)))
        await asyncio.wait_for(provider.started.wait(), 1)
        signal.set()
        with self.assertRaises(asyncio.CancelledError):
            await asyncio.wait_for(task, 1)
        self.assertIs(signal, provider.signals[0])
        self.assertTrue(provider.cleaned.is_set())

    async def test_already_cancelled_snapshot_does_not_call_summary_provider(self):
        signal = asyncio.Event()
        signal.set()
        provider = FauxProvider()
        for compactor in _compactors(provider):
            await compactor.check_budget(_snapshot(signal))
        self.assertEqual([], provider.calls)

    async def test_core_passes_signal_and_stops_before_main_provider_after_reduction(self):
        signal = asyncio.Event()
        seen = []
        class Reducer:
            def estimate(self, snapshot):
                return 1
            async def check_budget(self, snapshot):
                seen.append(snapshot.signal)
                signal.set()
                return None
            async def react_to_overflow(self, snapshot, error):
                return None
        provider = FauxProvider()
        result = await run_agent_loop(
            make_config(provider), [UserMessage(content="task")],
            signal=signal, context_pipeline=Reducer(),
        )
        self.assertEqual("aborted", result.stop_reason)
        self.assertEqual([signal], seen)
        self.assertEqual([], provider.calls)

    def test_summary_timeouts_reject_invalid_values(self):
        for config in (SummarizingCompactorConfig,):
            for value in (True, 0, -1, float("inf"), float("nan")):
                with self.subTest(config=config, value=value), self.assertRaises(ValueError):
                    config(summary_timeout_seconds=value)
