"""Line-oriented terminal commands remain offline and deterministic."""

from __future__ import annotations

from fruitfly_agent.interactive.optimization import OptimizationPreview

import asyncio
from dataclasses import replace
import io
import os
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from fruitfly_agent.core.config import AgentLoopConfig
from fruitfly_agent.interactive import (
    ResumableSession,
    TerminalConfigurationFrontend,
    InteractiveSession,
    TerminalFrontend,
    TerminalRenderer,
)
from fruitfly_agent.interactive.configuration import (
    ConfigurationActionResult,
    ConfigurationLaunchResult,
    ConfigurationMechanism,
    ConfigurationParameter,
    ConfigurationSelectionGroup,
)
from fruitfly_agent.interactive.commands import CommandResult, CommandRouter
from fruitfly_agent.interactive.events import (
    AssistantTextDelta,
    CompactionStarted,
    RunActivityChanged,
    RunFinished,
    RunStarted,
    ToolOutput,
    ToolStarted,
)
from fruitfly_agent.interactive.terminal.input import ReadlineLineEditor
from fruitfly_agent.interactive.terminal.live import InlineTerminalDisplay
from tests.support.faux_provider import FauxProvider


class _StubLineEditor:
    def __init__(self, *lines: str | None) -> None:
        self.lines = iter(lines)

    def read_line(self) -> str | None:
        return next(self.lines)


class _TtyStringIO(io.StringIO):
    def isatty(self) -> bool:
        return True


class _ActivityTtyStringIO(_TtyStringIO):
    def __init__(self) -> None:
        super().__init__()
        self.activities: list[str] = []

    def set_activity(self, text: str) -> None:
        self.activities.append(text)


class TerminalFrontendTest(unittest.IsolatedAsyncioTestCase):
    async def test_opro_command_confirms_cost_and_reviews_candidate(self) -> None:
        base = InteractiveSession(
            AgentLoopConfig(provider=FauxProvider(), model="offline-model")
        )
        candidate_id = "a" * 32
        record = SimpleNamespace(
            candidate_id=candidate_id, status="proposed", validation_score=1.0,
            seed_score=0.0, direction="be concise", parent_manifest_digest="parent",
            artifact_id="sha256:" + "b" * 64, cases_digest="cases", metric_calls=5,
            algorithm="opro", target="base_prompt", evidence=(("Validation", "1.0"),),
        )

        class OptimizationSession:
            running = False
            pending_count = 0

            @property
            def status(self):
                return base.status

            def set_event_sink(self, sink):
                self.sink = sink

            def optimization_preview(self, *, pack_id=None, direction=""):
                return OptimizationPreview("opro", "OPRO", "Model requests may incur cost", (("Maximum metric calls", "8"),))

            def start_optimization(self, direction, *, preview_token=""):
                return asyncio.create_task(self.optimize(direction))

            async def optimize(self, direction):
                self.direction = direction
                return (record,)

            def candidate_notice(self):
                return (candidate_id,) if not getattr(self, "acknowledged", False) else ()

            def acknowledge_candidate_notice(self, ids):
                self.acknowledged = True

            def cancel_optimization(self):
                return False

            def candidates(self):
                return (record,)

            def candidate_detail(self, value):
                return record, "-old\n+new\n"

            def candidate_action(self, value, action):
                record.status = "selected_for_next_session" if action == "adopt" else "reviewed"
                return record

        session = OptimizationSession()
        output = io.StringIO()
        frontend = TerminalFrontend(
            session,
            input_stream=io.StringIO(),
            output_stream=output,
            line_editor=_StubLineEditor(
                "/optimize be concise", "1", "1", "/optimize", "2", "1",
                "up", "up", "2", "/exit",
            ),
        )
        self.assertEqual(await frontend.run(), 0)
        self.assertEqual(session.direction, "be concise")
        self.assertIn("Maximum metric calls: 8", output.getvalue())
        self.assertIn("candidate(s) ready; not active", output.getvalue())
        self.assertIn("Candidate saved for the next session", output.getvalue())

    async def test_inline_terminal_accepts_input_while_run_is_active(self) -> None:
        base = InteractiveSession(
            AgentLoopConfig(provider=FauxProvider(), model="offline-model")
        )

        class ConcurrentSession:
            def __init__(self) -> None:
                self.prompts = []
                self.steering = []
                self.cancelled = 0
                self.running = False
                self.pending_count = 0
                self.worker = None
                self.release = asyncio.Event()

            @property
            def status(self):
                return base.status

            def set_event_sink(self, sink):
                self.sink = sink

            def enqueue(self, prompt):
                self.prompts.append(prompt)
                self.pending_count += 1
                if self.worker is None:
                    self.running = True
                    self.worker = asyncio.create_task(self._run())
                return self.pending_count

            async def _run(self):
                await self.release.wait()
                self.pending_count = 0
                self.running = False

            async def wait_until_idle(self):
                if self.worker is not None:
                    await self.worker

            def steer(self, prompt):
                if not self.running:
                    return False
                self.steering.append(prompt)
                return True

            def cancel(self):
                if not self.running:
                    return False
                self.cancelled += 1
                self.release.set()
                return True

            def trace(self, limit=12):
                return []

        session = ConcurrentSession()
        output = io.StringIO()
        display = InlineTerminalDisplay(output, rows=12, columns=60)
        editor = _StubLineEditor(
            "first prompt",
            "use the new detail",
            "/cancel",
            None,
        )
        with patch(
            "fruitfly_agent.interactive.terminal.frontend.create_inline_terminal",
            return_value=(display, editor),
        ):
            frontend = TerminalFrontend(
                session,
                input_stream=_TtyStringIO(),
                output_stream=output,
            )

        self.assertEqual(await frontend.run(), 0)
        self.assertEqual(session.prompts, ["first prompt"])
        self.assertEqual(session.steering, ["use the new detail"])
        self.assertEqual(session.cancelled, 1)
        self.assertIn("message added to current run", output.getvalue())
        self.assertIn("cancellation requested", output.getvalue())

    async def test_next_prompt_is_drawn_after_queued_response_finishes(self) -> None:
        base = InteractiveSession(
            AgentLoopConfig(provider=FauxProvider(), model="offline-model")
        )

        class QueuedSession:
            def __init__(self) -> None:
                self.sink = None
                self.worker = None
                self.completed = False

            @property
            def status(self):
                return base.status

            def set_event_sink(self, sink):
                self.sink = sink

            def enqueue(self, prompt):
                self.worker = asyncio.create_task(self._respond())
                return 1

            async def wait_until_idle(self):
                await self.worker

            async def _respond(self):
                await asyncio.sleep(0.02)
                await self.sink(
                    AssistantTextDelta(run_id="run-1", text="response complete")
                )
                await self.sink(
                    RunFinished(
                        run_id="run-1",
                        stop_reason="stop",
                        model="offline-model",
                        turn_count=1,
                        tool_call_count=0,
                        input_tokens=1,
                        output_tokens=2,
                        is_error=False,
                        error_details=None,
                    )
                )
                self.completed = True

        session = QueuedSession()
        output = io.StringIO()
        lines = iter(("hello", "/exit"))
        calls = 0

        def reader(prompt):
            nonlocal calls
            calls += 1
            if calls == 2:
                self.assertTrue(
                    session.completed,
                    "the next prompt was opened while model output was active",
                )
            value = next(lines)
            output.write(f"{prompt}{value}\n")
            return value

        frontend = TerminalFrontend(
            session,
            output_stream=output,
            line_editor=ReadlineLineEditor(output, reader=reader),
        )

        self.assertEqual(await frontend.run(), 0)

        rendered = output.getvalue()
        first_prompt = rendered.index("╭─ prompt ")
        response = rendered.index("🪰 response complete")
        second_prompt = rendered.index("╭─ prompt ", first_prompt + 1)
        self.assertLess(first_prompt, response)
        self.assertLess(response, second_prompt)

    async def test_active_text_and_cancel_are_frontend_controls(self) -> None:
        base = InteractiveSession(
            AgentLoopConfig(provider=FauxProvider(), model="offline-model")
        )

        class Controls:
            def __init__(self) -> None:
                self.queued = []
                self.steered = []
                self.cancelled = 0
                self.running = True
                self.pending_count = 0

            @property
            def status(self):
                return base.status

            def set_event_sink(self, sink):
                base.set_event_sink(sink)

            def trace(self, limit=12):
                return base.trace(limit)

            def enqueue(self, prompt):
                self.queued.append(prompt)
                return len(self.queued)

            def steer(self, prompt):
                self.steered.append(prompt)
                return True

            def cancel(self):
                self.cancelled += 1
                return True

            async def wait_until_idle(self):
                return None

        controls = Controls()
        output = io.StringIO()
        frontend = TerminalFrontend(
            controls,
            output_stream=output,
            line_editor=_StubLineEditor(
                "prefer tests",
                "/cancel",
                None,
            ),
        )

        self.assertEqual(await frontend.run(), 0)
        self.assertEqual(controls.queued, [])
        self.assertEqual(controls.steered, ["prefer tests"])
        self.assertEqual(controls.cancelled, 1)
        self.assertIn("message added to current run", output.getvalue())
        self.assertIn("cancellation requested", output.getvalue())

    async def test_status_lab_trace_and_exit_commands(self) -> None:
        app = InteractiveSession(
            AgentLoopConfig(provider=FauxProvider(), model="offline-model"),
            working_directory=".",
            session_path="session.jsonl",
            mechanisms=("test-mechanism",),
        )
        output = io.StringIO()
        frontend = TerminalFrontend(
            app,
            input_stream=io.StringIO("/status\n/lab\n/trace\n/exit\n"),
            output_stream=output,
        )

        code = await frontend.run()

        self.assertEqual(code, 0)
        rendered = output.getvalue()
        self.assertIn("FruitFlyAgent interactive", rendered)
        self.assertIn("model: offline-model", rendered)
        self.assertIn("Lab mechanisms", rendered)
        self.assertIn("Other\n    - test-mechanism", rendered)
        self.assertIn("trace: empty", rendered)
        self.assertNotIn("\x1b", rendered)
        self.assertEqual(rendered.count("FruitFlyAgent interactive"), 1)

    async def test_resume_picker_switches_session_without_model_submission(self) -> None:
        base = InteractiveSession(
            AgentLoopConfig(provider=FauxProvider(), model="offline-model"),
            working_directory="/workspace",
            session_path="/workspace/current.jsonl",
        )

        class ResumeApplication:
            running = False
            pending_count = 0

            def __init__(self) -> None:
                self.resumed: list[str] = []
                self._status = base.status

            @property
            def status(self):
                return self._status

            def set_event_sink(self, sink):
                self.sink = sink

            def resumable_sessions(self):
                return (
                    ResumableSession(
                        path="/workspace/previous.jsonl",
                        modified_at=1.0,
                        message_count=8,
                        profile="default",
                        model="offline-model",
                    ),
                )

            async def resume(self, path):
                self.resumed.append(str(path))
                self._status = replace(
                    self._status,
                    session_path=str(path),
                    message_count=8,
                )

            def trace(self, limit=12):
                return []

        application = ResumeApplication()
        output = io.StringIO()
        frontend = TerminalFrontend(
            application,
            output_stream=output,
            line_editor=_StubLineEditor("/resume", "1", "/exit"),
        )

        self.assertEqual(await frontend.run(), 0)
        self.assertEqual(application.resumed, ["/workspace/previous.jsonl"])
        self.assertIn("FruitFlyAgent · resume", output.getvalue())
        self.assertIn("8 messages", output.getvalue())
        self.assertIn("previous.jsonl", output.getvalue())

    async def test_resume_refuses_to_switch_while_work_is_active(self) -> None:
        base = InteractiveSession(
            AgentLoopConfig(provider=FauxProvider(), model="offline-model")
        )

        class BusyApplication:
            running = True
            pending_count = 0
            status = base.status

            def set_event_sink(self, sink):
                return None

            async def resume(self, path):
                raise AssertionError("resume must not run")

            def trace(self, limit=12):
                return []

        output = io.StringIO()
        frontend = TerminalFrontend(
            BusyApplication(),
            output_stream=output,
            line_editor=_StubLineEditor("/resume target.jsonl", "/exit"),
        )

        self.assertEqual(await frontend.run(), 0)
        self.assertIn("finish or /cancel", output.getvalue())

    async def test_resume_explicit_relative_path_uses_workspace(self) -> None:
        base = InteractiveSession(
            AgentLoopConfig(provider=FauxProvider(), model="offline-model"),
            working_directory="/workspace",
            session_path="/workspace/current.jsonl",
        )

        class ResumeApplication:
            running = False
            pending_count = 0
            status = base.status

            def __init__(self) -> None:
                self.resumed = None

            def set_event_sink(self, sink):
                return None

            async def resume(self, path):
                self.resumed = path

            def trace(self, limit=12):
                return []

        application = ResumeApplication()
        frontend = TerminalFrontend(
            application,
            output_stream=io.StringIO(),
            line_editor=_StubLineEditor(
                "/resume .fruitfly/sessions/previous.jsonl",
                "/exit",
            ),
        )

        self.assertEqual(await frontend.run(), 0)
        self.assertEqual(
            application.resumed,
            Path("/workspace/.fruitfly/sessions/previous.jsonl"),
        )

    async def test_line_editor_is_a_replaceable_frontend_boundary(self) -> None:
        app = InteractiveSession(
            AgentLoopConfig(provider=FauxProvider(), model="offline-model")
        )
        output = io.StringIO()
        frontend = TerminalFrontend(
            app,
            input_stream=io.StringIO("unused\n"),
            output_stream=output,
            line_editor=_StubLineEditor("/exit"),
        )

        self.assertEqual(await frontend.run(), 0)
        self.assertNotIn("you> ", output.getvalue())

    async def test_custom_command_is_rendered_without_reaching_provider(self) -> None:
        provider = FauxProvider()
        app = InteractiveSession(
            AgentLoopConfig(provider=provider, model="offline-model")
        )
        output = io.StringIO()
        router = CommandRouter(
            {
                "clear": lambda command, context: CommandResult(
                    text="cleared\n"
                )
            }
        )
        frontend = TerminalFrontend(
            app,
            output_stream=output,
            line_editor=_StubLineEditor("/clear", "/exit"),
            command_router=router,
        )

        self.assertEqual(await frontend.run(), 0)
        self.assertIn("cleared\n", output.getvalue())
        self.assertEqual(provider.calls, [])

    def test_no_color_keeps_full_welcome_without_ansi(self) -> None:
        output = _TtyStringIO()
        with patch.dict(os.environ, {"TERM": "xterm-256color", "NO_COLOR": "1"}):
            renderer = TerminalRenderer(output)
            renderer.show_welcome(
                InteractiveSession(
                    AgentLoopConfig(provider=FauxProvider(), model="offline-model")
                ).status
            )

        self.assertIn("⣀⣈⣷⡴⢦⣾⣁⣀", output.getvalue())
        self.assertNotIn("\x1b", output.getvalue())

    async def test_renderer_uses_fruit_fly_mark_and_semantic_activity_colors(
        self,
    ) -> None:
        output = _TtyStringIO()
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
        output = _TtyStringIO()
        with patch.dict(os.environ, {"TERM": "xterm-256color"}, clear=True):
            renderer = TerminalRenderer(output)
            await renderer.render(
                AssistantTextDelta(
                    run_id="run-1",
                    text="**Root cause**: `bad.css`\n",
                )
            )
            await renderer.render(
                RunFinished(
                    run_id="run-1",
                    stop_reason="stop",
                    model="offline-model",
                    turn_count=1,
                    tool_call_count=0,
                    input_tokens=1,
                    output_tokens=2,
                    is_error=False,
                    error_details=None,
                )
            )

        rendered = output.getvalue()
        self.assertIn("\x1b[1mRoot cause\x1b[0m", rendered)
        self.assertIn("\x1b[36mbad.css\x1b[0m", rendered)
        self.assertNotIn("**Root cause**", rendered)
        self.assertNotIn("`bad.css`", rendered)

    async def test_no_color_keeps_markdown_layout_without_sgr(self) -> None:
        output = _TtyStringIO()
        with patch.dict(
            os.environ,
            {"TERM": "xterm-256color", "NO_COLOR": "1"},
            clear=True,
        ):
            renderer = TerminalRenderer(output)
            await renderer.render(
                AssistantTextDelta(
                    run_id="run-1",
                    text="## Result\n\n- **fixed**\n",
                )
            )
            renderer.finish_line()

        rendered = output.getvalue()
        self.assertIn("▸ Result", rendered)
        self.assertIn("• fixed", rendered)
        self.assertNotIn("## Result", rendered)
        self.assertNotIn("**fixed**", rendered)
        self.assertNotIn("\x1b", rendered)

    async def test_tool_boundary_commits_unfinished_markdown_answer(self) -> None:
        output = _TtyStringIO()
        with patch.dict(os.environ, {"TERM": "xterm-256color"}, clear=True):
            renderer = TerminalRenderer(output)
            await renderer.render(
                AssistantTextDelta(
                    run_id="run-1",
                    text="**Checking** `README.md`",
                )
            )
            await renderer.render(
                ToolStarted(
                    run_id="run-1",
                    tool_call_id="tool-1",
                    tool_name="read",
                    arguments={"path": "README.md"},
                )
            )

        rendered = output.getvalue()
        answer = rendered.index("Checking")
        tool = rendered.index("[tool read]")
        self.assertLess(answer, tool)
        self.assertNotIn("**Checking**", rendered)
        self.assertNotIn("`README.md`", rendered)

    async def test_renderer_keeps_raw_markdown_for_redirected_output(self) -> None:
        output = io.StringIO()
        renderer = TerminalRenderer(output)

        await renderer.render(
            AssistantTextDelta(
                run_id="run-1",
                text="**Root cause**: `bad.css`\n",
            )
        )

        self.assertIn("**Root cause**: `bad.css`", output.getvalue())
        self.assertNotIn("\x1b", output.getvalue())

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
                RunFinished(
                    run_id="run-1",
                    stop_reason="stop",
                    model="offline-model",
                    turn_count=1,
                    tool_call_count=0,
                    input_tokens=1,
                    output_tokens=2,
                    is_error=False,
                    error_details=None,
                )
            )

        self.assertTrue(output.activities[0].startswith("⠋ Preparing · "))
        self.assertTrue(
            any(
                "Waiting for offline-model · request 2" in activity
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
        output = io.StringIO()
        renderer = TerminalRenderer(output)
        content = "<html>\n" + ("private body\n" * 1000) + "</html>"

        await renderer.render(
            ToolStarted(
                run_id="run-1",
                tool_call_id="tool-1",
                tool_name="write",
                arguments={"path": "page7.html", "content": content},
            )
        )

        rendered = output.getvalue()
        self.assertIn('path="page7.html"', rendered)
        self.assertIn("chars", rendered)
        self.assertIn("lines", rendered)
        self.assertNotIn("private body", rendered)

    async def test_renderer_bounds_live_tool_output(self) -> None:
        output = io.StringIO()
        renderer = TerminalRenderer(output)

        await renderer.render(
            ToolStarted(
                run_id="run-1",
                tool_call_id="tool-1",
                tool_name="bash",
                arguments={"command": "generate output"},
            )
        )
        await renderer.render(ToolOutput(run_id="run-1", text="x" * 1000))
        await renderer.render(ToolOutput(run_id="run-1", text="never-visible"))

        rendered = output.getvalue()
        self.assertEqual(rendered.count("x"), 800)
        self.assertIn("live tool output truncated", rendered)
        self.assertNotIn("never-visible", rendered)

    async def test_renderer_keeps_fly_mark_with_first_nonempty_answer_line(
        self,
    ) -> None:
        output = io.StringIO()
        renderer = TerminalRenderer(output)

        await renderer.render(
            AssistantTextDelta(run_id="run-1", text="\r\n")
        )
        await renderer.render(
            AssistantTextDelta(run_id="run-1", text="\nLet me try reading the file:")
        )
        await renderer.render(
            AssistantTextDelta(run_id="run-1", text="\nSecond line")
        )
        renderer.finish_line()

        self.assertEqual(output.getvalue(), "🪰 Let me try reading the file:\nSecond line\n")

    async def test_embedded_session_reports_that_host_must_apply_saved_config(self) -> None:
        app = InteractiveSession(
            AgentLoopConfig(provider=FauxProvider(), model="offline-model")
        )
        controller = MockConfiguration(model="offline")
        output = io.StringIO()
        frontend = TerminalFrontend(
            app,
            output_stream=output,
            line_editor=_StubLineEditor(
                "/config",
                "3",      # Custom category (after Model and Base prompt)
                "space",  # Enable the mechanism
                "back",
                "back",
                "1",      # Save and start a new session
            ),
            configuration=controller,
        )

        self.assertEqual(await frontend.run(), 0)
        self.assertTrue(controller.saved)
        self.assertIn("New session required", output.getvalue())
        self.assertIn("embedding host must open a new runtime", output.getvalue())

    async def test_config_menu_returns_to_current_session_when_unchanged(self) -> None:
        app = InteractiveSession(
            AgentLoopConfig(provider=FauxProvider(), model="offline-model")
        )
        controller = MockConfiguration(model="offline")
        frontend = TerminalFrontend(
            app,
            output_stream=io.StringIO(),
            line_editor=_StubLineEditor("/config", "back", "/exit"),
            configuration=controller,
        )

        self.assertEqual(await frontend.run(), 0)
        self.assertFalse(controller.saved)

    def test_dumb_terminal_uses_plain_welcome(self) -> None:
        output = _TtyStringIO()
        with patch.dict(os.environ, {"TERM": "dumb"}, clear=False):
            renderer = TerminalRenderer(output)
            renderer.show_welcome(
                InteractiveSession(
                    AgentLoopConfig(provider=FauxProvider(), model="offline-model")
                ).status
            )

        self.assertIn("FruitFlyAgent interactive · offline-model", output.getvalue())
        self.assertNotIn("███", output.getvalue())
        self.assertNotIn("\x1b", output.getvalue())


class TerminalConfigurationFrontendTest(unittest.TestCase):
    def test_startup_returns_only_after_save_when_configuration_changes(self) -> None:
        controller = MockConfiguration()
        output = io.StringIO()
        frontend = TerminalConfigurationFrontend(
            controller,
            output_stream=output,
            line_editor=_StubLineEditor("2", "", "1", "back", "1"),
        )

        result = frontend.run()

        self.assertEqual(result, ConfigurationLaunchResult(start=True, saved=True))
        self.assertEqual(controller.model, "offline")
        self.assertTrue(controller.saved)
        self.assertIn("Ready to start", output.getvalue())
        self.assertIn("> 1. Start new session", output.getvalue())
        self.assertIn("1. Model", output.getvalue())
        self.assertNotIn("Advanced settings", output.getvalue())

    def test_ready_configuration_starts_from_option_without_saving(self) -> None:
        controller = MockConfiguration(model="offline")
        output = io.StringIO()
        frontend = TerminalConfigurationFrontend(
            controller,
            output_stream=output,
            line_editor=_StubLineEditor("1"),
        )

        result = frontend.run()

        self.assertEqual(result, ConfigurationLaunchResult(start=True))
        self.assertFalse(controller.saved)

    def test_resume_view_is_read_only_and_generic(self) -> None:
        controller = MockConfiguration(model="offline")
        output = io.StringIO()
        frontend = TerminalConfigurationFrontend(
            controller,
            output_stream=output,
            line_editor=_StubLineEditor("1"),
        )

        result = frontend.run(editable=False)

        self.assertTrue(result.start)
        self.assertIn("FruitFlyAgent · resume", output.getvalue())
        self.assertIn("> 1. Resume session", output.getvalue())
        self.assertFalse(controller.changed)

    def test_configuration_groups_mechanisms_and_hides_parameters(self) -> None:
        controller = MockConfiguration(model="offline")
        output = io.StringIO()
        frontend = TerminalConfigurationFrontend(
            controller,
            output_stream=output,
            line_editor=_StubLineEditor(
                "2",      # configure
                "3",      # custom category (after Model and Base prompt)
                "space",  # toggle the injected mechanism
                "back",
                "back",
                "1",      # save and start
            ),
        )

        result = frontend.run()

        self.assertEqual(result, ConfigurationLaunchResult(start=True, saved=True))
        self.assertTrue(controller.enabled)
        self.assertIn("Injected mechanism", output.getvalue())
        self.assertNotIn("Provided entirely by the configuration snapshot.", output.getvalue())
        self.assertIn("✓ Injected mechanism", output.getvalue())
        self.assertNotIn("Toggle the injected feature", output.getvalue())
        self.assertNotIn("feature=True", output.getvalue())

    def test_configuration_omits_advanced_settings_and_detailed_parameters(self) -> None:
        controller = MockConfiguration(model="offline")
        output = io.StringIO()
        frontend = TerminalConfigurationFrontend(
            controller,
            output_stream=output,
            line_editor=_StubLineEditor("back"),
        )

        result = frontend.run_for_active_session()

        self.assertEqual(result, ConfigurationLaunchResult(start=False))
        rendered = output.getvalue()
        self.assertNotIn("Advanced settings", rendered)
        self.assertNotIn("Profile", rendered)
        self.assertNotIn("Model catalog", rendered)
        self.assertNotIn("Feature", rendered)
        self.assertNotIn("Toggle the injected feature", rendered)

    def test_module_checkbox_and_inline_algorithm_dropdown_hide_parameters(self) -> None:
        controller = AlgorithmConfiguration()
        output = io.StringIO()
        frontend = TerminalConfigurationFrontend(
            controller, output_stream=output,
            line_editor=_StubLineEditor("3", "2", "5", "back", "back", "1"),
        )
        result = frontend.run_for_active_session()
        self.assertEqual(result, ConfigurationLaunchResult(start=True, saved=True))
        self.assertEqual(controller.algorithm, "variant-c")
        rendered = output.getvalue()
        self.assertIn("✓ Reduction", rendered)
        self.assertIn("Algorithm: variant-b ▾", rendered)
        self.assertIn("Algorithm: variant-c ▾", rendered)
        self.assertIn("variant-a", rendered)
        self.assertNotIn("Settings", rendered)
        self.assertNotIn("Maximum tokens", rendered)
        self.assertNotIn("Detailed algorithm tuning", rendered)

    def test_single_algorithm_still_has_inline_dropdown(self) -> None:
        controller = AlgorithmConfiguration()
        original_snapshot = controller.snapshot
        def snapshot():
            value = original_snapshot()
            only = next(item for item in value.mechanisms if item.mechanism_id == "variant-b")
            return replace(value, mechanisms=(only,), selection_groups=(
                replace(value.selection_groups[0], option_ids=("variant-b",)),
            ))
        controller.snapshot = snapshot
        output = io.StringIO()
        frontend = TerminalConfigurationFrontend(
            controller, output_stream=output,
            line_editor=_StubLineEditor("2", "3", "back"),
        )
        self.assertFalse(frontend._category_loop("compaction"))
        self.assertEqual(controller.algorithm, "variant-b")
        self.assertIn("Algorithm: variant-b ▴", output.getvalue())
        self.assertIn("✓     variant-b", output.getvalue())
        self.assertNotIn("Settings", output.getvalue())

    def test_dropdown_cancel_keeps_algorithm_and_toggle_remembers_choice(self) -> None:
        controller = AlgorithmConfiguration()
        output = io.StringIO()
        frontend = TerminalConfigurationFrontend(
            controller, output_stream=output,
            line_editor=_StubLineEditor("2", "back", "1", "1", "back"),
        )
        self.assertFalse(frontend._category_loop("compaction"))
        self.assertEqual(controller.algorithm, "variant-b")
        self.assertTrue(controller.enabled)
        self.assertNotIn("Settings", output.getvalue())

    def test_active_session_configuration_requires_confirmation(self) -> None:
        controller = MockConfiguration(model="offline")
        output = io.StringIO()
        frontend = TerminalConfigurationFrontend(
            controller,
            output_stream=output,
            line_editor=_StubLineEditor(
                "3",      # Custom category (after Model and Base prompt)
                "space",  # Enable the mechanism
                "back",
                "back",
                "1",      # Save and start a new session
            ),
        )

        result = frontend.run_for_active_session()

        self.assertEqual(result, ConfigurationLaunchResult(start=True, saved=True))
        self.assertTrue(controller.saved)
        self.assertIn("New session required", output.getvalue())

    def test_active_session_configuration_returns_without_changes(self) -> None:
        controller = MockConfiguration(model="offline")
        frontend = TerminalConfigurationFrontend(
            controller,
            output_stream=io.StringIO(),
            line_editor=_StubLineEditor("back"),
        )

        result = frontend.run_for_active_session()

        self.assertEqual(result, ConfigurationLaunchResult(start=False))
        self.assertFalse(controller.saved)

    def test_current_model_uses_a_checkmark(self) -> None:
        controller = MockConfiguration(model="offline")
        output = io.StringIO()
        frontend = TerminalConfigurationFrontend(
            controller,
            output_stream=output,
            line_editor=_StubLineEditor("1", "back", "back"),
        )

        result = frontend.run_for_active_session()

        self.assertEqual(result, ConfigurationLaunchResult(start=False))
        self.assertIn("✓ offline", output.getvalue())


class MockConfiguration:
    def __init__(self, *, model=None) -> None:
        self.model = model
        self.saved = False
        self.changed = False
        self.enabled = False
        self.parameter = True

    def snapshot(self):
        from fruitfly_agent.interactive.configuration import ConfigurationSnapshot

        return ConfigurationSnapshot(
            "/workspace/fruitfly.yaml",
            "default",
            ("default",),
            "models.yaml",
            self.model,
            ("offline",),
            (
                ConfigurationMechanism(
                    "custom",
                    "custom",
                    "Injected mechanism",
                    "Provided entirely by the configuration snapshot.",
                    self.enabled,
                    "new_session",
                    parameters=(
                        ConfigurationParameter(
                            "feature",
                            "Feature",
                            "Toggle the injected feature.",
                            "boolean",
                            self.parameter,
                        ),
                    ),
                ),
            ),
            ready=self.model is not None,
            changed=self.changed,
        )

    def select_profile(self, profile_id):
        self.changed = True
        return ConfigurationActionResult("selected", changed=True)

    def select_model_catalog(self, path):
        self.changed = True
        return ConfigurationActionResult("catalog", changed=True)

    def select_model(self, model_profile):
        self.model = model_profile
        self.changed = True
        return ConfigurationActionResult("model", changed=True)

    def set_mechanism(self, mechanism_id, *, enabled):
        self.enabled = enabled
        self.changed = True
        return ConfigurationActionResult("mechanism", changed=True)

    def set_parameter(self, mechanism_id, name, value):
        self.parameter = value == "true"
        self.changed = True
        return ConfigurationActionResult("parameter", changed=True)

    def save(self):
        self.saved = True
        self.changed = False
        return ConfigurationActionResult("saved", saved=True)

    def reset(self):
        self.changed = False
        self.enabled = False
        return ConfigurationActionResult("reset")


class AlgorithmConfiguration(MockConfiguration):
    def __init__(self) -> None:
        super().__init__(model="offline")
        self.enabled = True
        self.algorithm = "variant-b"

    def snapshot(self):
        snapshot = super().snapshot()
        options = ("variant-a", "variant-b", "variant-c")
        return replace(snapshot,
            mechanisms=tuple(ConfigurationMechanism(
                option, "compaction", option, "Detailed algorithm tuning.",
                self.enabled and self.algorithm == option, "new_session",
                parameters=(ConfigurationParameter("max_tokens", "Maximum tokens", "Hidden tuning", "integer", 1000),),
                selection_group="reduction",
            ) for option in options),
            selection_groups=(ConfigurationSelectionGroup(
                "reduction", "Reduction", "compaction", "reduction", options,
                self.algorithm if self.enabled else None,
            ),),
        )

    def select_algorithm(self, group_id, option_id):
        assert group_id == "reduction"
        if option_id is not None:
            self.algorithm = option_id
        self.enabled = option_id is not None
        self.changed = True
        return ConfigurationActionResult("algorithm", changed=True)
