"""Optimization, candidate review and corrected-task terminal menus."""

from __future__ import annotations

import asyncio
import json
import textwrap

from ..optimization import CandidateActivationClient, TaskPackClient
from .input import LineEditor
from .menu import MenuAction, MenuInput, MenuRow, TerminalMenuRenderer, navigate_menu
from .renderer import TerminalRenderer
from .text import safe_terminal_text


class TerminalOptimizationFrontend:
    """Use injected interaction services without owning the chat input loop."""

    def __init__(self, session, renderer: TerminalRenderer, line_editor: LineEditor,
                 menu_input: MenuInput | None, menu_renderer: TerminalMenuRenderer | None) -> None:
        self.session = session
        self.renderer = renderer
        self.line_editor = line_editor
        self.menu_input = menu_input
        self.menu_renderer = menu_renderer

    async def run(self, arguments: tuple[str, ...]) -> None:
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
            selected, handled = navigate_menu(event, selected, len(rows))
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
                await self.start_search(direction)
                return
            elif selected == 1:
                await self.review_candidates()
                return
            else:
                await self.save_correction()
                return

    async def start_search(self, direction: str, *, pack_id=None) -> None:
        default_direction = ""
        if pack_id is None and (isinstance(self.session, TaskPackClient) and self.session.task_packs_available):
            try:
                packs = self.session.task_packs()
                if packs:
                    choice = self.choose_row("Choose task package", tuple(MenuRow(safe_terminal_text(p.name),
                        safe_terminal_text(p.error) if p.error else f"{p.train_count} training · {p.validation_count} validation · {p.holdout_count} holdout") for p in packs))
                    if choice is None:
                        return
                    pack = packs[choice]
                    if pack.error:
                        self.renderer.write_system(f"Cannot search: {safe_terminal_text(pack.error)}\n")
                        return
                    pack_id = pack.pack_id
                    default_direction = pack.default_direction
            except (OSError, RuntimeError, TypeError, ValueError) as exc:
                self.renderer.write_system(f"Task packages unavailable: {safe_terminal_text(str(exc))}\n")
                return
        if pack_id and not default_direction and isinstance(self.session, TaskPackClient) and self.session.task_packs_available:
            default_direction = next((p.default_direction for p in self.session.task_packs() if p.pack_id == pack_id), "")
        if not direction:
            self.renderer.write_system("Improvement direction" + (f" (blank uses {safe_terminal_text(default_direction)})" if default_direction else "") + ": ")
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
        rows = (MenuRow("Start search", f"{safe_terminal_text(preview.label)} · {safe_terminal_text(preview.target)}"), MenuRow("Cancel"))
        detail = safe_terminal_text(preview.cost_notice) + "\n" + "\n".join(
            f"{safe_terminal_text(key)}: {safe_terminal_text(value)}" for key, value in preview.details
        )
        if not self.confirm_choice(title="Confirm optimization", subtitle=detail, rows=rows):
            self.renderer.write_system("Search cancelled; no model calls made.\n")
            return
        try:
            self.session.start_optimization(direction, preview_token=preview.preview_token)
            self.renderer.write_system("Optimization submitted; use /status or /cancel.\n")
        except (OSError, RuntimeError, TypeError, ValueError) as exc:
            self.renderer.write_system(f"could not start optimization: {exc}\n")

    def confirm_choice(self, *, title: str, subtitle: str, rows: tuple[MenuRow, ...]) -> bool:
        instructions = ("↑↓ move · Enter select · Esc cancel" if self.menu_renderer.ansi
                        else "Enter an option number; blank selects highlighted; q cancels")
        return self._select_row(title, rows, subtitle=subtitle, selected=1,
                                instructions=instructions) == 0

    def choose_row(self, title, rows, *, subtitle=""):
        rows = (*rows, MenuRow("Back"))
        selected = self._select_row(title, rows, subtitle=subtitle)
        return None if selected == len(rows) - 1 else selected

    def _select_row(self, title, rows, *, subtitle="", selected=0, instructions=None):
        options = {} if instructions is None else {"instructions": instructions}
        while True:
            self.menu_renderer.render(title=title, subtitle=subtitle, rows=rows,
                                      selected=selected, **options)
            event = self.menu_input.read_event()
            selected, handled = navigate_menu(event, selected, len(rows))
            if handled:
                continue
            if event.action in {MenuAction.BACK, MenuAction.QUIT}:
                return None
            if event.action == MenuAction.ACTIVATE:
                return selected

    async def _ask_correction(self, prompt):
        self.renderer.write_system(prompt)
        return await asyncio.to_thread(self.line_editor.read_line)

    async def save_correction(self):
        try:
            tasks = self.session.correction_tasks()
            if not tasks:
                self.renderer.write_system("No completed text tasks available.\n")
                return
            choice = self.choose_row("Choose completed task", tuple(MenuRow(
                safe_terminal_text(t.input[:100]), safe_terminal_text(t.output[:100])) for t in tasks))
            if choice is None:
                return
            task = tasks[choice]
            packs = self.session.task_packs()
            choice = self.choose_row("Save to task package", (*tuple(MenuRow(
                safe_terminal_text(p.name), "Writable" if p.writable else "Save a workspace copy") for p in packs),
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
                answer = await self._ask_correction(f"Acceptance JSON (example {safe_terminal_text(pack.acceptance_example)}): ")
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
            detail = (f"Question: {safe_terminal_text(question)}\n"
                      + (f"Correct answer: {safe_terminal_text(answer)}\n" if acceptance is None else "")
                      + f"Package: {safe_terminal_text(pack.name if pack else name)}\n"
                      + ("A writable workspace copy will be created.\n" if copy else "")
                      + (f"Acceptance: {safe_terminal_text(json.dumps(acceptance, ensure_ascii=False))}\n" if acceptance is not None else "")
                      + "Only training changes. No model calls. Confirm the question is self-contained.")
            if not self.confirm_choice(title="Confirm training task", subtitle=detail,
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
                if not self.confirm_choice(title="Training answer already exists", subtitle="Replace its acceptance criteria?",
                        rows=(MenuRow("Replace answer"), MenuRow("Cancel"))):
                    return
                saved = self.session.save_training_task(task.task_id, pack.pack_id, question, answer.strip(), replace=True, **options)
            self.renderer.write_system(f"Saved to {safe_terminal_text(saved.name)} · {saved.train_count} training cases.\n")
            if saved.error:
                self.renderer.write_system(f"Before searching: {safe_terminal_text(saved.error)}.\n")
                return
            choice = self.choose_row("Task saved", (MenuRow("Return to chat"), MenuRow("Optimize this package")))
            if choice == 1:
                await self.start_search("", pack_id=saved.pack_id)
        except (OSError, RuntimeError, TypeError, ValueError) as exc:
            self.renderer.write_system(f"Cannot save task: {safe_terminal_text(str(exc))}\n")

    async def review_candidates(self) -> None:
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
            selected, handled = navigate_menu(event, selected, len(rows))
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
            await self.candidate_detail(records[value].candidate_id)
            return

    async def candidate_detail(self, candidate_id: str) -> None:
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
                rows=tuple(rows), selected=selected,
                instructions="↑↓ move · Enter select · n/p section · PageUp/PageDown text · Esc back" if self.menu_renderer.ansi else f"Enter 1–{len(rows)}; next/previous section; pageup/pagedown text; back")
            event = self.menu_input.read_event()
            selected, handled = navigate_menu(event, selected, len(rows))
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
                    if not self.confirm_choice(title="Confirm candidate activation",
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

