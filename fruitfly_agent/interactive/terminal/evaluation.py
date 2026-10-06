"""Generic terminal flow for selecting and launching an evaluation."""

from __future__ import annotations

import sys
from typing import Any, Mapping, TextIO

from ..evaluation import (
    EvaluationController,
    EvaluationLaunchRequest,
    EvaluationLaunchResult,
)
from ..events import event_from_dict
from .input import LineEditor, create_line_editor
from .menu import MenuAction, MenuInput, MenuRow, TerminalMenuRenderer, create_menu_input
from .renderer import TerminalRenderer
from .screen import transient_screen


class TerminalEvaluationFrontend:
    def __init__(
        self,
        controller: EvaluationController,
        *,
        input_stream: TextIO | None = None,
        output_stream: TextIO | None = None,
        line_editor: LineEditor | None = None,
        menu_input: MenuInput | None = None,
    ) -> None:
        self.controller = controller
        self.input = input_stream or sys.stdin
        self.output = output_stream or sys.stdout
        self.line_editor = line_editor or create_line_editor(self.input, self.output)
        self.menu_input = menu_input or create_menu_input(
            self.input, self.output, self.line_editor
        )
        self.renderer = TerminalMenuRenderer(self.output)
        self._log_source: tuple[object, object] | None = None

    async def run(self) -> EvaluationLaunchResult | None:
        with transient_screen(self.input, self.output):
            request = self._select_request()
        if request is None:
            return None
        renderer = TerminalRenderer(self.output, tool_output_limit=None)
        renderer.write_system("\n[evaluation started; Agent session is isolated]\n")
        try:
            return await self.controller.run(
                request,
                on_event=lambda event: self._show_event(renderer, event),
            )
        finally:
            await renderer.close()

    def _select_request(self) -> EvaluationLaunchRequest | None:
        snapshot = self.controller.snapshot()
        page = "mode"
        choices: dict[str, int] = {}
        while True:
            mode = snapshot.modes[choices.get("mode", 0)] if snapshot.modes else None
            benchmark = (
                snapshot.benchmarks[choices.get("benchmark", 0)]
                if snapshot.benchmarks else None
            )
            if page == "mode":
                title = "Evaluation"
                subtitle = "Choose what to measure. Runs use an independent process and session."
                rows = tuple(MenuRow(item.label, item.description) for item in snapshot.modes)
                previous, following = None, "benchmark"
            elif page == "benchmark":
                title, subtitle = "Benchmark", "Choose a standardized benchmark adapter."
                rows = tuple(
                    MenuRow(item.label, f"{item.version} · {item.description}")
                    for item in snapshot.benchmarks
                )
                previous, following = "mode", "variant"
            elif page == "variant":
                assert benchmark is not None and mode is not None
                title = benchmark.label
                subtitle = "Choose one resource profile. Availability is determined by Harbor preflight."
                rows = tuple(
                    MenuRow(
                        item.label,
                        item.description if item.available else f"Unavailable · {'; '.join(item.preflight)}",
                        marker="✓" if item.available else "!",
                    )
                    for item in benchmark.variants
                )
                previous = "benchmark"
                following = "mechanism" if mode.mode_id == "mechanism_comparison" else "confirm"
            elif page == "mechanism":
                title = "Compare a mechanism"
                subtitle = "Baseline removes exactly one active mechanism; all other conditions stay fixed."
                rows = tuple(MenuRow(item.label, item.mechanism_id) for item in snapshot.mechanisms)
                if not rows:
                    rows = (MenuRow("Back", "No active optional mechanism can be compared."),)
                previous, following = "variant", "confirm"
            else:
                assert benchmark is not None and mode is not None
                variant = benchmark.variants[choices["variant"]]
                title = "Confirm evaluation"
                subtitle = f"{mode.label} · {benchmark.label} / {variant.label}. Provider requests may incur cost."
                rows = (
                    MenuRow("Run", "Create a frozen plan and start the isolated runner"),
                    MenuRow("Back", "Return to the previous selection"),
                )
                previous = "mechanism" if mode.mode_id == "mechanism_comparison" else "variant"
                following = None
            choice = self._choose(
                title, subtitle, rows,
                selected=choices.get(page, 1 if page == "confirm" else 0),
            )
            if choice == MenuAction.QUIT:
                return None
            if (
                choice is None
                or (page == "confirm" and choice == 1)
                or (page == "mechanism" and not snapshot.mechanisms)
            ):
                if previous is None:
                    return None
                page = previous
                continue
            old_choice = choices.get(page)
            choices[page] = choice
            if page == "benchmark" and old_choice != choice:
                choices.pop("variant", None)
            if page == "variant":
                assert benchmark is not None
                variant = benchmark.variants[choice]
                if not variant.available:
                    raise RuntimeError(
                        f"{benchmark.label} / {variant.label} is unavailable: "
                        + "; ".join(variant.preflight)
                    )
            if page == "confirm":
                assert mode is not None and benchmark is not None
                return EvaluationLaunchRequest(
                    mode=mode.mode_id,
                    benchmark_id=benchmark.benchmark_id,
                    variant=benchmark.variants[choices["variant"]].variant_id,
                    mechanism_id=(snapshot.mechanisms[choices["mechanism"]].mechanism_id if mode.mode_id == "mechanism_comparison" else None),
                )
            assert following is not None
            page = following

    async def _show_event(
        self, renderer: TerminalRenderer, event: Mapping[str, Any]
    ) -> None:
        event_type = event.get("type")
        if event_type != "log":
            self._log_source = None
        if event_type == "agent_event":
            payload = event.get("event")
            if isinstance(payload, Mapping):
                if payload.get("type") == "run_started":
                    renderer.write_system(
                        f"\n[trial {event.get('trial_id', '?')} · "
                        f"{event.get('condition_id', '?')}]\n"
                    )
                    prompt = payload.get("prompt")
                    if isinstance(prompt, str):
                        renderer.write_user_input(prompt)
                try:
                    await renderer.render(event_from_dict(payload))
                except (TypeError, ValueError):
                    pass
        elif event_type == "log":
            source = (event.get("condition_id", "?"), event.get("source", "eval"))
            if self._log_source != source:
                renderer.write_system(f"[condition {source[0]} · {source[1]}]\n")
                self._log_source = source
            renderer.write_log(str(event.get("text", "")))
        elif event_type == "planned":
            renderer.write_system(f"[plan {event.get('evaluation_id', '?')}]\n")
        elif event_type == "preflight":
            renderer.write_system(
                "[preflight ready]\n" if event.get("available") else "[preflight blocked]\n"
            )
        elif event_type == "job_started":
            renderer.write_system(
                f"[condition {event.get('condition_index', '?')}/"
                f"{event.get('condition_total', '?')}: {event.get('condition_id', '?')} "
                "· Harbor job running]\n"
                f"[artifacts: {event.get('artifacts_path', 'unknown')}]\n"
            )
        elif event_type == "job_progress":
            stage = (
                "Harbor preparing tasks / waiting for Agent events"
                if not event.get("agent_runs_started")
                else "Agent execution / verification"
            )
            renderer.write_system(
                f"[condition {event.get('condition_id', '?')} · "
                f"{event.get('elapsed_seconds', 0)}s elapsed · "
                f"{event.get('completed', 0)} trials completed · "
                f"{event.get('active_agents', 0)} Agent runs active · "
                f"{stage}]\n"
            )
        elif event_type == "job_finished":
            renderer.write_system(
                f"[condition {event.get('condition_id', '?')} finished · "
                f"{event.get('completed', '?')} trials collected]\n"
            )
        elif event_type == "trial_finished":
            renderer.write_system(
                f"[condition {event.get('condition_id', '?')} · "
                f"{event.get('completed', '?')} trials completed]\n"
            )
            error = event.get("error")
            if isinstance(error, Mapping):
                renderer.write_system(
                    f"[trial error: {error.get('exception_type', 'Error')}]\n"
                    + str(error.get("exception_message", "")) + "\n"
                )
        elif event_type == "report_written":
            renderer.write_system("[report written]\n")

    def _choose(
        self,
        title: str,
        subtitle: str,
        rows: tuple[MenuRow, ...],
        *,
        selected: int = 0,
    ) -> int | MenuAction | None:
        if not rows:
            return None
        selected = min(selected, len(rows) - 1)
        while True:
            self.renderer.render(
                title=title,
                subtitle=subtitle,
                rows=rows,
                selected=selected,
                instructions="↑↓ move · Enter select · Esc back · q quit",
            )
            event = self.menu_input.read_event()
            if event.index is not None and 0 <= event.index < len(rows):
                selected = event.index
            elif event.action == MenuAction.UP:
                selected = (selected - 1) % len(rows)
                continue
            elif event.action == MenuAction.DOWN:
                selected = (selected + 1) % len(rows)
                continue
            if event.action == MenuAction.QUIT:
                return MenuAction.QUIT
            if event.action == MenuAction.BACK:
                return None
            if event.action == MenuAction.ACTIVATE:
                return selected



__all__ = ["TerminalEvaluationFrontend"]
