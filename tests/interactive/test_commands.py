"""Local command routing stays independent from terminal I/O."""

from __future__ import annotations

import unittest

from fruitfly_agent.interactive.commands import (
    HELP_TEXT,
    CommandResult,
    CommandRouter,
    InteractiveCommand,
    parse_command,
)
from fruitfly_agent.interactive.events import RunStarted
from fruitfly_agent.interactive.models import InteractiveMechanism, InteractiveStatus


class _Context:
    status = InteractiveStatus(
        model="offline-model",
        working_directory="/workspace",
        session_path="session.jsonl",
        message_count=2,
        tool_names=("read", "bash"),
        mechanisms=("compaction", "memory"),
        mechanism_details=(
            InteractiveMechanism("compaction", "context-manager", "Compaction", display_section="reduction"),
            InteractiveMechanism("memory", "context-manager", "File memory", display_section="augmentation"),
        ),
    )

    def __init__(self) -> None:
        self.events = [
            RunStarted(
                run_id="abcdefgh1234",
                sequence=1,
                prompt="hello",
                model="offline-model",
                message_count=1,
            )
        ]

    def trace(self, limit: int = 12):
        return self.events[-limit:]


class CommandRouterTest(unittest.TestCase):
    def setUp(self) -> None:
        self.context = _Context()
        self.router = CommandRouter()

    def test_parser_preserves_arguments_and_quit_alias(self) -> None:
        self.assertEqual(
            parse_command("/trace 5"),
            InteractiveCommand(name="trace", arguments=("5",)),
        )
        self.assertEqual(parse_command("/quit"), InteractiveCommand(name="exit"))
        self.assertIsNone(parse_command("plain prompt"))

    def test_absolute_path_is_prompt_content_not_a_command(self) -> None:
        prompt = (
            "/Users/researcher/Documents/annual-report.docx, "
            "Does this table have any obvious problems now?"
        )

        self.assertIsNone(parse_command(prompt))

    def test_builtin_commands_return_typed_results(self) -> None:
        status = self.router.execute(
            InteractiveCommand(name="status"),
            self.context,
        )
        lab = self.router.execute(InteractiveCommand(name="lab"), self.context)
        trace = self.router.execute(
            InteractiveCommand(name="trace", arguments=("1",)),
            self.context,
        )

        self.assertIn("model: offline-model", status.text)
        self.assertIn("Lab mechanisms", lab.text)
        self.assertIn("  Context Manager", lab.text)
        self.assertIn("    Reduction\n      - Compaction", lab.text)
        self.assertIn("    Augmentation\n      - File memory", lab.text)
        self.assertNotIn("Model-facing tools", lab.text)
        self.assertNotIn("  - read", lab.text)
        self.assertEqual(trace.text, "  1 run_started run=abcdefgh\n")
        self.assertFalse(status.should_exit)

    def test_lab_exposes_all_context_manager_phases(self) -> None:
        class ContextManagerContext(_Context):
            status = InteractiveStatus(
                model="offline-model",
                working_directory="/workspace",
                session_path="session.jsonl",
                message_count=0,
                tool_names=(),
                mechanisms=("information-context", "rlm-ipython"),
                mechanism_details=(
                    InteractiveMechanism(
                        "information-context",
                        "context-manager",
                        "Information context",
                        "online",
                        "context",
                        "augmentation",
                        "augmentation",
                    ),
                    InteractiveMechanism(
                        "rlm-ipython",
                        "context-manager",
                        "Programmatic Context (RLM)",
                        "online",
                        "context",
                        "externalization",
                        "externalization",
                    ),
                ),
            )

        result = self.router.execute(
            InteractiveCommand(name="lab"), ContextManagerContext()
        )

        self.assertIn("  Context Manager", result.text)
        self.assertIn("    Augmentation\n      - Information context", result.text)
        self.assertNotIn("Selection", result.text)
        self.assertIn(
            "    Externalization\n      - Programmatic Context (RLM)",
            result.text,
        )
        self.assertIn("    Reduction\n      - none", result.text)

    def test_invalid_and_unknown_commands_keep_existing_messages(self) -> None:
        invalid = self.router.execute(
            InteractiveCommand(name="trace", arguments=("many",)),
            self.context,
        )
        unknown = self.router.execute(
            InteractiveCommand(name="missing"),
            self.context,
        )

        self.assertEqual(invalid.text, "usage: /trace [N]\n")
        self.assertEqual(
            unknown.text,
            "unknown command: /missing; use /help\n",
        )
        self.assertNotIn("/steer", HELP_TEXT)
        self.assertNotIn("/candidates", HELP_TEXT)
        self.assertNotIn("/candidate ID", HELP_TEXT)
        self.assertIn("/optimize [TEXT]", HELP_TEXT)
        self.assertEqual(
            self.router.execute(InteractiveCommand(name="steer"), self.context).text,
            "unknown command: /steer; use /help\n",
        )

    def test_custom_handler_can_extend_without_changing_frontend(self) -> None:
        router = CommandRouter(
            {
                "clear": lambda command, context: CommandResult(
                    text="cleared\n"
                )
            }
        )

        result = router.execute(
            InteractiveCommand(name="clear"),
            self.context,
        )

        self.assertEqual(result, CommandResult(text="cleared\n"))

    def test_config_has_a_clear_embedded_frontend_fallback(self) -> None:
        result = self.router.execute(InteractiveCommand("config"), self.context)

        self.assertIn("unavailable", result.text)

    def test_resume_has_help_and_an_embedded_frontend_fallback(self) -> None:
        result = self.router.execute(InteractiveCommand("resume"), self.context)

        self.assertIn("/resume [PATH]", HELP_TEXT)
        self.assertIn("session picker is unavailable", result.text)

    def test_eval_has_help_and_an_embedded_frontend_fallback(self) -> None:
        result = self.router.execute(InteractiveCommand("eval"), self.context)

        self.assertIn("/eval", HELP_TEXT)
        self.assertIn("selection menu is unavailable", result.text)


if __name__ == "__main__":
    unittest.main()
