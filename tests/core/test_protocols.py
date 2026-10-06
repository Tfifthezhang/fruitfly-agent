"""Structural checks for Core seam protocols (Provider / ContextReducer /
SessionLike).

Everything here is offline: the AnthropicProvider instance is constructed
against a localhost base_url and only inspected — no request is ever made.
"""

from __future__ import annotations

import unittest

from fruitfly_agent.core.data_model import (
    AgentLoopContext,
    ContextDecision,
    ProviderView,
)
from fruitfly_agent.core.model_stream import AssistantMessageEventStream
from fruitfly_agent.core.context import ContextReducer
from fruitfly_agent.core.extensions.protocols import (
    Provider,
    SessionLike,
)
from fruitfly_agent.core.session import Session
from fruitfly_agent.providers.anthropic import AnthropicProvider

from tests.support.faux_provider import FauxProvider


class _HandRolledCompactor:
    def estimate(self, ctx):
        return 0

    async def check_budget(self, ctx):
        return None

    async def react_to_overflow(self, ctx, error):
        return ContextDecision(retry=True, mechanism_id="test")


class ProtocolTests(unittest.TestCase):
    def test_anthropic_provider_satisfies_provider(self) -> None:
        provider = AnthropicProvider(
            api_key="x", model="m", base_url="http://localhost"
        )
        self.assertIsInstance(provider, Provider)
        self.assertTrue(callable(provider))
        stream = provider(
            ProviderView(system_prompt="", messages=[], tools=[], model="m"),
            signal=None,
        )
        self.assertIsInstance(stream, AssistantMessageEventStream)

    def test_faux_provider_satisfies_provider(self) -> None:
        self.assertIsInstance(FauxProvider(), Provider)

    def test_hand_rolled_compactor_satisfies_compactor_like(self) -> None:
        self.assertIsInstance(_HandRolledCompactor(), ContextReducer)

    def test_concrete_session_satisfies_session_like(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            session = Session(tmp + "/session.jsonl")
            try:
                self.assertIsInstance(session, SessionLike)
            finally:
                session.close()


if __name__ == "__main__":
    unittest.main()
