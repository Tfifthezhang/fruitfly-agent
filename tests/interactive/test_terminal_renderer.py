"""Offline terminal renderer events and output boundaries."""

import asyncio
import io
import os
import unittest
from dataclasses import replace
from unittest.mock import patch

from fruitfly_agent.interactive import TerminalRenderer
from fruitfly_agent.interactive.contracts.events import AssistantTextDelta, AssistantThinkingDelta, CompactionStarted, RunActivityChanged, RunStarted, ToolOutput, ToolStarted
from tests.support.application import offline_session
from tests.support.terminal import TtyStringIO, run_finished


class _ActivityTtyStringIO(TtyStringIO):
    def __init__(self) -> None:
        super().__init__()
        self.activities: list[str] = []

    def set_activity(self, text: str) -> None:
        self.activities.append(text)


class TerminalRendererTests(unittest.IsolatedAsyncioTestCase):
    def test_submission_history_has_no_width_dependent_frame(self):
        output = io.StringIO()
        renderer = TerminalRenderer(output)
        renderer.write_user_input("/improvement\nsecond line")
        self.assertEqual(output.getvalue(), "\n❯ /improvement\n│ second line\n\n")
        self.assertNotIn("─", output.getvalue())

    async def test_hidden_reasoning_preserves_answer_stream_and_markdown(self) -> None:
        answer = (
            AssistantTextDelta(run_id="run-1", text="**Complete"),
            AssistantTextDelta(run_id="run-1", text=" answer**\n"),
            run_finished(),
        )
        for tty, no_color in ((False, False), (True, False), (True, True)):
            with self.subTest(tty=tty, no_color=no_color):
                expected = await self.render_events(*answer, tty=tty, no_color=no_color)
                actual = await self.render_events(
                    AssistantThinkingDelta(run_id="run-1", text="hidden before answer"),
                    answer[0],
                    AssistantThinkingDelta(run_id="run-1", text="hidden inside Markdown"),
                    answer[1], answer[2],
                    tty=tty, no_color=no_color,
                )
                self.assertEqual(actual, expected)
                self.assertNotIn("thinking>", actual)

    async def test_redirected_reasoning_has_one_status_and_no_text(self) -> None:
        activity = RunActivityChanged(run_id="run-1", phase="receiving_thinking")
        rendered = await self.render_events(
            activity,
            AssistantThinkingDelta(run_id="run-1", text="hidden first chunk"),
            activity,
            AssistantThinkingDelta(run_id="run-1", text="hidden second chunk"),
            RunActivityChanged(run_id="run-1", phase="receiving_answer"),
            AssistantTextDelta(run_id="run-1", text="answer"),
            finish_line=True,
        )
        self.assertEqual(rendered, (
            "[activity] Receiving model reasoning\n"
            "[activity] Receiving answer\n🪰 answer\n"
        ))

    async def test_reasoning_activity_survives_deltas_and_clears_on_all_end_paths(self) -> None:
        endings = (
            run_finished(),
            replace(run_finished(), stop_reason="aborted"),
            replace(run_finished(), is_error=True, error_details="offline failure"),
            None,
        )
        for ending in endings:
            with self.subTest(ending=ending), patch.dict(
                os.environ, {"TERM": "xterm-256color"}, clear=True,
            ):
                output = _ActivityTtyStringIO()
                renderer = TerminalRenderer(output)
                try:
                    await renderer.render(RunActivityChanged(
                        run_id="run-1", phase="receiving_thinking",
                    ))
                    self.assertIn("Receiving model reasoning", output.activities[-1])
                    initial_activities = list(output.activities)
                    for chunk in ("hidden first chunk", "hidden second chunk"):
                        await renderer.render(AssistantThinkingDelta(run_id="run-1", text=chunk))
                    self.assertEqual(output.activities, initial_activities)
                    self.assertEqual(output.getvalue(), "")
                    if ending is not None:
                        await renderer.render(ending)
                        self.assertEqual(output.activities[-1], "")
                    await renderer.close()
                    self.assertEqual(output.activities[-1], "")
                    if ending is not None and ending.is_error:
                        self.assertIn("offline failure", output.getvalue())
                    if ending is not None and ending.stop_reason == "aborted":
                        self.assertIn("run cancelled", output.getvalue())
                finally:
                    await renderer.close()

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
        self.assertIn("\x1b[36m◐ read\n\x1b[0m", rendered)
        self.assertIn("\x1b[35m◐ note_lookup\n\x1b[0m", rendered)
        self.assertIn("\x1b[34m◐ skill_lookup\n\x1b[0m", rendered)
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
        tool = rendered.index("◐ read")
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

