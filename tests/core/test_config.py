"""AgentLoopConfig normalization and composition safety."""

from __future__ import annotations

import unittest

from fruitfly_agent.core.config import AgentLoopConfig

from tests.support.faux_provider import FauxProvider
from tests.support.loop import make_tool


class ConfigTests(unittest.TestCase):
    def test_tools_are_snapshotted_as_tuple(self) -> None:
        tool, _calls = make_tool()
        source = [tool]

        config = AgentLoopConfig(provider=FauxProvider(), tools=source)
        source.clear()

        self.assertIsInstance(config.tools, tuple)
        self.assertEqual((tool,), config.tools)

    def test_duplicate_tool_names_are_rejected(self) -> None:
        first, _calls = make_tool("duplicate")
        second, _calls = make_tool("duplicate")

        with self.assertRaisesRegex(ValueError, "duplicate tool names: duplicate"):
            AgentLoopConfig(provider=FauxProvider(), tools=[first, second])

    def test_context_recovery_attempt_limit_is_positive(self) -> None:
        for invalid in (0, -1, True, 1.5):
            with self.subTest(invalid=invalid), self.assertRaisesRegex(
                ValueError, "max_context_recovery_attempts"
            ):
                AgentLoopConfig(
                    provider=FauxProvider(),
                    max_context_recovery_attempts=invalid,
                )

    def test_turn_and_tool_budgets_are_nonnegative_integers(self) -> None:
        for name in ("max_turns", "max_tool_calls_per_turn"):
            for invalid in (-1, True, 1.5):
                with self.subTest(name=name, invalid=invalid), self.assertRaisesRegex(ValueError, name):
                    AgentLoopConfig(provider=FauxProvider(), **{name: invalid})
            config = AgentLoopConfig(provider=FauxProvider(), **{name: 0})
            self.assertEqual(0, getattr(config, name))


if __name__ == "__main__":
    unittest.main()
