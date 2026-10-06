from __future__ import annotations

import io
import unittest

from fruitfly_agent.interactive import (
    EvaluationBenchmarkOption,
    EvaluationLaunchResult,
    EvaluationModeOption,
    EvaluationMechanismOption,
    EvaluationSnapshot,
    EvaluationVariantOption,
)
from fruitfly_agent.interactive.terminal.evaluation import TerminalEvaluationFrontend
from fruitfly_agent.interactive.terminal.menu import MenuAction, MenuEvent


class _MenuInput:
    def __init__(self, *events: MenuEvent) -> None:
        self.events = iter(events)

    def read_event(self) -> MenuEvent:
        return next(self.events)


class _Controller:
    request = None

    def snapshot(self) -> EvaluationSnapshot:
        return EvaluationSnapshot(
            modes=(EvaluationModeOption("current_setup", "Test current setup", "all"),),
            benchmarks=(
                EvaluationBenchmarkOption(
                    "terminal-bench",
                    "Terminal-Bench",
                    "terminal tasks",
                    "2.0",
                    (
                        EvaluationVariantOption(
                            "smoke",
                            "Low-resource smoke",
                            "one task",
                            True,
                        ),
                    ),
                ),
            ),
            mechanisms=(),
        )

    async def run(self, request, on_event=None):
        self.request = request
        if on_event is not None:
            await on_event({"type": "preflight", "available": True})
            await on_event({
                "type": "agent_event", "condition_id": "current", "trial_id": "trial-1",
                "event": {"type": "assistant_text_delta", "run_id": "run-1", "text": "hello"},
            })
        return EvaluationLaunchResult(
            "completed", "eval-1", "/tmp/report.md", "/tmp/report.json"
        )


class TerminalEvaluationTests(unittest.IsolatedAsyncioTestCase):
    async def test_unavailable_variant_cannot_start_a_paid_run(self) -> None:
        controller = _Controller()
        controller.snapshot = lambda: EvaluationSnapshot(
            modes=(EvaluationModeOption("current_setup", "Test current setup", "all"),),
            benchmarks=(
                EvaluationBenchmarkOption(
                    "terminal-bench",
                    "Terminal-Bench",
                    "terminal tasks",
                    "2.0",
                    (EvaluationVariantOption("smoke", "Smoke", "one task", False, ("start Docker",)),),
                ),
            ),
            mechanisms=(),
        )
        menu = _MenuInput(
            MenuEvent(MenuAction.ACTIVATE),
            MenuEvent(MenuAction.ACTIVATE),
            MenuEvent(MenuAction.ACTIVATE),
        )
        with self.assertRaisesRegex(RuntimeError, "start Docker"):
            await TerminalEvaluationFrontend(
                controller,
                input_stream=io.StringIO(),
                output_stream=io.StringIO(),
                menu_input=menu,
            ).run()
        self.assertIsNone(controller.request)

    async def test_data_driven_flow_launches_selected_benchmark(self) -> None:
        controller = _Controller()
        output = io.StringIO()
        menu = _MenuInput(
            MenuEvent(MenuAction.ACTIVATE),
            MenuEvent(MenuAction.ACTIVATE),
            MenuEvent(MenuAction.ACTIVATE),
            MenuEvent(MenuAction.ACTIVATE, 0),
        )
        result = await TerminalEvaluationFrontend(
            controller,
            input_stream=io.StringIO(),
            output_stream=output,
            menu_input=menu,
        ).run()

        self.assertEqual(result.status, "completed")
        self.assertEqual(controller.request.mode, "current_setup")
        self.assertEqual(controller.request.benchmark_id, "terminal-bench")
        self.assertEqual(controller.request.variant, "smoke")
        self.assertIn("[preflight ready]", output.getvalue())
        self.assertIn("hello", output.getvalue())

    async def test_back_visits_each_parent_and_quit_exits_without_launch(self) -> None:
        controller = _Controller()
        output = io.StringIO()
        menu = _MenuInput(
            MenuEvent(MenuAction.ACTIVATE),  # mode -> benchmark
            MenuEvent(MenuAction.ACTIVATE),  # benchmark -> variant
            MenuEvent(MenuAction.ACTIVATE),  # variant -> confirm
            MenuEvent(MenuAction.BACK),      # confirm -> variant
            MenuEvent(MenuAction.BACK),      # variant -> benchmark
            MenuEvent(MenuAction.BACK),      # benchmark -> mode
            MenuEvent(MenuAction.QUIT),
        )
        result = await TerminalEvaluationFrontend(controller, input_stream=io.StringIO(), output_stream=output, menu_input=menu).run()
        self.assertIsNone(result)
        self.assertIsNone(controller.request)
        titles = [line for line in output.getvalue().splitlines() if line in {"Evaluation", "Benchmark", "Terminal-Bench", "Confirm evaluation"}]
        self.assertEqual(titles, ["Evaluation", "Benchmark", "Terminal-Bench", "Confirm evaluation", "Terminal-Bench", "Benchmark", "Evaluation"])

    async def test_comparison_back_preserves_selection_and_confirmation_defaults_to_back(self) -> None:
        controller = _Controller()
        snapshot = controller.snapshot()
        controller.snapshot = lambda: EvaluationSnapshot(
            modes=(EvaluationModeOption("mechanism_comparison", "Compare", "one mechanism"),),
            benchmarks=snapshot.benchmarks,
            mechanisms=(EvaluationMechanismOption("first", "First"), EvaluationMechanismOption("second", "Second")),
        )
        output = io.StringIO()
        menu = _MenuInput(
            MenuEvent(MenuAction.ACTIVATE), MenuEvent(MenuAction.ACTIVATE), MenuEvent(MenuAction.ACTIVATE),
            MenuEvent(MenuAction.ACTIVATE, 1),  # second mechanism -> confirm
            MenuEvent(MenuAction.ACTIVATE),     # default Back -> mechanism
            MenuEvent(MenuAction.ACTIVATE),     # retained second mechanism
            MenuEvent(MenuAction.ACTIVATE, 0),  # explicit Run
        )
        result = await TerminalEvaluationFrontend(controller, input_stream=io.StringIO(), output_stream=output, menu_input=menu).run()
        self.assertEqual(result.status, "completed")
        self.assertEqual(controller.request.mechanism_id, "second")
        self.assertEqual(output.getvalue().count("Compare a mechanism\n"), 2)

    async def test_quit_from_nested_page_does_not_reopen_parent(self) -> None:
        controller = _Controller()
        menu = _MenuInput(MenuEvent(MenuAction.ACTIVATE), MenuEvent(MenuAction.QUIT))
        result = await TerminalEvaluationFrontend(controller, input_stream=io.StringIO(), output_stream=io.StringIO(), menu_input=menu).run()
        self.assertIsNone(result)
        self.assertIsNone(controller.request)

    async def test_progress_and_agent_tools_are_visible_during_run(self) -> None:
        controller = _Controller()
        output = io.StringIO()

        async def run(request, on_event):
            await on_event({"type": "job_progress", "condition_id": "current", "elapsed_seconds": 5, "completed": 0, "agent_runs_started": 0, "active_agents": 0})
            self.assertIn("Harbor preparing tasks", output.getvalue())
            await on_event({"type": "agent_event", "trial_id": "one", "event": {"type": "tool_started", "run_id": "run-1", "tool_call_id": "call-1", "tool_name": "bash", "arguments": {"command": "ls"}}})
            self.assertIn("bash", output.getvalue())
            await on_event({"type": "job_progress", "condition_id": "current", "elapsed_seconds": 10, "completed": 1, "agent_runs_started": 1, "active_agents": 0})
            self.assertIn("1 trials completed", output.getvalue())
            return EvaluationLaunchResult("completed", "eval-1", "report.md", "report.json")

        controller.run = run
        menu = _MenuInput(*(MenuEvent(MenuAction.ACTIVATE, 0) for _ in range(4)))
        result = await TerminalEvaluationFrontend(controller, input_stream=io.StringIO(), output_stream=output, menu_input=menu).run()
        self.assertEqual(result.status, "completed")

    async def test_evaluation_tool_stream_is_not_subject_to_chat_display_limit(self) -> None:
        output = io.StringIO()
        controller = _Controller()
        text = "tool detail " * 1000

        async def run(request, on_event):
            await on_event({"type": "agent_event", "event": {"type": "tool_output", "run_id": "one", "tool_call_id": "call", "tool_name": "bash", "text": text}})
            return EvaluationLaunchResult("completed", "one", "report.md", "report.json")

        controller.run = run
        menu = _MenuInput(*(MenuEvent(MenuAction.ACTIVATE, 0) for _ in range(4)))
        await TerminalEvaluationFrontend(controller, input_stream=io.StringIO(), output_stream=output, menu_input=menu).run()
        self.assertIn(text, output.getvalue())
        self.assertNotIn("truncated", output.getvalue())

    async def test_eval_logs_and_trial_errors_are_not_truncated(self) -> None:
        from fruitfly_agent.interactive.terminal.renderer import TerminalRenderer
        output = io.StringIO()
        frontend = TerminalEvaluationFrontend(_Controller(), input_stream=io.StringIO(), output_stream=output)
        renderer = TerminalRenderer(output)
        text = "install output " * 1000 + "final detail\n"
        await frontend._show_event(renderer, {"type": "log", "source": "job/trial/agent/setup.log", "condition_id": "current", "text": text})
        await frontend._show_event(renderer, {"type": "trial_finished", "error": {"exception_type": "AgentSetupTimeoutError", "exception_message": "setup timed out"}})
        await renderer.close()
        self.assertIn(text, output.getvalue())
        self.assertIn("AgentSetupTimeoutError", output.getvalue())
        self.assertIn("setup timed out", output.getvalue())

    async def test_log_chunks_preserve_lines_without_repeated_source_headers(self) -> None:
        from fruitfly_agent.interactive.terminal.renderer import TerminalRenderer
        output = io.StringIO()
        frontend = TerminalEvaluationFrontend(_Controller(), input_stream=io.StringIO(), output_stream=output)
        renderer = TerminalRenderer(output)
        text = "│ trace line " + "x" * 9000 + " │\nfinal partial line"
        for start in range(0, len(text), 4096):
            await frontend._show_event(renderer, {"type": "log", "source": "harbor.log", "condition_id": "current", "text": text[start:start+4096]})
        await frontend._show_event(renderer, {"type": "log", "source": "exception.txt", "condition_id": "current", "text": "exception\n"})
        await renderer.close()
        self.assertIn(text, output.getvalue())
        self.assertEqual(output.getvalue().count("[condition current · harbor.log]"), 1)
        self.assertIn("final partial line\n[condition current · exception.txt]", output.getvalue())


if __name__ == "__main__":
    unittest.main()
