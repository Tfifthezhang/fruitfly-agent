"""Offline terminal renderer events and output boundaries."""

import asyncio
import io
import os
import unittest
from unittest.mock import patch

from fruitfly_agent.interactive import TerminalRenderer
from fruitfly_agent.interactive.events import (
    AssistantTextDelta, CompactionStarted, RunActivityChanged,
    RunStarted, ToolOutput, ToolStarted,
)
from tests.support.application import offline_session
from tests.support.terminal import TtyStringIO, run_finished


class _ActivityTtyStringIO(TtyStringIO):
    def __init__(self) -> None:
        super().__init__()
        self.activities: list[str] = []

    def set_activity(self, text: str) -> None:
        self.activities.append(text)


class TerminalRendererTests(unittest.IsolatedAsyncioTestCase):
    async def render_events(self, *events, tty=False, no_color=False, finish_line=False):
        output = TtyStringIO() if tty else io.StringIO()
        environment = {"TERM": "xterm-256color"}
        if no_color:
            environment["NO_COLOR"] = "1"
        with patch.dict(os.environ, environment, clear=True):
            renderer = TerminalRenderer(output)
            try:
                for event in events:
                    await renderer.render(event)
                if finish_line:
                    renderer.finish_line()
                return output.getvalue()
            finally:
                await renderer.close()

    def test_no_color_keeps_full_welcome_without_ansi(self) -> None:
        output = TtyStringIO()
        with patch.dict(os.environ, {"TERM": "xterm-256color", "NO_COLOR": "1"}):
            renderer = TerminalRenderer(output)
            renderer.show_welcome(
                offline_session().status
            )

        self.assertIn("⣀⣈⣷⡴⢦⣾⣁⣀", output.getvalue())
        self.assertNotIn("\x1b", output.getvalue())

    async def test_renderer_uses_fruit_fly_mark_and_semantic_activity_colors(
        self,
    ) -> None:
        output = TtyStringIO()
        with patch.dict(os.environ, {"TERM": "xterm-256color"}, clear=True):
            renderer = TerminalRenderer(output)
            await renderer.render(
                AssistantTextDelta(run_id="run-1", text="answer")
            )
            await renderer.render(
                ToolStarted(
                    run_id="run-1",
                    tool_call_id="tool-1",
                    tool_name="read",
                    arguments={"path": "README.md"},
                    category="tools",
                )
            )
            await renderer.render(
                ToolStarted(
                    run_id="run-1",
                    tool_call_id="tool-2",
                    tool_name="note_lookup",
                    arguments={"id": "note"},
                    category="memory",
                )
            )
            await renderer.render(
                ToolStarted(
                    run_id="run-1",
                    tool_call_id="tool-3",
                    tool_name="skill_lookup",
                    arguments={"name": "review"},
                    category="skills",
                )
            )
            await renderer.render(
                CompactionStarted(
                    run_id="run-1",
                    estimated_tokens=100,
                    mechanism_id="example-reducer",
                    trigger="overflow",
                )
            )

        rendered = output.getvalue()
        self.assertIn("\x1b[1;32m🪰 \x1b[0manswer", rendered)
        self.assertIn("\x1b[36m[tool read] \x1b[0m", rendered)
        self.assertIn("\x1b[35m[memory note_lookup] \x1b[0m", rendered)
        self.assertIn("\x1b[34m[skill skill_lookup] \x1b[0m", rendered)
        self.assertIn("\x1b[33m[compaction example-reducer", rendered)

    async def test_renderer_presents_markdown_only_on_ansi_terminal(self) -> None:
        rendered = await self.render_events(
            AssistantTextDelta(run_id='run-1', text='**Root cause**: `bad.css`\n'),
            run_finished(),
            tty=True,
        )
        self.assertIn("\x1b[1mRoot cause\x1b[0m", rendered)
        self.assertIn("\x1b[36mbad.css\x1b[0m", rendered)
        self.assertNotIn("**Root cause**", rendered)
        self.assertNotIn("`bad.css`", rendered)

    async def test_no_color_keeps_markdown_layout_without_sgr(self) -> None:
        rendered = await self.render_events(
            AssistantTextDelta(run_id='run-1', text='## Result\n\n- **fixed**\n'),
            tty=True, no_color=True, finish_line=True,
        )
        self.assertIn("▸ Result", rendered)
        self.assertIn("• fixed", rendered)
        self.assertNotIn("## Result", rendered)
        self.assertNotIn("**fixed**", rendered)
        self.assertNotIn("\x1b", rendered)

    async def test_tool_boundary_commits_unfinished_markdown_answer(self) -> None:
        rendered = await self.render_events(
            AssistantTextDelta(run_id='run-1', text='**Checking** `README.md`'),
            ToolStarted(
                run_id='run-1', tool_call_id='tool-1', tool_name='read', arguments={'path': 'README.md'},
            ),
            tty=True,
        )
        answer = rendered.index("Checking")
        tool = rendered.index("[tool read]")
        self.assertLess(answer, tool)
        self.assertNotIn("**Checking**", rendered)
        self.assertNotIn("`README.md`", rendered)

    async def test_renderer_keeps_raw_markdown_for_redirected_output(self) -> None:
        rendered = await self.render_events(
            AssistantTextDelta(run_id='run-1', text='**Root cause**: `bad.css`\n'),
        )
        self.assertIn("**Root cause**: `bad.css`", rendered)
        self.assertNotIn("\x1b", rendered)

    async def test_renderer_keeps_activity_transient_and_stops_animation(self) -> None:
        output = _ActivityTtyStringIO()
        with patch.dict(os.environ, {"TERM": "xterm-256color"}, clear=True):
            renderer = TerminalRenderer(output)
            await renderer.render(
                RunStarted(
                    run_id="run-1",
                    prompt="hello",
                    model="offline-model",
                    message_count=1,
                )
            )
            await renderer.render(
                RunActivityChanged(
                    run_id="run-1",
                    phase="waiting_model",
                    request_index=2,
                    subject="offline-model",
                    activity_id="model-request-2",
                )
            )
            await asyncio.sleep(0.14)
            await renderer.render(
                run_finished()
            )

        self.assertTrue(output.activities[0].startswith("⠋ Preparing · "))
        self.assertTrue(
            any(
                "Waiting for offline-model · /cancel or Ctrl+C to stop · request 2" in activity
                for activity in output.activities
            )
        )
        self.assertGreaterEqual(len(output.activities), 4)
        self.assertEqual(output.activities[-1], "")
        self.assertNotIn("[activity]", output.getvalue())

    async def test_renderer_prints_bounded_activity_milestones_without_tty(
        self,
    ) -> None:
        output = io.StringIO()
        renderer = TerminalRenderer(output)

        await renderer.render(
            RunStarted(
                run_id="run-1",
                prompt="hello",
                model="offline-model",
                message_count=1,
            )
        )
        await renderer.render(
            RunActivityChanged(
                run_id="run-1",
                phase="running_tool",
                subject="write",
                activity_id="tool-1",
            )
        )
        await renderer.close()

        self.assertEqual(
            output.getvalue(),
            "[activity] Preparing\n[activity] Running write\n",
        )
        self.assertNotIn("\x1b", output.getvalue())

    async def test_renderer_summarizes_large_tool_arguments(self) -> None:
        content = "<html>\n" + ("private body\n" * 1000) + "</html>"
        rendered = await self.render_events(
            ToolStarted(
                run_id='run-1', tool_call_id='tool-1', tool_name='write',
                arguments={'path': 'page7.html', 'content': content},
            ),
        )
        self.assertIn('path="page7.html"', rendered)
        self.assertIn("chars", rendered)
        self.assertIn("lines", rendered)
        self.assertNotIn("private body", rendered)

    async def test_renderer_bounds_live_tool_output(self) -> None:
        rendered = await self.render_events(
            ToolStarted(
                run_id='run-1', tool_call_id='tool-1', tool_name='bash',
                arguments={'command': 'generate output'},
            ),
            ToolOutput(run_id='run-1', text='x' * 1000),
            ToolOutput(run_id='run-1', text='never-visible'),
        )
        self.assertEqual(rendered.count("x"), 800)
        self.assertIn("live tool output truncated", rendered)
        self.assertNotIn("never-visible", rendered)

    async def test_renderer_keeps_fly_mark_with_first_nonempty_answer_line(
        self,
    ) -> None:
        rendered = await self.render_events(
            AssistantTextDelta(run_id='run-1', text='\r\n'),
            AssistantTextDelta(run_id='run-1', text='\nLet me try reading the file:'),
            AssistantTextDelta(run_id='run-1', text='\nSecond line'),
            finish_line=True,
        )
        self.assertEqual(rendered, "🪰 Let me try reading the file:\nSecond line\n")

    def test_dumb_terminal_uses_plain_welcome(self) -> None:
        output = TtyStringIO()
        with patch.dict(os.environ, {"TERM": "dumb"}, clear=False):
            renderer = TerminalRenderer(output)
            renderer.show_welcome(
                offline_session().status
            )

        self.assertIn("FruitFlyAgent interactive · offline-model", output.getvalue())
        self.assertNotIn("███", output.getvalue())
        self.assertNotIn("\x1b", output.getvalue())

