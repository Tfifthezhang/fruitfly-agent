"""Task-driven improvement, candidate review and saved-case terminal menus."""

from __future__ import annotations

import asyncio
import json
import textwrap

from fruitfly_agent.interactive.terminal.bindings import ImprovementClients
from fruitfly_agent.interactive.terminal.io.input import LineEditor
from fruitfly_agent.interactive.terminal.io.menu import (
    MenuAction,
    MenuInput,
    MenuRow,
    TerminalMenuRenderer,
    navigate_menu,
)
from fruitfly_agent.interactive.terminal.rendering.renderer import TerminalRenderer
from fruitfly_agent.interactive.terminal.io.text import safe_terminal_text
from fruitfly_agent.interactive.contracts.evaluation import BenchmarkImprovementController, BenchmarkImprovementRequest
from .events import BenchmarkEventDisplay
from .formatting import format_optimization_activity


class TerminalImprovementFrontend:
    """Use injected interaction services without owning the chat input loop."""

    def __init__(self, session, renderer: TerminalRenderer, line_editor: LineEditor,
                 menu_input: MenuInput | None, menu_renderer: TerminalMenuRenderer | None,
                 *, clients: ImprovementClients | None = None, benchmark=None) -> None:
        self.clients = clients or ImprovementClients.from_session(session)
        self.renderer = renderer
        self.line_editor = line_editor
        self.menu_input = menu_input
        self.menu_renderer = menu_renderer
        self.benchmark = benchmark if isinstance(benchmark, BenchmarkImprovementController) else None
        self._quit = False
        self._selections = {}
        self._drafts = {}
        self._form_key = None
        self.notice = ""
        self.messages = []

    async def run(self, arguments: tuple[str, ...]) -> str | None:
        result = await self._run(arguments)
        return "".join((*self.messages, result or "")) or None

    def report(self, message):
        self.notice = message
        self.messages.append(message.rstrip() + "\n")

    async def _run(self, arguments: tuple[str, ...]) -> str | None:
        if self.menu_input is None or self.menu_renderer is None:
            self.renderer.write_system("improvement menu unavailable\n")
            return
        direction = " ".join(arguments).strip()
        selected = 0
        while not self._quit:
            progress = self.clients.progress()
            running = progress is not None and progress.status == "running"
            try:
                candidates = self.clients.candidates.candidates() if self.clients.candidates is not None else ()
            except (OSError, RuntimeError, TypeError, ValueError):
                candidates = ()
            pending = sum(item.status in {"proposed", "reviewed", "deferred", "selected_for_next_session"} for item in candidates)
            actions, rows = [], []
            if self.clients.search is not None or self.benchmark is not None:
                actions.append("search")
                rows.append(MenuRow("Start improvement", "Choose benchmark tasks or a saved case package", marker="!" if running else ""))
            if self.clients.candidates is not None:
                actions.append("review")
                rows.append(MenuRow("Review candidates", f"{pending} pending · {len(candidates)} total"))
            if self.clients.materials is not None and self.clients.materials.task_packs_available:
                actions.append("correction")
                rows.append(MenuRow("Save a failed task", "Correct a completed answer and add it to training"))
            actions.append("back")
            rows.append(MenuRow("Return to chat"))
            self.menu_renderer.render(
                title="Improvement",
                subtitle=(f"Improvement {progress.status}" if running else "Improve against declared task acceptance; review before adoption"),
                rows=tuple(rows), selected=selected, notice=self.notice,
                instructions="↑↓ move · Enter select · Esc back · q close menu" if self.menu_renderer.ansi else "Enter an option number; blank selects highlighted; q closes the menu",
            )
            self.notice = ""
            event = self.menu_input.read_event()
            selected, handled = navigate_menu(event, selected, len(rows))
            if handled:
                continue
            if event.action in {MenuAction.BACK, MenuAction.QUIT} or (event.action == MenuAction.ACTIVATE and selected == len(rows) - 1):
                return
            if event.action != MenuAction.ACTIVATE:
                continue
            if actions[selected] == "search":
                if running:
                    self.renderer.write_system("improvement is already running; use /status or /cancel\n")
                    continue
                result = await self.start_improvement(direction)
                if result is not None:
                    return result
            elif actions[selected] == "review":
                await self.review_candidates()
            else:
                await self.save_correction()

    async def start_improvement(self, direction) -> str | None:
        if self.benchmark is None:
            return await self.start_search(direction)
        if self.clients.search is None:
            return await self.start_benchmark(direction)
        while not self._quit:
            choice = self.choose_row("Choose task source", (
                MenuRow("Saved task packages", "Authored tasks and daily cases with explicit acceptance criteria"),
                MenuRow("Benchmark tasks", "Original isolated environments and official verification")))
            if choice is None:
                return
            result = await (self.start_search(direction) if choice == 0 else self.start_benchmark(direction))
            if result is not None:
                return result

    async def start_benchmark(self, direction) -> str | None:
        if self.benchmark is None:
            self.report("Benchmark task source unavailable.\n")
            return
        try:
            if not self.benchmark.improvement_available:
                self.report("Benchmark improvement unavailable. Enable an optimizer, failure processing "
                            "and automatic improvement in /config; then start a new session.\n")
                return
            snapshot = self.benchmark.improvement_snapshot()
            if not snapshot.benchmarks:
                self.report("No benchmark task sources are available. Check the optional Eval installation.\n")
                return
            while not self._quit:
                choice = self.choose_row("Choose benchmark tasks", tuple(MenuRow(item.label,
                    f"{item.version} · {item.description}") for item in snapshot.benchmarks))
                if choice is None:
                    return
                benchmark = snapshot.benchmarks[choice]
                if not benchmark.variants:
                    self.report(f"No task sets are available for {safe_terminal_text(benchmark.label)}.\n")
                    continue
                while not self._quit:
                    choice = self.choose_row("Choose task set", tuple(MenuRow(item.label,
                        item.description if item.available else "Unavailable · " + "; ".join(item.preflight))
                        for item in benchmark.variants), key=("task-set", benchmark.benchmark_id))
                    if choice is None:
                        break
                    variant = benchmark.variants[choice]
                    if not variant.available:
                        reason = "; ".join(variant.preflight) or "the selected task environment is unavailable"
                        self.report("Cannot start improvement: " + safe_terminal_text(reason) + "\n")
                        continue
                    request = BenchmarkImprovementRequest(benchmark.benchmark_id, variant.variant_id)
                    try:
                        preview = self.benchmark.benchmark_preview(request, direction)
                    except (OSError, RuntimeError, TypeError, ValueError) as exc:
                        self.report(f"Cannot run improvement: {safe_terminal_text(str(exc))}\n")
                        continue
                    detail = safe_terminal_text(preview.cost_notice) + "\n" + "\n".join(
                        f"{safe_terminal_text(key)}: {safe_terminal_text(value)}" for key, value in preview.details)
                    if not self.confirm_choice(title="Confirm improvement", subtitle=detail,
                            rows=(MenuRow("Start improvement", "Prepare tasks, run baseline, iterate and confirm"), MenuRow("Cancel"))):
                        self.report("Improvement cancelled; no task download or model calls started.\n")
                        continue
                    return await self.execute_benchmark(preview.preview_token)
        except (OSError, RuntimeError, TypeError, ValueError) as exc:
            self.report(f"Cannot run improvement: {safe_terminal_text(str(exc))}\n")

    async def execute_benchmark(self, preview_token):
        try:
            display = BenchmarkEventDisplay()
            event_renderer = TerminalRenderer(self.renderer.output, tool_output_limit=None)
            task = asyncio.create_task(self.benchmark.improve(preview_token,
                on_event=lambda event: display.show_event(event_renderer, event)))
            previous = None
            try:
                while not task.done():
                    await asyncio.wait({task}, timeout=.5)
                    progress = self.clients.progress()
                    activity = progress.activity if progress is not None else None
                    text = format_optimization_activity(activity) if activity is not None else ""
                    if text and text != previous:
                        event_renderer.write_system(text + "\n")
                        previous = text
                records = await task
            finally:
                if not task.done():
                    task.cancel()
                    await asyncio.gather(task, return_exceptions=True)
                await event_renderer.close()
                event_renderer.finish_line()
            return f"Improvement completed: {len(records)} candidate(s) awaiting review. Use /improvement → Review candidates.\n"
        except asyncio.CancelledError:
            if asyncio.current_task().cancelling():
                raise
            return "Improvement cancelled; no candidate adopted.\n"
        except (OSError, RuntimeError, TypeError, ValueError) as exc:
            return f"Cannot run improvement: {safe_terminal_text(str(exc))}\n"

    async def start_search(self, direction: str, *, pack_id=None) -> str | None:
        if self.clients.search is None:
            self.report("improvement service unavailable\n")
            return
        while not self._quit:
            selected_pack = pack_id
            packs = ()
            default_direction = ""
            if pack_id is None and (self.clients.materials is not None and self.clients.materials.task_packs_available):
                try:
                    packs = self.clients.materials.task_packs()
                    if packs:
                        choice = self.choose_row("Choose task package", tuple(MenuRow(safe_terminal_text(p.name),
                            safe_terminal_text(p.error) if p.error else f"{p.train_count} training · {p.validation_count} validation · {p.holdout_count} holdout") for p in packs))
                        if choice is None:
                            return
                        pack = packs[choice]
                        if pack.error:
                            self.report(f"Cannot search: {safe_terminal_text(pack.error)}\n")
                            continue
                        selected_pack = pack.pack_id
                        default_direction = pack.default_direction
                except (OSError, RuntimeError, TypeError, ValueError) as exc:
                    self.report(f"Task packages unavailable: {safe_terminal_text(str(exc))}\n")
                    return
            if selected_pack and not default_direction and self.clients.materials is not None and self.clients.materials.task_packs_available:
                default_direction = next((p.default_direction for p in self.clients.materials.task_packs() if p.pack_id == selected_pack), "")
            if not direction:
                self.renderer.write_system("Improvement direction" + (f" (blank uses {safe_terminal_text(default_direction)})" if default_direction else "") + ": ")
                value = await asyncio.to_thread(self.line_editor.read_line)
                if value is None:
                    self.report("\nSearch cancelled.\n")
                    return
                direction = value.strip() or default_direction
            if not direction or len(direction) > 500:
                self.report("Search cancelled; direction must contain 1–500 characters.\n")
                return
            try:
                preview = self.clients.search.optimization_preview(pack_id=selected_pack, direction=direction)
            except (OSError, RuntimeError, TypeError, ValueError) as exc:
                self.report(f"cannot start improvement: {exc}\n")
                return
            rows = (MenuRow("Start search", f"{safe_terminal_text(preview.label)} · {safe_terminal_text(preview.target)}"), MenuRow("Cancel"))
            detail = safe_terminal_text(preview.cost_notice) + "\n" + "\n".join(
                f"{safe_terminal_text(key)}: {safe_terminal_text(value)}" for key, value in preview.details
            )
            if not self.confirm_choice(title="Confirm improvement", subtitle=detail, rows=rows):
                self.report("Search cancelled; no model calls made.\n")
                if pack_id is None and packs:
                    continue
                return
            try:
                self.clients.search.start_optimization(direction, preview_token=preview.preview_token)
                return "Improvement submitted; use /status or /cancel.\n"
            except (OSError, RuntimeError, TypeError, ValueError) as exc:
                self.report(f"could not start improvement: {exc}\n")
            return

    def confirm_choice(self, *, title: str, subtitle: str, rows: tuple[MenuRow, ...]) -> bool:
        instructions = ("↑↓ move · Enter select · Esc cancel" if self.menu_renderer.ansi
                        else "Enter an option number; blank selects highlighted; q cancels")
        return self._select_row(title, rows, subtitle=subtitle, selected=1,
                                instructions=instructions) == 0

    def choose_row(self, title, rows, *, subtitle="", key=None):
        rows = (*rows, MenuRow("Back"))
        key = title if key is None else key
        selected = self._select_row(title, rows, subtitle=subtitle,
                                    selected=min(self._selections.get(key, 0), len(rows) - 1))
        if selected is not None and selected != len(rows) - 1:
            self._selections[key] = selected
            return selected
        return None

    def _select_row(self, title, rows, *, subtitle="", selected=0, instructions=None):
        options = {} if instructions is None else {"instructions": instructions}
        while not self._quit:
            self.menu_renderer.render(title=title, subtitle=subtitle, rows=rows,
                                      selected=selected, notice=self.notice, **options)
            self.notice = ""
            event = self.menu_input.read_event()
            selected, handled = navigate_menu(event, selected, len(rows))
            if handled:
                continue
            if event.action == MenuAction.QUIT:
                self._quit = True
                return
            if event.action == MenuAction.BACK:
                return None
            if event.action == MenuAction.ACTIVATE:
                return selected

    async def _ask_correction(self, prompt):
        self.renderer.write_system(prompt)
        key = (self._form_key, prompt)
        if key not in self._drafts:
            self._drafts[key] = await asyncio.to_thread(self.line_editor.read_line)
        return self._drafts[key]

    async def save_correction(self):
        if self.clients.materials is None:
            self.report("task package service unavailable\n")
            return
        try:
            tasks = self.clients.materials.correction_tasks()
            if not tasks:
                self.report("No completed text tasks available.\n")
                return
            while not self._quit:
                choice = self.choose_row("Choose completed task", tuple(MenuRow(
                    safe_terminal_text(t.input[:100]), safe_terminal_text(t.output[:100])) for t in tasks))
                if choice is None:
                    return
                task = tasks[choice]
                while not self._quit:
                    packs = self.clients.materials.task_packs()
                    choice = self.choose_row("Save to task package", (*tuple(MenuRow(
                        safe_terminal_text(p.name), "Writable" if p.writable else "Save a workspace copy") for p in packs),
                        MenuRow("Create task package", "Independent selection and confirmation must be added before automatic improvement")))
                    if choice is None:
                        break
                    pack = packs[choice] if choice < len(packs) else None
                    if await self.save_correction_form(task, pack) is not False:
                        return
        except (OSError, RuntimeError, TypeError, ValueError) as exc:
            self.report(f"Cannot save task: {safe_terminal_text(str(exc))}\n")

    async def save_correction_form(self, task, pack):
        try:
            self._form_key = (task.task_id, pack.pack_id if pack else "new")
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
                answer = await self._ask_correction(f"Acceptance JSON (example {safe_terminal_text(pack.acceptance_example)}): ")
                if answer is None or not answer.strip():
                    self.report("Save cancelled; acceptance is required.\n")
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
                    self.report("Save cancelled; a correct answer is required.\n")
                    return
            reason = await self._ask_correction("Reason (optional, stored as metadata): ")
            if reason is None:
                return
            copy = pack is not None and not pack.writable
            detail = (f"Question: {safe_terminal_text(question)}\n"
                      + (f"Correct answer: {safe_terminal_text(answer)}\n" if acceptance is None else "")
                      + f"Package: {safe_terminal_text(pack.name if pack else name)}\n"
                      + ("A writable workspace copy will be created.\n" if copy else "")
                      + (f"Acceptance: {safe_terminal_text(json.dumps(acceptance, ensure_ascii=False))}\n" if acceptance is not None else "")
                      + "Only training changes. No model calls. Confirm the question is self-contained.")
            if not self.confirm_choice(title="Confirm training task", subtitle=detail,
                    rows=(MenuRow("Save task"), MenuRow("Cancel"))):
                self.report("Save cancelled.\n")
                return False
            options = dict(expected_hash=pack.source_hash if pack else "", name=name,
                           reason=reason.strip(), copy=copy, acceptance=acceptance)
            try:
                saved = self.clients.materials.save_training_task(task.task_id, pack.pack_id if pack else "", question, answer.strip(), **options)
            except ValueError as exc:
                if "conflicting training answer" not in str(exc):
                    raise
                if not self.confirm_choice(title="Training answer already exists", subtitle="Replace its acceptance criteria?",
                        rows=(MenuRow("Replace answer"), MenuRow("Cancel"))):
                    return
                saved = self.clients.materials.save_training_task(task.task_id, pack.pack_id, question, answer.strip(), replace=True, **options)
            self.report(f"Saved to {safe_terminal_text(saved.name)} · {saved.train_count} training cases.\n")
            if saved.error:
                self.report(f"Before searching: {safe_terminal_text(saved.error)}.\n")
                return
            if self.clients.search is None:
                return
            choice = self._select_row("Task saved", (MenuRow("Back"), MenuRow("Improve this package")))
            if choice == 1:
                return await self.start_search("", pack_id=saved.pack_id)
            return False
        except (OSError, RuntimeError, TypeError, ValueError) as exc:
            self._drafts = {key: value for key, value in self._drafts.items() if key[0] != self._form_key}
            self.report(f"Cannot save task: {safe_terminal_text(str(exc))}\n")
            return False

    async def review_candidates(self) -> None:
        if self.clients.candidates is None:
            self.report("candidate service unavailable\n")
            return
        selected = 0
        page = 0
        page_size = 10
        while not self._quit:
            try:
                records = self.clients.candidates.candidates()
            except (OSError, RuntimeError, TypeError, ValueError) as exc:
                self.report(f"candidate inbox unavailable: {exc}\n")
                return
            if not records:
                self.menu_renderer.render(title="Improvement candidates", subtitle="No saved candidates", rows=(MenuRow("Back"),), selected=0)
                event = self.menu_input.read_event()
                if event.action == MenuAction.QUIT:
                    self._quit = True
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
            self.menu_renderer.render(title="Improvement candidates", subtitle=f"Select a result to inspect its changes · page {page + 1}/{page_count}", rows=tuple(rows), selected=selected, notice=self.notice)
            self.notice = ""
            event = self.menu_input.read_event()
            selected, handled = navigate_menu(event, selected, len(rows))
            if handled:
                continue
            if event.action == MenuAction.QUIT:
                self._quit = True
                return
            if event.action == MenuAction.BACK:
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
            await self.candidate_detail(records[value].candidate_id)

    async def candidate_detail(self, candidate_id: str) -> None:
        if self.clients.candidates is None:
            self.report("candidate service unavailable\n")
            return
        try:
            record, diff = self.clients.candidates.candidate_detail(candidate_id)
        except (OSError, RuntimeError, TypeError, ValueError) as exc:
            self.report(f"candidate unavailable: {exc}\n")
            return
        lines = diff.splitlines() or ["(no textual difference)"]
        page = 0
        page_size = 8
        selected = None
        sections = getattr(record, 'sections', ())
        section_index = next((i for i, section in enumerate(sections) if section.initial), 0)
        while not self._quit:
            if sections:
                lines = [part for line in sections[section_index].text.splitlines()
                         for part in (textwrap.wrap(safe_terminal_text(line), width=80,
                                      replace_whitespace=False, drop_whitespace=False) or [''])] or ['(empty)']
            chunk = lines[page * page_size:(page + 1) * page_size]
            evidence = ('\n\n'.join(f'{section.title}\n{section.summary}' for section in sections
                        if section.summary) if sections else
                        "\n".join(f"{safe_terminal_text(k)}: {safe_terminal_text(v)}" for k, v in record.evidence))
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
                subtitle=f"{safe_terminal_text(record.algorithm)} · {safe_terminal_text(record.target)}\n{safe_terminal_text(evidence)}\n\n{safe_terminal_text(sections[section_index].title) if sections else 'Changes'} ({page + 1}/{max(1, (len(lines) + page_size - 1)//page_size)}):\n" + "\n".join(safe_terminal_text(line) for line in chunk),
                rows=tuple(rows), selected=selected, notice=self.notice,
                instructions="↑↓ move · Enter select · n/p section · PageUp/PageDown text · Esc back" if self.menu_renderer.ansi else f"Enter 1–{len(rows)}; next/previous section; pageup/pagedown text; back")
            event = self.menu_input.read_event()
            self.notice = ""
            selected, handled = navigate_menu(event, selected, len(rows))
            if handled:
                continue
            chosen = event.index if event.index is not None else selected
            if sections and event.action in {MenuAction.SECTION_NEXT, MenuAction.SECTION_PREVIOUS}:
                section_index = (section_index + (1 if event.action == MenuAction.SECTION_NEXT else -1)) % len(sections)
                page = 0
                continue
            if event.action == MenuAction.QUIT:
                self._quit = True
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
                    if not self.confirm_choice(title="Confirm candidate activation",
                            subtitle="The current conversation remains in its original session. This profile's saved default will change.",
                            rows=(MenuRow("Start a fresh session with this candidate"), MenuRow("Cancel"))):
                        self.report("Candidate activation cancelled.\n")
                        continue
                    if self.clients.activation is None:
                        self.clients.candidates.candidate_action(candidate_id, "adopt")
                        self.report("Candidate saved for the next session.\n")
                    else:
                        await self.clients.activation.adopt_candidate(candidate_id)
                        self.report("Candidate activated in a new session.\n")
                else:
                    if action == "defer" and record.status == "selected_for_next_session":
                        self.report("Candidate is already saved for the next session.\n")
                    else:
                        self.clients.candidates.candidate_action(candidate_id, "adopt" if action == "defer" else "reject")
                        self.report("Candidate saved for the next session.\n" if action == "defer" else "Candidate discarded.\n")
            except (OSError, RuntimeError, TypeError, ValueError) as exc:
                self.report(f"candidate operation failed: {exc}\n")
            return


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

