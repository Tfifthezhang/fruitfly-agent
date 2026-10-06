"""Input loop for the built-in line-oriented terminal adapter."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
import sys
import textwrap
from typing import Protocol, TextIO

from ..models import InteractiveStatus
from ..optimization import OptimizationClient, CandidateActivationClient, TaskPackClient, format_optimization_activity
from ..dispatch import EventSink

from ..configuration import ConfigurationController
from ..evaluation import EvaluationController
from ..commands import CommandRouter, parse_command
from .configuration import TerminalConfigurationFrontend
from .evaluation import TerminalEvaluationFrontend
from .input import LineEditor, create_line_editor
from .live import InlineTerminalDisplay, create_inline_terminal
from .renderer import TerminalRenderer
from .resume import TerminalResumeFrontend
from .screen import transient_screen
from .menu import MenuAction, MenuRow


class TerminalSession(Protocol):
    @property
    def status(self) -> InteractiveStatus: ...
    @property
    def running(self) -> bool: ...
    def set_event_sink(self, sink: EventSink | None) -> None: ...
    def steer(self, prompt: str) -> bool: ...
    def cancel(self) -> bool: ...
    async def submit(self, prompt: str): ...


class TerminalFrontend:
    """Route terminal input while delegating state and rendering."""

    def __init__(
        self,
        session: TerminalSession,
        *,
        input_stream: TextIO | None = None,
        output_stream: TextIO | None = None,
        renderer: TerminalRenderer | None = None,
        line_editor: LineEditor | None = None,
        command_router: CommandRouter | None = None,
        configuration: ConfigurationController | None = None,
        evaluation: EvaluationController | None = None,
    ) -> None:
        self.session = session
        self._last_optimization_notice = 0
        self._last_optimization_activity = None
        self.input = input_stream or sys.stdin
        self.output = output_stream or sys.stdout
        self._inline_display: InlineTerminalDisplay | None = None
        if renderer is None and line_editor is None:
            isolated = create_inline_terminal(self.input, self.output)
            if isolated is not None:
                self._inline_display, line_editor = isolated
                renderer = TerminalRenderer(self._inline_display)
        self.renderer = renderer or TerminalRenderer(self.output)
        self.line_editor = line_editor or create_line_editor(self.input, self.output)
        if command_router is not None and configuration is not None:
            raise ValueError("pass command_router or configuration, not both")
        self.configuration = configuration or getattr(session, "configuration", None)
        self.menu_input = None
        self.menu_renderer = None
        if isinstance(session, OptimizationClient):
            from .menu import create_menu_input, TerminalMenuRenderer
            self.menu_input = create_menu_input(self.input, self.output, self.line_editor)
            self.menu_renderer = TerminalMenuRenderer(self.output)
        self.evaluation = evaluation
        self.command_router = command_router or CommandRouter()
        self.session.set_event_sink(self.renderer.render)

    async def run(self) -> int:
        try:
            self._activate_inline_terminal()
            self.renderer.show_welcome(self.session.status)
            self._show_candidate_notice()
            return await self._run_loop()
        finally:
            try:
                await self.renderer.close()
            finally:
                try:
                    self.renderer.finish_line()
                finally:
                    self._suspend_inline_terminal()

    async def _run_loop(self) -> int:
        while True:
            await asyncio.sleep(0)
            self._show_optimization_activity()
            self._show_optimization_notice()
            self._show_candidate_notice()
            line = await self._read_prompt_line()
            if line is None:
                self.renderer.finish_line()
                wait = getattr(self.session, "wait_until_idle", None)
                if wait is not None:
                    await wait()
                return 0
            submitted = line.rstrip("\r\n")
            text = submitted.strip()
            if not text:
                continue
            if self._inline_display is not None:
                self.renderer.write_user_input(submitted)
            command = parse_command(text)
            if command is None:
                if bool(getattr(self.session, "running", False)) and self.session.steer(text):
                    self.renderer.write_system("message added to current run\n")
                    continue
                enqueue = getattr(self.session, "enqueue", None)
                if enqueue is None:
                    await self.session.submit(text)
                else:
                    was_running = bool(getattr(self.session, "running", False))
                    try:
                        position = enqueue(text)
                    except (RuntimeError, ValueError) as exc:
                        self.renderer.write_system(f"cannot submit: {exc}\n")
                        continue
                    if was_running or position > 1:
                        self.renderer.write_system(
                            f"queued prompt ({position} pending)\n"
                        )
                    wait = getattr(self.session, "wait_until_idle", None)
                    if wait is not None and self._inline_display is None:
                        # A readline frame and streamed model output cannot safely
                        # own the same cursor in the fallback path.  A real ANSI
                        # terminal uses isolated output and input regions instead.
                        await wait()
                if self._inline_display is None:
                    self.renderer.finish_line()
                continue
            if command.name == "cancel":
                if command.arguments:
                    self.renderer.write_system("usage: /cancel\n")
                elif self.session.cancel():
                    self.renderer.write_system("cancellation requested\n")
                else:
                    self.renderer.write_system("no active run\n")
                continue
            if command.name == "optimize" and isinstance(self.session, OptimizationClient):
                await self._optimize(command.arguments)
                continue
            if command.name in {"candidates", "candidate"}:
                self.renderer.write_system(f"unknown command: /{command.name}; use /optimize\n")
                continue
            if command.name == "config" and self.configuration is not None:
                if command.arguments:
                    self.renderer.write_system(
                        "usage: /config (opens the configuration menu)\n"
                    )
                    continue
                if getattr(self.session, "running", False) or getattr(
                    self.session,
                    "pending_count",
                    0,
                ):
                    self.renderer.write_system(
                        "finish or /cancel the active run before changing config\n"
                    )
                    continue
                if self._inline_display is not None:
                    self._suspend_inline_terminal()
                try:
                    with transient_screen(self.input, self.output):
                        result = TerminalConfigurationFrontend(
                            self.configuration,
                            input_stream=self.input,
                            output_stream=self.output,
                            line_editor=self.line_editor,
                            active_prompt_label=getattr(self.session.status, "prompt_label", ""),
                        ).run_for_active_session()
                    if result.start:
                        rebuild = getattr(self.session, "rebuild", None)
                        if rebuild is None:
                            self.renderer.write_system(
                                "configuration saved; the embedding host must open "
                                "a new runtime\n"
                            )
                            return 0
                        await rebuild()
                        self.configuration = getattr(
                            self.session,
                            "configuration",
                            self.configuration,
                        )
                    self._activate_inline_terminal()
                    if result.start:
                        self.renderer.write_system("\n[new session]\n")
                        self.renderer.show_welcome(self.session.status)
                finally:
                    if (
                        self._inline_display is not None
                        and not self._inline_display.active
                    ):
                        self._activate_inline_terminal()
                continue
            if command.name == "resume" and hasattr(self.session, "resume"):
                await self._resume(command.arguments)
                continue
            if command.name == "eval" and self.evaluation is not None:
                if command.arguments:
                    self.renderer.write_system("usage: /eval\n")
                    continue
                if getattr(self.session, "running", False) or getattr(
                    self.session, "pending_count", 0
                ):
                    self.renderer.write_system(
                        "finish or /cancel the active run before starting eval\n"
                    )
                    continue
                if self._inline_display is not None:
                    self._suspend_inline_terminal()
                try:
                    result = await TerminalEvaluationFrontend(
                        self.evaluation,
                        input_stream=self.input,
                        output_stream=self.output,
                        line_editor=self.line_editor,
                    ).run()
                except (OSError, RuntimeError, TypeError, ValueError) as exc:
                    result = None
                    self.renderer.write_system(f"could not run evaluation: {exc}\n")
                finally:
                    if self._inline_display is not None:
                        self._activate_inline_terminal()
                if result is not None:
                    self.renderer.write_system(
                        f"\n[evaluation {result.status}: {result.evaluation_id}]\n"
                        f"report: {result.report_markdown}\n"
                        f"json: {result.report_json}\n"
                    )
                continue
            result = self.command_router.execute(command, self.session)
            if result.text:
                self.renderer.write_system(result.text)
            if result.should_exit:
                return 0

    async def _read_prompt_line(self):
        if self._inline_display is None:
            # The fallback line editor owns the cursor until input is submitted.
            return await asyncio.to_thread(self.line_editor.read_line)
        reader = asyncio.create_task(asyncio.to_thread(self.line_editor.read_line))
        try:
            while not reader.done():
                await asyncio.wait({reader}, timeout=0.5)
                self._show_optimization_activity()
                self._show_optimization_notice()
                self._show_candidate_notice()
            return await reader
        finally:
            if not reader.done():
                reader.cancel()

    def _show_optimization_activity(self):
        progress = getattr(self.session, "optimization_progress", None)
        if progress is None or progress.status != "running" or progress.activity is None:
            return
        identity = (progress.sequence, progress.activity)
        if identity == self._last_optimization_activity:
            return
        self._last_optimization_activity = identity
        self.renderer.write_system("[optimization] " + _safe_terminal_text(format_optimization_activity(progress.activity)) + "\n")

    def _show_optimization_notice(self):
        progress = getattr(self.session, "optimization_progress", None)
        if progress is None or progress.status in {"idle", "running"} or progress.sequence == self._last_optimization_notice:
            return
        self._last_optimization_notice = progress.sequence
        self.renderer.write_system(f"Optimization {progress.status}" +
                                   (f": {_safe_terminal_text(progress.error)}" if progress.error else "") + "\n")

    def _show_candidate_notice(self) -> None:
        if getattr(self.session, "running", False) or getattr(self.session, "pending_count", 0):
            return
        peek = getattr(self.session, "candidate_notice", None)
        acknowledge = getattr(self.session, "acknowledge_candidate_notice", None)
        if peek is None or acknowledge is None:
            return
        try:
            candidate_ids = peek()
            if candidate_ids:
                self.renderer.write_system(
                    f"\n[{len(candidate_ids)} candidate(s) ready; not active. "
                    "Use /optimize to review.]\n"
                )
                acknowledge(candidate_ids)
        except (OSError, ValueError, RuntimeError) as exc:
            self.renderer.write_system(f"candidate notice unavailable: {exc}\n")

    async def _optimize(self, arguments: tuple[str, ...]) -> None:
        if self.menu_input is None or self.menu_renderer is None:
            self.renderer.write_system("optimization menu unavailable\n")
            return
        direction = " ".join(arguments).strip()
        selected = 0
        while True:
            progress = getattr(self.session, "optimization_progress", None)
            running = progress is not None and progress.status == "running"
            try:
                candidates = self.session.candidates()
            except (OSError, RuntimeError, TypeError, ValueError):
                candidates = ()
            pending = sum(item.status in {"proposed", "reviewed", "deferred", "selected_for_next_session"} for item in candidates)
            rows = (
                MenuRow("Start optimization", "Enter an improvement direction", marker="!" if running else ""),
                MenuRow("Review candidates", f"{pending} pending · {len(candidates)} total"),
                *((MenuRow("Save a failed task", "Correct a completed answer and add it to training"),) if (isinstance(self.session, TaskPackClient) and self.session.task_packs_available) else ()),
                MenuRow("Return to chat"),
            )
            self.menu_renderer.render(
                title="Optimization",
                subtitle=(f"Search {progress.status}" if running else "Search and review proposed changes"),
                rows=rows, selected=selected,
                instructions="↑↓ move · Enter select · Esc back · q close menu" if self.menu_renderer.ansi else "Enter an option number; blank selects highlighted; q closes the menu",
            )
            event = self.menu_input.read_event()
            selected, handled = _menu_navigate(event, selected, len(rows))
            if handled:
                continue
            if event.action in {MenuAction.BACK, MenuAction.QUIT} or (event.action == MenuAction.ACTIVATE and selected == len(rows) - 1):
                return
            if event.action != MenuAction.ACTIVATE:
                continue
            if selected == 0:
                if running:
                    self.renderer.write_system("optimization is already running; use /status or /cancel\n")
                    continue
                await self._start_optimization_flow(direction)
                return
            elif selected == 1:
                await self._review_candidates_flow()
                return
            else:
                await self._save_correction_flow()
                return

    async def _start_optimization_flow(self, direction: str, *, pack_id=None) -> None:
        default_direction = ""
        if pack_id is None and (isinstance(self.session, TaskPackClient) and self.session.task_packs_available):
            try:
                packs = self.session.task_packs()
                if packs:
                    choice = self._choose_row("Choose task package", tuple(MenuRow(_safe_terminal_text(p.name),
                        _safe_terminal_text(p.error) if p.error else f"{p.train_count} training · {p.validation_count} validation · {p.holdout_count} holdout") for p in packs))
                    if choice is None:
                        return
                    pack = packs[choice]
                    if pack.error:
                        self.renderer.write_system(f"Cannot search: {_safe_terminal_text(pack.error)}\n")
                        return
                    pack_id = pack.pack_id
                    default_direction = pack.default_direction
            except (OSError, RuntimeError, TypeError, ValueError) as exc:
                self.renderer.write_system(f"Task packages unavailable: {_safe_terminal_text(str(exc))}\n")
                return
        if pack_id and not default_direction and isinstance(self.session, TaskPackClient) and self.session.task_packs_available:
            default_direction = next((p.default_direction for p in self.session.task_packs() if p.pack_id == pack_id), "")
        if not direction:
            self.renderer.write_system("Improvement direction" + (f" (blank uses {_safe_terminal_text(default_direction)})" if default_direction else "") + ": ")
            value = await asyncio.to_thread(self.line_editor.read_line)
            if value is None:
                self.renderer.write_system("\nSearch cancelled.\n")
                return
            direction = value.strip() or default_direction
        if not direction or len(direction) > 500:
            self.renderer.write_system("Search cancelled; direction must contain 1–500 characters.\n")
            return
        try:
            preview = self.session.optimization_preview(pack_id=pack_id, direction=direction)
        except (OSError, RuntimeError, TypeError, ValueError) as exc:
            self.renderer.write_system(f"cannot start optimization: {exc}\n")
            return
        rows = (MenuRow("Start search", f"{_safe_terminal_text(preview.label)} · {_safe_terminal_text(preview.target)}"), MenuRow("Cancel"))
        detail = _safe_terminal_text(preview.cost_notice) + "\n" + "\n".join(
            f"{_safe_terminal_text(key)}: {_safe_terminal_text(value)}" for key, value in preview.details
        )
        if not self._confirm_choice(title="Confirm optimization", subtitle=detail, rows=rows):
            self.renderer.write_system("Search cancelled; no model calls made.\n")
            return
        try:
            self.session.start_optimization(direction, preview_token=preview.preview_token)
            self.renderer.write_system("Optimization submitted; use /status or /cancel.\n")
        except (OSError, RuntimeError, TypeError, ValueError) as exc:
            self.renderer.write_system(f"could not start optimization: {exc}\n")

    def _confirm_choice(self, *, title: str, subtitle: str, rows: tuple[MenuRow, ...]) -> bool:
        """Render the actual selection throughout an explicit confirmation."""
        selected = 1
        instructions = ("↑↓ move · Enter select · Esc cancel" if self.menu_renderer.ansi
                        else "Enter an option number; blank selects highlighted; q cancels")
        while True:
            self.menu_renderer.render(title=title, subtitle=subtitle, rows=rows,
                                      selected=selected, instructions=instructions)
            event = self.menu_input.read_event()
            selected, handled = _menu_navigate(event, selected, len(rows))
            if handled:
                continue
            if event.action in {MenuAction.BACK, MenuAction.QUIT}:
                return False
            if event.action == MenuAction.ACTIVATE:
                return selected == 0

    def _choose_row(self, title, rows, *, subtitle=""):
        rows = (*rows, MenuRow("Back"))
        selected = 0
        while True:
            self.menu_renderer.render(title=title, subtitle=subtitle, rows=rows, selected=selected)
            event = self.menu_input.read_event()
            selected, handled = _menu_navigate(event, selected, len(rows))
            if handled:
                continue
            if event.action in {MenuAction.BACK, MenuAction.QUIT}:
                return None
            if event.action == MenuAction.ACTIVATE:
                return None if selected == len(rows) - 1 else selected

    async def _ask_correction(self, prompt):
        self.renderer.write_system(prompt)
        return await asyncio.to_thread(self.line_editor.read_line)

    async def _save_correction_flow(self):
        try:
            tasks = self.session.correction_tasks()
            if not tasks:
                self.renderer.write_system("No completed text tasks available.\n")
                return
            choice = self._choose_row("Choose completed task", tuple(MenuRow(
                _safe_terminal_text(t.input[:100]), _safe_terminal_text(t.output[:100])) for t in tasks))
            if choice is None:
                return
            task = tasks[choice]
            packs = self.session.task_packs()
            choice = self._choose_row("Save to task package", (*tuple(MenuRow(
                _safe_terminal_text(p.name), "Writable" if p.writable else "Save a workspace copy") for p in packs),
                MenuRow("Create task package", "Independent validation must be added before searching")))
            if choice is None:
                return
            pack = packs[choice] if choice < len(packs) else None
            name = ""
            if pack is None:
                name = await self._ask_correction("New task package name: ")
                if name is None or not name.strip():
                    return
                name = name.strip()
            self.renderer.write_system("Make the question self-contained; include any facts needed from earlier messages or tools.\n")
            edited = await self._ask_correction("Question (blank keeps the original): ")
            if edited is None:
                return
            question = edited.strip() or task.input
            acceptance = None
            if pack is not None and pack.acceptance_example:
                answer = await self._ask_correction(f"Acceptance JSON (example {_safe_terminal_text(pack.acceptance_example)}): ")
                if answer is None or not answer.strip():
                    self.renderer.write_system("Save cancelled; acceptance is required.\n")
                    return
                def unique_object(pairs):
                    result = {}
                    for key, value in pairs:
                        if key in result:
                            raise ValueError("duplicate acceptance JSON field: " + key)
                        result[key] = value
                    return result
                acceptance = json.loads(answer, object_pairs_hook=unique_object)
                if not isinstance(acceptance, dict):
                    raise ValueError("acceptance must be a JSON object")
            else:
                answer = await self._ask_correction("Correct answer (required): ")
                if answer is None or not answer.strip():
                    self.renderer.write_system("Save cancelled; a correct answer is required.\n")
                    return
            reason = await self._ask_correction("Reason (optional, stored as metadata): ")
            if reason is None:
                return
            copy = pack is not None and not pack.writable
            detail = (f"Question: {_safe_terminal_text(question)}\n"
                      + (f"Correct answer: {_safe_terminal_text(answer)}\n" if acceptance is None else "")
                      + f"Package: {_safe_terminal_text(pack.name if pack else name)}\n"
                      + ("A writable workspace copy will be created.\n" if copy else "")
                      + (f"Acceptance: {_safe_terminal_text(json.dumps(acceptance, ensure_ascii=False))}\n" if acceptance is not None else "")
                      + "Only training changes. No model calls. Confirm the question is self-contained.")
            if not self._confirm_choice(title="Confirm training task", subtitle=detail,
                    rows=(MenuRow("Save task"), MenuRow("Cancel"))):
                self.renderer.write_system("Save cancelled.\n")
                return
            options = dict(expected_hash=pack.source_hash if pack else "", name=name,
                           reason=reason.strip(), copy=copy, acceptance=acceptance)
            try:
                saved = self.session.save_training_task(task.task_id, pack.pack_id if pack else "", question, answer.strip(), **options)
            except ValueError as exc:
                if "conflicting training answer" not in str(exc):
                    raise
                if not self._confirm_choice(title="Training answer already exists", subtitle="Replace its acceptance criteria?",
                        rows=(MenuRow("Replace answer"), MenuRow("Cancel"))):
                    return
                saved = self.session.save_training_task(task.task_id, pack.pack_id, question, answer.strip(), replace=True, **options)
            self.renderer.write_system(f"Saved to {_safe_terminal_text(saved.name)} · {saved.train_count} training cases.\n")
            if saved.error:
                self.renderer.write_system(f"Before searching: {_safe_terminal_text(saved.error)}.\n")
                return
            choice = self._choose_row("Task saved", (MenuRow("Return to chat"), MenuRow("Optimize this package")))
            if choice == 1:
                await self._start_optimization_flow("", pack_id=saved.pack_id)
        except (OSError, RuntimeError, TypeError, ValueError) as exc:
            self.renderer.write_system(f"Cannot save task: {_safe_terminal_text(str(exc))}\n")

    async def _review_candidates_flow(self) -> None:
        selected = 0
        page = 0
        page_size = 10
        while True:
            try:
                records = self.session.candidates()
            except (OSError, RuntimeError, TypeError, ValueError) as exc:
                self.renderer.write_system(f"candidate inbox unavailable: {exc}\n")
                return
            if not records:
                self.menu_renderer.render(title="Optimization candidates", subtitle="No saved candidates", rows=(MenuRow("Back"),), selected=0)
                event = self.menu_input.read_event()
                if event.action in {MenuAction.ACTIVATE, MenuAction.BACK, MenuAction.QUIT}:
                    return
                continue
            page_count = max(1, (len(records) + page_size - 1) // page_size)
            page = min(page, page_count - 1)
            start = page * page_size
            shown = records[start:start + page_size]
            rows = []
            row_actions = []
            if page > 0:
                rows.append(MenuRow("Previous page"))
                row_actions.append(("page", page - 1))
            for offset, item in enumerate(shown):
                rows.append(MenuRow(f"{item.candidate_id[:10]} · {item.algorithm} · {item.target}", _candidate_status(item.status)))
                row_actions.append(("candidate", start + offset))
            if page + 1 < page_count:
                rows.append(MenuRow("Next page"))
                row_actions.append(("page", page + 1))
            rows.append(MenuRow("Back"))
            row_actions.append(("back", None))
            selected = min(selected, len(rows) - 1)
            self.menu_renderer.render(title="Optimization candidates", subtitle=f"Select a result to inspect its changes · page {page + 1}/{page_count}", rows=tuple(rows), selected=selected)
            event = self.menu_input.read_event()
            selected, handled = _menu_navigate(event, selected, len(rows))
            if handled:
                continue
            if event.action in {MenuAction.BACK, MenuAction.QUIT}:
                return
            if event.action != MenuAction.ACTIVATE:
                continue
            action, value = row_actions[selected]
            if action == "back":
                return
            if action == "page":
                page = value
                selected = 0
                continue
            await self._candidate_detail_flow(records[value].candidate_id)
            return

    async def _candidate_detail_flow(self, candidate_id: str) -> None:
        try:
            record, diff = self.session.candidate_detail(candidate_id)
        except (OSError, RuntimeError, TypeError, ValueError) as exc:
            self.renderer.write_system(f"candidate unavailable: {exc}\n")
            return
        lines = diff.splitlines() or ["(no textual difference)"]
        page = 0
        page_size = 8
        selected = None
        sections = getattr(record, 'sections', ())
        section_index = next((i for i, section in enumerate(sections) if section.initial), 0)
        while True:
            if sections:
                lines = [part for line in sections[section_index].text.splitlines()
                         for part in (textwrap.wrap(_safe_terminal_text(line), width=80,
                                      replace_whitespace=False, drop_whitespace=False) or [''])] or ['(empty)']
            chunk = lines[page * page_size:(page + 1) * page_size]
            evidence = ('\n\n'.join(f'{section.title}\n{section.summary}' for section in sections
                        if section.summary) if sections else
                        "\n".join(f"{_safe_terminal_text(k)}: {_safe_terminal_text(v)}" for k, v in record.evidence))
            rows = []
            row_actions = []
            can_adopt = record.status in {"proposed", "reviewed", "deferred", "selected_for_next_session"}
            can_save = record.status in {"proposed", "reviewed", "deferred"}
            if can_adopt:
                rows.append(MenuRow("Use for a new session", "Use in a fresh session and set this profile's default"))
                row_actions.append("adopt")
            if can_save:
                rows.append(MenuRow("Save for later", "Set this profile's default for its next session"))
                row_actions.append("defer")
            if record.status in {"proposed", "reviewed", "deferred"}:
                rows.append(MenuRow("Discard candidate"))
                row_actions.append("reject")
            rows.append(MenuRow("Back"))
            row_actions.append(None)
            selected = len(rows) - 1 if selected is None else min(selected, len(rows) - 1)
            self.menu_renderer.render(title=f"Candidate {record.candidate_id[:10]} · {_candidate_status(record.status)}",
                subtitle=f"{_safe_terminal_text(record.algorithm)} · {_safe_terminal_text(record.target)}\n{_safe_terminal_text(evidence)}\n\n{_safe_terminal_text(sections[section_index].title) if sections else 'Changes'} ({page + 1}/{max(1, (len(lines) + page_size - 1)//page_size)}):\n" + "\n".join(_safe_terminal_text(line) for line in chunk),
                rows=tuple(rows), selected=selected,
                instructions="↑↓ move · Enter select · n/p section · PageUp/PageDown text · Esc back" if self.menu_renderer.ansi else f"Enter 1–{len(rows)}; next/previous section; pageup/pagedown text; back")
            event = self.menu_input.read_event()
            selected, handled = _menu_navigate(event, selected, len(rows))
            if handled:
                continue
            chosen = event.index if event.index is not None else selected
            if sections and event.action in {MenuAction.SECTION_NEXT, MenuAction.SECTION_PREVIOUS}:
                section_index = (section_index + (1 if event.action == MenuAction.SECTION_NEXT else -1)) % len(sections)
                page = 0
                continue
            if event.action in {MenuAction.BACK, MenuAction.QUIT} or event.action == MenuAction.ACTIVATE and row_actions[chosen] is None:
                return
            if event.action == MenuAction.PAGE_UP and page > 0:
                page -= 1
                continue
            if event.action == MenuAction.PAGE_DOWN and (page + 1) * page_size < len(lines):
                page += 1
                continue
            if event.action != MenuAction.ACTIVATE:
                continue
            action = row_actions[chosen]
            if action is None:
                continue
            try:
                if action == "adopt":
                    if not self._confirm_choice(title="Confirm candidate activation",
                            subtitle="The current conversation remains in its original session. This profile's saved default will change.",
                            rows=(MenuRow("Start a fresh session with this candidate"), MenuRow("Cancel"))):
                        self.renderer.write_system("Candidate activation cancelled.\n")
                        return
                    if not isinstance(self.session, CandidateActivationClient):
                        self.session.candidate_action(candidate_id, "adopt")
                        self.renderer.write_system("Candidate saved for the next session.\n")
                    else:
                        await self.session.adopt_candidate(candidate_id)
                        self.renderer.write_system("Candidate activated in a new session.\n")
                else:
                    if action == "defer" and record.status == "selected_for_next_session":
                        self.renderer.write_system("Candidate is already saved for the next session.\n")
                    else:
                        self.session.candidate_action(candidate_id, "adopt" if action == "defer" else "reject")
                        self.renderer.write_system("Candidate saved for the next session.\n" if action == "defer" else "Candidate discarded.\n")
            except (OSError, RuntimeError, TypeError, ValueError) as exc:
                self.renderer.write_system(f"candidate operation failed: {exc}\n")
            return

    async def _resume(self, arguments: tuple[str, ...]) -> None:
        if getattr(self.session, "running", False) or getattr(
            self.session,
            "pending_count",
            0,
        ):
            self.renderer.write_system(
                "finish or /cancel the active run before resuming another session\n"
            )
            return

        path: Path | None = None
        if arguments:
            value = " ".join(arguments)
            path = Path(value)
            if not path.is_absolute():
                path = Path(self.session.status.working_directory) / path
            path = path.resolve()
        else:
            discover = getattr(self.session, "resumable_sessions", None)
            if discover is None:
                self.renderer.write_system(
                    "the /resume session picker is unavailable in this frontend\n"
                )
                return
            try:
                sessions = discover()
            except (
                OSError,
                RuntimeError,
                TypeError,
                ValueError,
            ) as exc:
                self.renderer.write_system(f"could not list sessions: {exc}\n")
                return
            if not sessions:
                self.renderer.write_system(
                    "no compatible non-empty sessions are available\n"
                )
                return
            if self._inline_display is not None:
                self._suspend_inline_terminal()
            try:
                with transient_screen(self.input, self.output):
                    selected = TerminalResumeFrontend(
                        sessions,
                        input_stream=self.input,
                        output_stream=self.output,
                        line_editor=self.line_editor,
                    ).run()
                path = Path(selected.path) if selected is not None else None
            finally:
                if self._inline_display is not None:
                    self._activate_inline_terminal()

        if path is None:
            return
        try:
            await self.session.resume(path)
        except (
            OSError,
            RuntimeError,
            TypeError,
            ValueError,
        ) as exc:
            self.renderer.write_system(f"could not resume session: {exc}\n")
            return
        self.configuration = getattr(
            self.session,
            "configuration",
            self.configuration,
        )
        self.renderer.write_system(f"\n[resumed {path}]\n")
        self.renderer.show_welcome(self.session.status)

    def _activate_inline_terminal(self) -> None:
        if self._inline_display is None:
            return
        start = getattr(self.line_editor, "start", None)
        if start is not None:
            start()
        self._inline_display.activate()

    def _suspend_inline_terminal(self) -> None:
        if self._inline_display is None:
            return
        try:
            self._inline_display.suspend()
        finally:
            stop = getattr(self.line_editor, "stop", None)
            if stop is not None:
                stop()


def _safe_terminal_text(value: str) -> str:
    return "".join(
        char if char in "\n\t" or 32 <= ord(char) < 127 or ord(char) >= 160
        else f"\\x{ord(char):02x}"
        for char in value
    )


__all__ = ["TerminalFrontend"]


def _menu_navigate(event, selected: int, size: int):
    if event.index is not None:
        return (event.index, False) if 0 <= event.index < size else (selected, True)
    if event.action == MenuAction.UP:
        return (selected - 1) % size, True
    if event.action == MenuAction.DOWN:
        return (selected + 1) % size, True
    return selected, False


def _candidate_status(value: str) -> str:
    return {
        "proposed": "Ready for review",
        "reviewed": "Reviewed",
        "deferred": "Deferred",
        "selected_for_next_session": "Saved for next session",
        "adopted": "Active in a session",
        "rejected": "Discarded",
        "stale": "Out of date",
    }.get(value, value)
