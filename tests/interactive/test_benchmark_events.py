"""Full original-task event rendering in the unified improvement menu."""
import io
import unittest
from fruitfly_agent.interactive.terminal.features.improvement.events import BenchmarkEventDisplay
from fruitfly_agent.interactive.terminal.rendering.renderer import TerminalRenderer


class BenchmarkEventTests(unittest.IsolatedAsyncioTestCase):
    async def test_progress_and_agent_tools_are_visible(self):
        output = io.StringIO()
        renderer = TerminalRenderer(output, tool_output_limit=None)
        display = BenchmarkEventDisplay()
        try:
            await display.show_event(renderer, {"type": "job_progress", "job_id": "current", "completed": 0})
            self.assertIn("Harbor preparing tasks", output.getvalue())
            await display.show_event(renderer, {"type": "agent_event", "trial_id": "one", "event": {
                "type": "tool_started", "run_id": "one", "tool_call_id": "call", "tool_name": "bash", "arguments": {"command": "ls"}}})
            self.assertIn("bash", output.getvalue())
            await display.show_event(renderer, {"type": "job_progress", "job_id": "current", "completed": 1, "agent_runs_started": 1})
            self.assertIn("1 trials completed", output.getvalue())
        finally:
            await renderer.close()

    async def test_original_task_tool_stream_is_not_truncated(self):
        output = io.StringIO()
        renderer = TerminalRenderer(output, tool_output_limit=None)
        display = BenchmarkEventDisplay()
        text = "tool detail " * 1000
        try:
            await display.show_event(renderer, {"type": "agent_event", "event": {
                "type": "tool_output", "run_id": "one", "tool_call_id": "call", "tool_name": "bash", "text": text}})
        finally:
            await renderer.close()
        self.assertIn(text, output.getvalue())
        self.assertNotIn("truncated", output.getvalue())

    async def test_eval_logs_and_trial_errors_are_not_truncated(self) -> None:
        from fruitfly_agent.interactive.terminal.rendering.renderer import TerminalRenderer
        output = io.StringIO()
        display = BenchmarkEventDisplay()
        renderer = TerminalRenderer(output)
        text = "install output " * 1000 + "final detail\n"
        await display.show_event(renderer, {"type": "log", "source": "job/trial/agent/setup.log", "job_id": "current", "text": text})
        await display.show_event(renderer, {"type": "trial_finished", "error": {"exception_type": "AgentSetupTimeoutError", "exception_message": "setup timed out"}})
        await renderer.close()
        self.assertIn(text, output.getvalue())
        self.assertIn("AgentSetupTimeoutError", output.getvalue())
        self.assertIn("setup timed out", output.getvalue())

    async def test_log_chunks_preserve_lines_without_repeated_source_headers(self) -> None:
        from fruitfly_agent.interactive.terminal.rendering.renderer import TerminalRenderer
        output = io.StringIO()
        display = BenchmarkEventDisplay()
        renderer = TerminalRenderer(output)
        text = "│ trace line " + "x" * 9000 + " │\nfinal partial line"
        for start in range(0, len(text), 4096):
            await display.show_event(renderer, {"type": "log", "source": "harbor.log", "job_id": "current", "text": text[start:start+4096]})
        await display.show_event(renderer, {"type": "log", "source": "exception.txt", "job_id": "current", "text": "exception\n"})
        await renderer.close()
        self.assertIn(text, output.getvalue())
        self.assertEqual(output.getvalue().count("[job current · harbor.log]"), 1)
        self.assertIn("final partial line\n[job current · exception.txt]", output.getvalue())
