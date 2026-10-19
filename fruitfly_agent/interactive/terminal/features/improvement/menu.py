"""Task-driven improvement, candidate review and saved-case terminal menus."""

from __future__ import annotations

import asyncio
from dataclasses import replace
import textwrap
import inspect
import shutil
from uuid import uuid4

from fruitfly_agent.interactive.terminal.bindings import ImprovementClients
from fruitfly_agent.interactive.terminal.io.input import LineEditor, read_field_line
from fruitfly_agent.interactive.terminal.io.live import InputInterrupted
from fruitfly_agent.interactive.terminal.io.menu import (
    MenuAction,
    MenuInput,
    LineMenuInput,
    MenuRow,
    TerminalMenuRenderer,
    navigate_menu,
)
from fruitfly_agent.interactive.terminal.rendering.renderer import TerminalRenderer
from fruitfly_agent.interactive.terminal.io.text import safe_terminal_text
from fruitfly_agent.interactive.contracts.evaluation import BenchmarkImprovementController
from .events import BenchmarkEventDisplay
from .panel import ExperimentPanel
from fruitfly_agent.interactive.contracts.improvement import ImprovementRunView
from fruitfly_agent.interactive.contracts.candidates import CandidateSection
from .formatting import format_improvement_activity


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
        if menu_renderer is not None and isinstance(menu_input, LineMenuInput):
            menu_renderer.numbered = True
        self.benchmark = benchmark if isinstance(benchmark, BenchmarkImprovementController) else None
        self._quit = False
        self._selections = {}
        self.role = "H"
        self.notice = ""
        self.messages = []
        self._selected_row = 0

    async def run(self, arguments: tuple[str, ...]) -> str | None:
        result = await self._run(arguments)
        return "".join((*self.messages, result or "")) or None

    def report(self, message):
        self.notice = message
        self.messages.append(message.rstrip() + "\n")

    async def _run(self, arguments: tuple[str, ...]) -> str | None:
        if self.menu_input is None or self.menu_renderer is None:
            self.report("improvement menu unavailable\n")
            return
        panel = ExperimentPanel(clients=self.clients, benchmark=self.benchmark,
            choose=self.choose_row, select=self._select_row, confirm=self.confirm_choice,
            read=self.read_value, report=self.report, execute=self.execute,
            history=self.experiment_history, direction=" ".join(arguments).strip())
        await panel.run()

    async def read_value(self, prompt):
        self.menu_renderer.begin_input(safe_terminal_text(prompt), selected=self._selected_row)
        try:
            return await asyncio.to_thread(read_field_line, self.line_editor, 'Value')
        except (InputInterrupted, KeyboardInterrupt):
            return None

    async def execute(self, preview, direction, source):
        before = {r.run_id for r in self.clients.history()}
        display = BenchmarkEventDisplay()
        event_renderer = TerminalRenderer(self.renderer.output, tool_output_limit=None)

        async def run():
            try:
                if source == 'benchmark':
                    return await self.benchmark.improve(preview.preview_token,
                        on_event=lambda event: display.show_event(event_renderer, event))
                value = self.clients.search.start_improvement(direction, preview_token=preview.preview_token)
                return await value if inspect.isawaitable(value) else ()
            finally:
                await event_renderer.close()
                event_renderer.finish_line()

        task = asyncio.create_task(run())
        if await self.watch(task):
            # Application still owns the work. Retrieve the frontend wrapper's exception.
            task.add_done_callback(lambda value: value.exception() if not value.cancelled() else None)
            self.report('Improvement running; use /status, /cancel or /improvement to inspect results.\n')
            return True
        records, error, status = (), '', 'completed'
        try:
            records = await task
        except asyncio.CancelledError:
            if asyncio.current_task().cancelling():
                raise
            status, error = 'cancelled', 'Improvement cancelled; no candidate adopted.'
        except (OSError, RuntimeError, TypeError, ValueError) as exc:
            status, error = 'failed', str(exc)
        rows = self.clients.history()
        result = next((r for r in rows if r.run_id not in before), None)
        if result is None:
            result = ImprovementRunView(uuid4().hex, status, preview.algorithm, preview.target,
                preview.role, direction, stop_reason='interrupted' if status == 'cancelled' else 'error' if error else 'completed',
                candidate_ids=tuple(r.candidate_id for r in records), sections=(
                    CandidateSection('Result', error or f'{len(records)} candidate(s) published; human review required. '
                        'Completion alone does not establish improvement.', initial=True),
                    CandidateSection('Setup', preview.cost_notice + '\n' + '\n'.join(f'{k}: {v}' for k, v in preview.details))))
        self.report(f'Improvement {result.status}: {result.stop_reason}; {len(result.candidate_ids)} candidate(s).'
                    + (f' {error}' if error else '') + '\n')
        return await self.run_result(result)

    async def watch(self, task):
        """Poll the existing menu reader only when it supports bounded reads."""
        previous = None
        selected = 0
        poll = getattr(self.menu_input, 'poll_event', None)
        try:
            while not task.done():
                progress = self.clients.progress()
                activity = progress.activity if progress is not None else None
                text = format_improvement_activity(activity) if activity is not None else 'Preparing experiment'
                if poll is not None:
                    if (text, selected) != previous:
                        self.menu_renderer.render(title='Improvement · Running', subtitle=text,
                            rows=(MenuRow('Return to chat', 'The experiment continues'), MenuRow('Cancel improvement')),
                            selected=selected, instructions='↑↓ move · Enter select · Esc return to chat')
                        previous = (text, selected)
                    try:
                        event = await asyncio.to_thread(poll, .1)
                    except KeyboardInterrupt:
                        self.clients.cancel()
                        task.cancel()
                        await asyncio.gather(task, return_exceptions=True)
                        return False
                    selected, handled = navigate_menu(event, selected, 2)
                    if handled:
                        continue
                    if event.action in {MenuAction.BACK, MenuAction.QUIT} or event.action == MenuAction.ACTIVATE and selected == 0:
                        return True
                    if event.action == MenuAction.ACTIVATE and selected == 1:
                        self.clients.cancel()
                        task.cancel()
                        await asyncio.gather(task, return_exceptions=True)
                        return False
                else:
                    if text != previous:
                        self.renderer.write_system('[improvement] ' + safe_terminal_text(text) + '\n')
                        previous = text
                    await asyncio.wait({task}, timeout=.5)
        except BaseException:
            self.clients.cancel()
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            raise
        return False

    async def experiment_history(self):
        page, selected = 0, 0
        while not self._quit:
            try:
                runs = tuple(self.clients.history())
            except (OSError, ValueError, RuntimeError, TypeError) as exc:
                self.report(f'Experiment history unavailable: {exc}\n')
                return
            page = min(page, max(0, (len(runs) - 1) // 10))
            shown = runs[page * 10:(page + 1) * 10]
            actions = [('run', r) for r in shown]
            rows = [MenuRow(f'{r.status} · {r.algorithm} · {r.target}',
                            f'{r.started_at} · {r.stop_reason or "in progress"} · {len(r.candidate_ids)} candidate(s)') for r in shown]
            if page:
                rows.append(MenuRow('Previous page'))
                actions.append(('page', page - 1))
            if (page + 1) * 10 < len(runs):
                rows.append(MenuRow('Next page'))
                actions.append(('page', page + 1))
            rows.append(MenuRow('Saved candidates', 'Includes candidates created before experiment history was available'))
            actions.append(('candidates', None))
            choice = self.choose_row('Results and history', tuple(rows),
                subtitle='Every submitted experiment is recorded, including empty, failed and cancelled runs.', key=('history', page))
            if choice is None:
                return
            action, value = actions[choice]
            if action == 'page':
                page = value
            elif action == 'candidates':
                await self.review_candidates(all_roles=True)
            else:
                if await self.run_result(value, historical=True):
                    self._quit = True
                    return

    async def run_result(self, result, *, historical=False):
        sections = list(result.sections or (CandidateSection('Result', result.stop_reason or result.status),))
        section, page, selected = 0, 0, None
        while not self._quit:
            lines = [part for line in sections[section].text.splitlines()
                     for part in (textwrap.wrap(safe_terminal_text(line), width=80,
                         replace_whitespace=False, drop_whitespace=False) or [''])] or ['(empty)']
            pages = max(1, (len(lines) + 7) // 8)
            page = min(page, pages - 1)
            rows = [MenuRow('Review candidate ' + identity[:10]) for identity in result.candidate_ids]
            actions = [('candidate', identity) for identity in result.candidate_ids]
            if result.status == 'running':
                rows.extend((MenuRow('Watch progress'), MenuRow('Cancel improvement')))
                actions.extend((('watch', None), ('cancel', None)))
            for index, item in enumerate(sections):
                if item.title in {'Evaluation', 'Usage', 'Evidence', 'Setup'}:
                    rows.append(MenuRow('View ' + item.title.lower()))
                    actions.append(('section', index))
            if self.clients.history_logs is not None:
                rows.append(MenuRow('View logs'))
                actions.append(('logs', None))
            rows.append(MenuRow('Back' if historical else 'Edit and run again', 'Returns without starting work'))
            actions.append(('back', None))
            rows.append(MenuRow('Return to chat'))
            actions.append(('chat', None))
            selected = len(rows) - 2 if selected is None else min(selected, len(rows) - 1)
            self.menu_renderer.render(title=f'Improvement · Result · {result.status}',
                subtitle=f'{safe_terminal_text(result.algorithm)} · {safe_terminal_text(result.target)}\n'
                    f'Stop reason: {safe_terminal_text(result.stop_reason or result.status)}\n'
                    f'{sections[section].title} ({page + 1}/{pages})\n' + '\n'.join(lines[page * 8:(page + 1) * 8]),
                rows=tuple(rows), selected=selected, notice=self.notice,
                instructions='n/p section · PageUp/PageDown text · Enter select · Esc back · q return to chat')
            self.notice = ''
            event = self.menu_input.read_event()
            selected, handled = navigate_menu(event, selected, len(rows))
            if handled:
                continue
            if event.action == MenuAction.QUIT:
                return True
            if event.action == MenuAction.BACK:
                return False
            if event.action in {MenuAction.SECTION_NEXT, MenuAction.SECTION_PREVIOUS}:
                section = (section + (1 if event.action == MenuAction.SECTION_NEXT else -1)) % len(sections)
                page = 0
            elif event.action == MenuAction.PAGE_DOWN:
                page = min(page + 1, pages - 1)
            elif event.action == MenuAction.PAGE_UP:
                page = max(0, page - 1)
            elif event.action == MenuAction.ACTIVATE:
                action, value = actions[selected]
                if action == 'candidate':
                    await self.candidate_detail(value)
                elif action == 'section':
                    section, page = value, 0
                elif action == 'logs':
                    try:
                        text = self.clients.history_logs(result.run_id)
                        sections.append(CandidateSection('Logs', text))
                        section, page = len(sections) - 1, 0
                    except (OSError, ValueError, TypeError, RuntimeError) as exc:
                        self.report(f'Logs unavailable: {exc}\n')
                elif action == 'cancel':
                    self.clients.cancel()
                    self.report('Cancellation requested.\n')
                    return False
                elif action == 'watch':
                    if self.clients.wait is not None:
                        task = asyncio.create_task(self.clients.wait())
                        if await self.watch(task):
                            task.add_done_callback(lambda item: item.exception() if not item.cancelled() else None)
                            return True
                        await task
                        result = next((r for r in self.clients.history() if r.run_id == result.run_id), result)
                        sections = list(result.sections) or sections
                        section, page, selected = 0, 0, None
                elif action == 'chat':
                    return True
                else:
                    return False
        return True

    def confirm_choice(self, *, title: str, subtitle: str, rows: tuple[MenuRow, ...]) -> bool:
        instructions = ("↑↓ move · Enter select · Esc cancel" if self.menu_renderer.ansi and not getattr(self.menu_renderer, 'numbered', False)
                        else "Enter an option number; blank selects highlighted; q returns to chat")
        return self._select_row(title, rows, subtitle=subtitle, selected=1,
                                instructions=instructions) == 0

    def choose_row(self, title, rows, *, subtitle="", key=None):
        key = title if key is None else key
        preferred = min(self._selections.get(key, 0), max(0, len(rows) - 1))
        page, size = preferred // 8, 8
        while not self._quit:
            start = page * size
            shown = list(rows[start:start + size])
            actions = list(range(start, start + len(shown)))
            if page:
                shown.append(MenuRow('Previous page'))
                actions.append('previous')
            if start + size < len(rows):
                shown.append(MenuRow('Next page'))
                actions.append('next')
            shown.append(MenuRow('Back'))
            actions.append('back')
            selected = self._select_row(title, tuple(shown), subtitle=subtitle,
                selected=max(0, min(preferred - start, len(shown) - 1)))
            if selected is None or actions[selected] == 'back':
                return None
            action = actions[selected]
            if action in {'previous', 'next'}:
                page += 1 if action == 'next' else -1
                preferred = page * size
            else:
                self._selections[key] = action
                return action

    def _select_row(self, title, rows, *, subtitle="", selected=0, instructions=None):
        reference_page = 0
        rows = tuple(replace(row, label=safe_terminal_text(row.label), detail=safe_terminal_text(row.detail),
            section=safe_terminal_text(row.section)) for row in rows)
        subtitle = safe_terminal_text(subtitle)
        columns, height = shutil.get_terminal_size(fallback=(80, 24))
        lines = [part for line in subtitle.splitlines() for part in
                 (textwrap.wrap(line, width=max(20, columns - 4), replace_whitespace=False) or [''])]
        size = max(3, min(12, height - sum(1 + bool(row.detail) for row in rows) - 8))
        page, pages = 0, max(1, (len(lines) + size - 1) // size)
        if pages > 1:
            instructions = (instructions or '↑↓ move · Enter select · Esc back · q quit') + ' · PageUp/PageDown details'
        options = {"instructions": instructions or ('↑↓ move · Enter expand/select · Esc collapse/back · q return to chat'
            if self.menu_renderer.ansi else 'Enter an option number; blank selects highlighted; back collapses; q returns to chat')}
        while not self._quit:
            detail = '\n'.join(lines[page * size:(page + 1) * size])
            if pages > 1:
                detail += f'\nDetails page {page + 1}/{pages}'
            self.menu_renderer.render(title=title, subtitle=detail, rows=rows,
                                      selected=selected, notice=self.notice, reference_page=reference_page, **options)
            reference_page = getattr(self.menu_renderer, 'reference_page', 0)
            self.notice = ""
            event = self.menu_input.read_event()
            if event.action in {MenuAction.PAGE_UP, MenuAction.PAGE_DOWN} and rows[selected].references:
                reference_page = max(0, reference_page + (1 if event.action == MenuAction.PAGE_DOWN else -1))
                continue
            reference_page = 0
            selected, handled = navigate_menu(event, selected, len(rows))
            if handled:
                continue
            if event.action == MenuAction.QUIT:
                self._quit = True
                return
            if event.action == MenuAction.BACK:
                return None
            if event.action == MenuAction.PAGE_DOWN:
                page = min(page + 1, pages - 1)
                continue
            if event.action == MenuAction.PAGE_UP:
                page = max(0, page - 1)
                continue
            if event.action == MenuAction.ACTIVATE:
                self._selected_row = selected
                return selected

    async def review_candidates(self, *, target_id=None, all_roles=False) -> None:
        if self.clients.candidates is None:
            self.report("candidate service unavailable\n")
            return
        selected = 0
        page = 0
        page_size = 10
        while not self._quit:
            try:
                records = tuple(r for r in self.clients.candidates.candidates()
                                if all_roles or (r.role == self.role and (target_id is None or r.target == target_id)))
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
                rows.append(MenuRow(f"{item.role} · {item.candidate_id[:10]} · {item.algorithm} · {item.target}",
                    _candidate_status(item.status) + (' · ' + getattr(item, 'assessment', '') if getattr(item, 'assessment', '') else '')))
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
            evidence = ('' if sections else
                        "\n".join(f"{safe_terminal_text(k)}: {safe_terminal_text(v)}" for k, v in record.evidence))
            rows = []
            row_actions = []
            can_adopt = record.status in {"proposed", "reviewed", "deferred", "selected_for_next_session"}
            can_save = record.status in {"proposed", "reviewed", "deferred"}
            if can_adopt and self.clients.activation is not None:
                rows.append(MenuRow("Set default and start a new session", "Changes this profile's default and opens an empty session"))
                row_actions.append("adopt")
            if can_save:
                rows.append(MenuRow("Set as next-session default", "Changes saved configuration; the current session continues"))
                row_actions.append("defer")
            if record.status in {"proposed", "reviewed", "deferred"}:
                rows.append(MenuRow("Discard candidate"))
                row_actions.append("reject")
            rows.append(MenuRow("Back"))
            row_actions.append(None)
            selected = len(rows) - 1 if selected is None else min(selected, len(rows) - 1)
            self.menu_renderer.render(title=f"Candidate {record.candidate_id[:10]} · {_candidate_status(record.status)}",
                subtitle=f"{safe_terminal_text(record.algorithm)} · {safe_terminal_text(record.target)}\n"
                    + safe_terminal_text(getattr(record, 'assessment', '')) + '\n' + safe_terminal_text(evidence)
                    + f"\n\n{safe_terminal_text(sections[section_index].title) if sections else 'Changes'} ({page + 1}/{max(1, (len(lines) + page_size - 1)//page_size)}):\n" + "\n".join(safe_terminal_text(line) for line in chunk),
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
                            subtitle=getattr(record, 'assessment', '') + "\nThe current conversation remains in its original session. This profile's saved default will change.",
                            rows=(MenuRow("Start a fresh session with this candidate"), MenuRow("Cancel"))):
                        self.report("Candidate activation cancelled.\n")
                        continue
                    await self.clients.activation.adopt_candidate(candidate_id)
                    self.report("Candidate activated in a new session.\n")
                else:
                    if action == "defer" and record.status == "selected_for_next_session":
                        self.report("Candidate is already saved for the next session.\n")
                    else:
                        if action == 'defer' and not self.confirm_choice(title='Confirm default change',
                            subtitle=getattr(record, 'assessment', '') + "\nThis changes the profile's saved default for future sessions. The candidate is already stored.",
                            rows=(MenuRow('Set as next-session default'), MenuRow('Cancel'))):
                            self.report('Default change cancelled.\n')
                            continue
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

