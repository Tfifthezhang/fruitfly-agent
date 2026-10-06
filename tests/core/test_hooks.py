"""Hook contracts: ordering, isolation, committed active changes and cloning."""

from __future__ import annotations

import unittest

from fruitfly_agent.core.extensions.hooks import (
    AFTER_RESPONSE,
    BEFORE_REQUEST,
    BeforeRequestEvent,
    HookRegistry,
)
from fruitfly_agent.core.data_model import AssistantMessage, TextBlock, UserMessage

from tests.support.faux_provider import FauxProvider
from tests.support.loop import make_config, run_loop


class HookRegistryTests(unittest.IsolatedAsyncioTestCase):
    async def test_active_priority_and_passive_registration_do_not_collide(self) -> None:
        calls: list[str] = []
        hooks = HookRegistry()

        def active(event):
            calls.append("active")

        def passive(event):
            calls.append("passive")

        hooks.add(BEFORE_REQUEST, active, priority=200)
        hooks.on(BEFORE_REQUEST, passive)
        event = BeforeRequestEvent("", [], [], "model", 10)

        await hooks.run(BEFORE_REQUEST, event)
        self.assertEqual(["active"], calls)
        await hooks.emit(BEFORE_REQUEST, event)
        self.assertEqual(["active", "passive"], calls)

    async def test_passive_observer_receives_private_snapshot(self) -> None:
        provider = FauxProvider()
        provider.respond_text("done")
        hooks = HookRegistry()

        def mutate(snapshot):
            snapshot.model = "mutated"
            snapshot.messages.append(UserMessage(content="injected"))

        hooks.on(BEFORE_REQUEST, mutate)
        result = await run_loop(make_config(provider, hooks=hooks), "original")

        self.assertFalse(result.is_error)
        self.assertEqual("test-model", provider.calls[0]["model"])
        self.assertEqual(1, len(provider.calls[0]["messages"]))

    async def test_active_after_response_replacement_is_committed(self) -> None:
        provider = FauxProvider()
        provider.respond_text("original")
        hooks = HookRegistry()

        def rewrite(event):
            event.assistant = AssistantMessage(
                content=[TextBlock(text="rewritten")],
                stop_reason="stop",
                usage=event.assistant.usage,
            )

        hooks.add(AFTER_RESPONSE, rewrite)
        result = await run_loop(make_config(provider, hooks=hooks), "go")

        self.assertFalse(result.is_error)
        self.assertEqual("rewritten", result.messages[-1].text)

    async def test_invalid_active_return_is_discarded(self) -> None:
        provider = FauxProvider()
        provider.respond_text("done")
        hooks = HookRegistry()
        hooks.add(BEFORE_REQUEST, lambda event: "not an event")

        result = await run_loop(make_config(provider, hooks=hooks), "go")

        self.assertFalse(result.is_error)
        self.assertEqual("test-model", provider.calls[0]["model"])

    def test_clone_has_independent_registrations(self) -> None:
        hooks = HookRegistry()
        clone = hooks.clone()
        clone.on(BEFORE_REQUEST, lambda event: None)

        self.assertNotIn(BEFORE_REQUEST, hooks)
        self.assertIn(BEFORE_REQUEST, clone)


if __name__ == "__main__":
    unittest.main()
