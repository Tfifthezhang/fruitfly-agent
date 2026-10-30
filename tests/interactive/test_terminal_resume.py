"""Terminal resume behavior and failure contracts."""
from __future__ import annotations
from dataclasses import replace
import io
from pathlib import Path
import unittest
from fruitfly_agent.interactive import ResumableSession, TerminalFrontend
from tests.support.terminal import ScriptedLines

from tests.support.terminal import TerminalSessionStub


class TerminalFrontendTest(unittest.IsolatedAsyncioTestCase):
    async def test_resume_picker_switches_session_without_model_submission(self) -> None:

        class ResumeApplication(TerminalSessionStub):

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

        class BusyApplication(TerminalSessionStub):
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

        class ResumeApplication(TerminalSessionStub):

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
