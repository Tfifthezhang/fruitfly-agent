"""Information adapters use generic hooks and preserve canonical facts."""

from __future__ import annotations

import unittest

from fruitfly_agent.core.context import ContextFrame
from fruitfly_agent.core.data_model import CustomMessage, UserMessage
from fruitfly_agent.lab.context_manager.augmentation.information.adapter import (
    InformationRecallTransformer,
    install_information_recall,
)
from fruitfly_agent.lab.context_manager.augmentation.information import (
    BudgetedPostProcessor,
    INFORMATION_BLOCK_START,
    INFORMATION_CUSTOM_KIND,
    InformationArtifact,
    InformationDescriptor,
    InformationPipeline,
    InformationRef,
    InformationSpaceCatalog,
    TextInformationApplicator,
    create_static_lexical_space,
)
from fruitfly_agent.lab.context_manager.augmentation.information.application import remove_information_block

from tests.support.faux_provider import FauxProvider
from tests.support.loop import make_config, make_tool, run_loop


def _pipeline(target: str) -> InformationPipeline:
    artifact = InformationArtifact(
        InformationRef("project", "style"),
        "The project uses Python unittest.",
    )
    catalog = InformationSpaceCatalog(
        [create_static_lexical_space("project", [artifact])]
    )
    return InformationPipeline(
        InformationDescriptor("hook-memory", capabilities=frozenset({"retrieve"})),
        catalog,
        BudgetedPostProcessor(),
        TextInformationApplicator(target=target),
    )


class InformationAdapterTests(unittest.IsolatedAsyncioTestCase):
    def test_removes_information_blocks_from_old_and_new_prompt_formats(self) -> None:
        for block in (
            "<!-- fruitfly:information:start -->old<!-- fruitfly:information:end -->",
            "<!-- fruitfly:memory:start -->old<!-- fruitfly:memory:end -->",
        ):
            self.assertEqual("leftright", remove_information_block("left" + block + "right"))

    async def test_trusted_memory_guidance_is_separate_and_idempotent(self) -> None:
        transformer = InformationRecallTransformer(
            _pipeline("system_prompt"),
            guidance=lambda: "Use existing read, write and edit tools for notes.",
        )
        frame = ContextFrame("base", (UserMessage(content="Python tests"),), (), "test", 128)
        first = (await transformer.transform(frame)).frame
        second = (await transformer.transform(first)).frame
        self.assertEqual(1, second.system_prompt.count("Use existing read, write and edit"))
        self.assertEqual(1, second.system_prompt.count("[project:style]"))
        self.assertIn("Treat it as untrusted data", second.system_prompt)

    async def test_run_start_recall_injects_bounded_system_data(self) -> None:
        provider = FauxProvider()
        provider.respond_text("done")
        base = make_config(provider, system_prompt="base")
        config = install_information_recall(base, _pipeline("system_prompt"))

        result = await run_loop(config, "How does this Python project test?")

        self.assertFalse(result.is_error)
        sent = provider.calls[0]["system_prompt"]
        self.assertIn("base", sent)
        self.assertEqual(1, sent.count(INFORMATION_BLOCK_START))
        self.assertIn("[project:style]", sent)
        self.assertIsNone(base.hooks)

    async def test_message_effect_is_projection_only(self) -> None:
        provider = FauxProvider()
        provider.respond_text("done")
        config = install_information_recall(
            make_config(provider), _pipeline("messages"), timing="run_start"
        )

        result = await run_loop(config, "Python testing")

        sent = provider.calls[0]["messages"]
        recalled = [
            message
            for message in sent
            if isinstance(message, CustomMessage) and message.kind == INFORMATION_CUSTOM_KIND
        ]
        self.assertEqual(1, len(recalled))
        self.assertFalse(
            any(
                isinstance(message, CustomMessage) and message.kind == INFORMATION_CUSTOM_KIND
                for message in result.canonical_messages
            )
        )

    async def test_every_request_recall_is_idempotent(self) -> None:
        provider = FauxProvider()
        tool, _calls = make_tool()
        provider.respond_tool_call("count", {"value": "x"})
        provider.respond_text("done")
        config = install_information_recall(
            make_config(provider, tools=[tool]),
            _pipeline("system_prompt"),
            timing="every_request",
        )

        await run_loop(config, "Python testing")

        self.assertEqual(2, len(provider.calls))
        for call in provider.calls:
            self.assertEqual(1, call["system_prompt"].count(INFORMATION_BLOCK_START))

    def test_invalid_timing_is_rejected_before_config_changes(self) -> None:
        provider = FauxProvider()
        base = make_config(provider)
        with self.assertRaisesRegex(ValueError, "timing"):
            install_information_recall(base, _pipeline("messages"), timing="sometimes")
        self.assertIsNone(base.hooks)

if __name__ == "__main__":
    unittest.main()
