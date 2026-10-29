"""Line-oriented terminal commands remain offline and deterministic."""

from __future__ import annotations

from fruitfly_agent.interactive.contracts.improvement import ImprovementPreview, ImprovementTargetView
from tests.support.improvement_ui import configuration

import asyncio
from dataclasses import replace
import io
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from fruitfly_agent.interactive import ResumableSession, TerminalFrontend
from fruitfly_agent.interactive.contracts.commands import CommandResult
from fruitfly_agent.interactive.interaction.commands import CommandRouter
from fruitfly_agent.interactive.contracts.events import AssistantTextDelta, AuthorizationRequested, AuthorizationResolved
from fruitfly_agent.interactive.terminal.io.input import ReadlineLineEditor
from fruitfly_agent.interactive.terminal.io.live import InlineTerminalDisplay, IsolatedLineEditor
from fruitfly_agent.interactive.terminal.rendering.renderer import TerminalRenderer
from tests.support.faux_provider import FauxProvider
from tests.support.application import offline_session
from tests.support.configuration import MockConfiguration
from tests.support.terminal import ScriptedLines, MenuScriptedLines, TtyStringIO, run_finished


class _TerminalSessionStub:
    running = False
    pending_count = 0

    def __init__(self, **kwargs):
        self.base = offline_session(**kwargs)

    @property
    def status(self):
        return self.base.status

    def set_event_sink(self, sink):
        self.sink = sink
        self.base.set_event_sink(sink)

    def trace(self, limit=12):
        return self.base.trace(limit)


class TerminalFrontendTest(unittest.IsolatedAsyncioTestCase):
    async def test_permission_menu_uses_exact_scope_and_clears_on_resolution(self) -> None:
        session = offline_session()
        output = TtyStringIO()
        display = InlineTerminalDisplay(output, rows=12, columns=100)
        editor = IsolatedLineEditor(io.StringIO(), display)
        with patch.dict("os.environ", {"TERM": "xterm-256color"}, clear=True):
            renderer = TerminalRenderer(display)
            frontend = TerminalFrontend(session, input_stream=io.StringIO(), output_stream=output,
                                        line_editor=editor, renderer=renderer)
            display.activate()
            try:
                await frontend._render_event(AuthorizationRequested(
                    run_id="", request_id="request-1", tool_name="read", operation="read",
                    targets=("/outside/file.txt",), summary="Read the requested file",
                    session_label="Allow reads in /outside for this session",
                ))
                self.assertEqual(editor._choices[1], "2. Allow reads in /outside for this session")
                self.assertIn("❯ 1. Allow once", output.getvalue())
                self.assertIn("target: /outside/file.txt", output.getvalue())
                self.assertIn("Read the requested file", output.getvalue())
                start = len(output.getvalue())
                await frontend._render_event(AuthorizationResolved(
                    run_id="", request_id="request-1", operation="read", choice="deny",
                ))
                self.assertEqual(editor._choices, ())
                resolved = output.getvalue()[start:]
                self.assertNotIn("Allow reads", resolved)
                self.assertIn("permission: deny", resolved)
                self.assertIn("❯ ", resolved)
                self.assertNotIn("╭", resolved)
            finally:
                await renderer.close()
                display.suspend()

    async def test_opro_command_confirms_cost_and_reviews_candidate(self) -> None:
        candidate_id = "a" * 32
        record = SimpleNamespace(
            candidate_id=candidate_id, status="proposed", validation_score=1.0,
            seed_score=0.0, direction="be concise", parent_manifest_digest="parent",
            artifact_id="sha256:" + "b" * 64, cases_digest="cases", metric_calls=5,
            algorithm="opro", target="base_prompt", role="H", evidence=(("Validation", "1.0"),),
        )

        class ImprovementSession(_TerminalSessionStub):
            def workflow_configuration(self):
                return configuration()

            def workflow_preview(self, request):
                return ImprovementPreview('rule', 'Rule', 'Model requests may incur cost',
                    (('Maximum model calls', '8'),), target='base_prompt', preview_token='token')

            def start_improvement(self, direction, *, preview_token=""):
                return asyncio.create_task(self.improve(direction))

            async def improve(self, direction):
                self.direction = direction
                return (record,)

            def candidate_notice(self):
                return (candidate_id,) if not getattr(self, "acknowledged", False) else ()

            def acknowledge_candidate_notice(self, ids):
                self.acknowledged = True

            def cancel_improvement(self):
                return False

            def candidates(self):
                return (record,)

            def candidate_detail(self, value):
                return record, "-old\n+new\n"

            def candidate_action(self, value, action):
                record.status = "selected_for_next_session" if action == "adopt" else "reviewed"
                return record

        session = ImprovementSession()
        output = io.StringIO()
        frontend = TerminalFrontend(
            session,
            input_stream=io.StringIO(),
            output_stream=output,
            line_editor=MenuScriptedLines(output,
                '/improvement be concise', '@Start improvement', '@Start the frozen workflow',
                '@Review candidate', '@Set as next-session default', '@Set as next-session default', 'q', '/exit',
            ),
        )
        self.assertEqual(await frontend.run(), 0)
        self.assertEqual(session.direction, "be concise")
        self.assertIn("Maximum model calls: 8", output.getvalue())
        self.assertIn("candidate(s)", output.getvalue())
        self.assertIn("Candidate saved for the next session", output.getvalue())

    async def test_inline_terminal_accepts_input_while_run_is_active(self) -> None:

        class ConcurrentSession(_TerminalSessionStub):
            def __init__(self) -> None:
                super().__init__()
                self.prompts = []
                self.steering = []
                self.cancelled = 0
                self.running = False
                self.pending_count = 0
                self.worker = None
                self.release = asyncio.Event()


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


        session = ConcurrentSession()
        output = io.StringIO()
        display = InlineTerminalDisplay(output, rows=12, columns=60)
        editor = ScriptedLines(
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
                input_stream=TtyStringIO(),
                output_stream=output,
            )

        self.assertEqual(await frontend.run(), 0)
        self.assertEqual(session.prompts, ["first prompt"])
        self.assertEqual(session.steering, ["use the new detail"])
        self.assertEqual(session.cancelled, 1)
        self.assertIn("message added to current run", output.getvalue())
        self.assertIn("cancellation requested", output.getvalue())

    async def test_next_prompt_is_drawn_after_queued_response_finishes(self) -> None:

        class QueuedSession(_TerminalSessionStub):
            def __init__(self) -> None:
                super().__init__()
                self.sink = None
                self.worker = None
                self.completed = False


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
                    run_finished()
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
        first_prompt = rendered.index("❯ hello")
        response = rendered.index("🪰 response complete")
        second_prompt = rendered.index("❯ /exit", first_prompt + 1)
        self.assertLess(first_prompt, response)
        self.assertLess(response, second_prompt)

    async def test_active_text_and_cancel_are_frontend_controls(self) -> None:

        class Controls(_TerminalSessionStub):
            def __init__(self) -> None:
                super().__init__()
                self.queued = []
                self.steered = []
                self.cancelled = 0
                self.running = True
                self.pending_count = 0


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
            line_editor=ScriptedLines(
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
        app = offline_session(
            working_directory='.', session_path='session.jsonl', mechanisms=('test-mechanism',),
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
        self.assertIn("Lab · Active session", rendered)
        self.assertIn("Other\n  test-mechanism  Enabled", rendered)
        self.assertIn("trace: empty", rendered)
        self.assertNotIn("\x1b", rendered)
        self.assertEqual(rendered.count("FruitFlyAgent interactive"), 1)

    async def test_resume_picker_switches_session_without_model_submission(self) -> None:

        class ResumeApplication(_TerminalSessionStub):

            def __init__(self) -> None:
                super().__init__(working_directory='/workspace', session_path='/workspace/current.jsonl')
                self.resumed: list[str] = []
                self._status = self.base.status

            @property
            def status(self):
                return self._status


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


        application = ResumeApplication()
        output = io.StringIO()
        frontend = TerminalFrontend(
            application,
            output_stream=output,
            line_editor=ScriptedLines("/resume", "1", "/exit"),
        )

        self.assertEqual(await frontend.run(), 0)
        self.assertEqual(application.resumed, ["/workspace/previous.jsonl"])
        self.assertIn("FruitFlyAgent · resume", output.getvalue())
        self.assertIn("8 messages", output.getvalue())
        self.assertIn("previous.jsonl", output.getvalue())

    async def test_resume_refuses_to_switch_while_work_is_active(self) -> None:

        class BusyApplication(_TerminalSessionStub):
            running = True


            async def resume(self, path):
                raise AssertionError("resume must not run")


        output = io.StringIO()
        frontend = TerminalFrontend(
            BusyApplication(),
            output_stream=output,
            line_editor=ScriptedLines("/resume target.jsonl", "/exit"),
        )

        self.assertEqual(await frontend.run(), 0)
        self.assertIn("finish or /cancel", output.getvalue())

    async def test_resume_explicit_relative_path_uses_workspace(self) -> None:

        class ResumeApplication(_TerminalSessionStub):

            def __init__(self) -> None:
                super().__init__(working_directory='/workspace', session_path='/workspace/current.jsonl')
                self.resumed = None


            async def resume(self, path):
                self.resumed = path


        application = ResumeApplication()
        frontend = TerminalFrontend(
            application,
            output_stream=io.StringIO(),
            line_editor=ScriptedLines(
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
        app = offline_session()
        output = io.StringIO()
        frontend = TerminalFrontend(
            app,
            input_stream=io.StringIO("unused\n"),
            output_stream=output,
            line_editor=ScriptedLines("/exit"),
        )

        self.assertEqual(await frontend.run(), 0)
        self.assertNotIn("you> ", output.getvalue())

    async def test_custom_command_is_rendered_without_reaching_provider(self) -> None:
        provider = FauxProvider()
        app = offline_session(provider=provider)
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
            line_editor=ScriptedLines("/clear", "/exit"),
            command_router=router,
        )

        self.assertEqual(await frontend.run(), 0)
        self.assertIn("cleared\n", output.getvalue())
        self.assertEqual(provider.calls, [])

    async def test_embedded_session_keeps_draft_when_host_cannot_apply_config(self) -> None:
        app = offline_session()
        controller = MockConfiguration(model="offline")
        output = io.StringIO()
        frontend = TerminalFrontend(
            app,
            output_stream=output,
            line_editor=ScriptedLines(
                "/config",
                "3",      # Custom category (after Model and Base prompt)
                "space",  # Enable the mechanism
                "back",
                "back",
                "1",      # Save and apply to this conversation
                "/exit",
            ),
            configuration=controller,
        )

        self.assertEqual(await frontend.run(), 0)
        self.assertFalse(controller.saved)
        self.assertTrue(controller.changed)
        self.assertIn("Apply configuration", output.getvalue())
        self.assertIn("this host cannot apply configuration; draft retained", output.getvalue())

    async def test_config_menu_returns_to_current_session_when_unchanged(self) -> None:
        app = offline_session()
        controller = MockConfiguration(model="offline")
        frontend = TerminalFrontend(
            app,
            output_stream=io.StringIO(),
            line_editor=ScriptedLines("/config", "back", "/exit"),
            configuration=controller,
        )

        self.assertEqual(await frontend.run(), 0)
        self.assertFalse(controller.saved)


