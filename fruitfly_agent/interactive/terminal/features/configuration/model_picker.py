"""Search and page cached subscription models without expanding project catalogs."""
from __future__ import annotations
import re
import time
from typing import Any
from fruitfly_agent.interactive.terminal.io.controls import cancellable_form
from .forms import CANCELLED
from fruitfly_agent.interactive.terminal.io.input import read_field_line
from fruitfly_agent.interactive.terminal.io.layout import columns_frame, terminal_size


@cancellable_form
def choose_subscription_model(form: Any, service: Any, integration: str, account: str) -> bool:
    query, page = '', 0
    focus = None
    while True:
        models = service.models(integration, account, query)
        capacity = _page_capacity(form)
        pages = max(1, (len(models) + capacity - 1) // capacity)
        page = min(page, pages - 1)
        visible = models[page * capacity:(page + 1) * capacity]
        values = tuple(m.id for m in visible) + ('Search…', 'Refresh models', 'Next page', 'Previous page', 'Back')
        labels = {m.id: ('★ ' if m.favorite else '') + m.label + (' · recent' if m.recent else '')
            + (' · unavailable' if not m.available else '') for m in visible}
        _, chosen = _live_choice(form, service, integration, account, query, page, title=f'Choose model · {integration} · {page + 1}/{pages}',
            subtitle=service.catalog_status(integration, account) + ('\nSearch: ' + query if query else ''),
            values=values, current=focus or values[0], labels=labels, focus=focus,
            details={m.id: model_details(m) for m in visible})
        if isinstance(chosen, tuple):
            chosen, visible, page, pages = chosen
        if chosen is CANCELLED or chosen == 'Back':
            return False
        if chosen == 'Search…':
            value = read_field_line(form.line_editor, 'Search models')
            if value is not None and value != '/cancel':
                query, page, focus = value, 0, None
            continue
        if chosen == 'Refresh models':
            service.refresh(integration, account)
            continue
        if chosen in ('Next page', 'Previous page'):
            page = min(pages - 1, max(0, page + (1 if chosen == 'Next page' else -1)))
            focus = None
            continue
        model = next(m for m in visible if m.id == chosen)
        focus = model.id
        if not model.available:
            from fruitfly_agent.interactive.contracts.configuration import ConfigurationActionResult
            form.apply(lambda: ConfigurationActionResult(model.reason))
            continue
        parameters = None
        options = getattr(model, 'options', {})
        while True:
            _, action = form.choose_value(title=model.label, subtitle=model_details(model),
                values=('Use model', 'Toggle favorite', 'Back') + (('Advanced settings…',) if options else ()),
                current='Use model')
            if action != 'Advanced settings…':
                break
            draft = dict(parameters or {})
            for name, choices in options.items():
                _, setting = form.choose_value(title=name.replace('_', ' ').capitalize(),
                    subtitle='Change this request option for this model.',
                    values=(None, *choices), current=draft.get(name),
                    labels={None: 'Service default'})
                if setting is CANCELLED:
                    break
                if setting is None:
                    draft.pop(name, None)
                else:
                    draft[name] = setting
            else:
                parameters = draft
        if action == 'Toggle favorite':
            service.toggle_favorite(integration, account, model.id)
            continue
        if action != 'Use model':
            continue
        context, output = model.context_window, model.output_limit
        try:
            if context is None:
                context = int(read_field_line(form.line_editor, 'Documented context window') or '')
            if output is None:
                output = int(read_field_line(form.line_editor, 'Documented maximum output tokens') or '')
        except ValueError:
            continue
        suggested = re.sub(r'[^A-Za-z0-9_.-]', '-', integration + '-' + model.id)[:80]
        alias = suggested
        while True:
            value = read_field_line(form.line_editor, 'Model label [' + alias + ']')
            if value is None or value == '/cancel':
                break
            alias = value.strip() or alias
            overrides = ', '.join(f'{key}: {value}' for key, value in (parameters or {}).items())
            _, confirmation = form.choose_value(title='Review model',
                subtitle=f'{alias}\n{integration} · {model.id}\nContext window: {context}\nOutput budget: {output}'
                         + ('\nRequest overrides: ' + overrides if overrides else ''),
                values=('Back', 'Stage model'), current='Back')
            if confirmation == 'Stage model':
                arguments = (integration, account, model.id, alias, context, output)
                if parameters is not None:
                    arguments += (parameters,)
                result = form.apply(service.stage, *arguments)
                if result is not None:
                    return True


def _page_capacity(form: Any, size: Any = None) -> int:
    if getattr(form.menu_input, 'poll_event', None) is None:
        return 8
    size = size or terminal_size(form.output)
    split = form.renderer.ansi and size.columns >= 86 and size.lines >= 16
    return max(1, size.lines - (9 if split else 14))


def _live_choice(form: Any, service: Any, integration: str, account: str, query: str, page: int, **initial: Any) -> Any:
    """Poll the single input owner while refreshed metadata arrives; preserve focus."""
    from fruitfly_agent.interactive.terminal.io.menu import MenuAction, MenuRow, MenuHelp, navigate_menu
    poll = getattr(form.menu_input, 'poll_event', None)
    focused = initial.pop('focus', None)
    if poll is None:
        # The shared renderer supports section labels without changing selection indices.
        return _section_choice(form, initial)
    selected, refresh_at, fingerprint = 0, 0.0, None
    rows, status = (), ''
    detail_offset = 0
    while True:
        if time.monotonic() >= refresh_at:
            rows = service.models(integration, account, query)
            status = service.catalog_status(integration, account)
            refresh_at = time.monotonic() + .5
        size = terminal_size(form.output)
        split = form.renderer.ansi and size.columns >= 86 and size.lines >= 16
        capacity = _page_capacity(form, size)
        pages = max(1, (len(rows) + capacity - 1) // capacity)
        position = next((i for i, model in enumerate(rows) if model.id == focused), None)
        page = position // capacity if position is not None else min(page, pages - 1)
        visible = rows[page * capacity:(page + 1) * capacity]
        controls = ('Search…', 'Refresh models')
        if page < pages - 1:
            controls += ('Next page',)
        if page > 0:
            controls += ('Previous page',)
        values = tuple(m.id for m in visible) + controls + ('Back',)
        labels = {m.id: ('★ ' if m.favorite else '') + m.label + (' · recent' if m.recent else '')
            + (' · unavailable' if not m.available else '') for m in visible}
        details = {m.id: model_details(m) for m in visible}
        selected = values.index(focused) if focused in values else min(selected, len(values) - 1)
        current = (size, values, tuple(labels.items()), tuple(details.items()), status, selected, detail_offset)
        if current != fingerprint:
            title = f'Choose model · {integration} · {page + 1}/{pages}'
            subtitle = status + (' · Search: ' + query if query else '')
            menu_rows = tuple(MenuRow(labels.get(value, value), section=model_section(value, visible),
                help=MenuHelp(labels.get(value, value), details.get(value, ''))) for value in values)
            if split:
                items = tuple(('› ' if i == selected else '  ') + row.label
                              for i, row in enumerate(menu_rows[:len(visible)]))
                footer = tuple(('› ' if i == selected else '  ') + row.section + ' · ' + row.label
                               for i, row in enumerate(menu_rows) if i >= len(visible))
                footer += ('↑↓ move · Enter select · PgUp/PgDn scroll details · Esc back',)
                form.output.write('\x1b[2J\x1b[H' + columns_frame(size.columns, size.lines,
                    title=title, subtitle=subtitle, left=items, detail=details.get(values[selected], ''),
                    footer=footer, detail_offset=detail_offset))
                form.output.flush()
            else:
                form.renderer.render(title=title, subtitle=subtitle, rows=menu_rows,
                    selected=selected, help_panel=True, instructions='↑↓ move · Enter select · Esc back')
            fingerprint = current
        event = poll(.1)
        if event.action in (MenuAction.BACK, MenuAction.QUIT):
            return False, CANCELLED
        if split and event.action in (MenuAction.PAGE_UP, MenuAction.PAGE_DOWN):
            detail_offset = max(0, detail_offset + (5 if event.action == MenuAction.PAGE_DOWN else -5))
            continue
        previous = selected
        selected, handled = navigate_menu(event, selected, len(values))
        focused = values[selected]
        if selected != previous:
            detail_offset = 0
        if not handled and event.action == MenuAction.ACTIVATE:
            return False, (focused, visible, page, pages)


def model_section(value: str, visible: Any) -> str:
    if any(m.id == value for m in visible):
        return 'Models'
    return {'Search…': 'Search', 'Refresh models': 'Provider directory',
            'Next page': 'Pages', 'Previous page': 'Pages', 'Back': 'Navigation'}.get(value, '')

def model_details(model: Any) -> str:
    lines = [f'Model ID: {model.id}', f'Context: {model.context_window or "unconfirmed"}',
             f'Maximum output: {model.output_limit or "unconfirmed"}']
    caps = getattr(model, 'capabilities', {})
    if caps:
        lines.append('Capabilities: ' + ', '.join(k + '=' + str(v).lower() for k, v in caps.items()))
    prices = getattr(model, 'pricing', {})
    for key, label in (('input_usd_per_million', 'Input USD / 1M tokens'),
                       ('output_usd_per_million', 'Output USD / 1M tokens'),
                       ('cache_read_usd_per_million', 'Cache read USD / 1M tokens'),
                       ('cache_write_usd_per_million', 'Cache write USD / 1M tokens')):
        if key in prices:
            lines.append(f'{label}: {prices[key]}')
    if prices.get('monthly_usage'):
        lines.append('Provider monthly allowance: ' + str(prices['monthly_usage']))
    lines.append('List prices are not a charge or remaining plan balance. Missing prices remain unknown.')
    if model.reason:
        lines.append(model.reason)
    return '\n'.join(lines)

def _section_choice(form: Any, initial: Any) -> Any:
    # Real FormIO owns a renderer; lightweight embedding forms may provide their own chooser.
    if not hasattr(form, 'renderer'):
        return form.choose_value(**initial)
    from fruitfly_agent.interactive.terminal.io.menu import MenuAction, MenuRow, MenuHelp, navigate_menu
    values = initial['values']
    current = initial['current']
    selected = values.index(current) if current in values else 0
    while True:
        rows = []
        for value in values:
            section = 'Models' if value in initial.get('details', {}) else model_section(value, ())
            label = initial.get('labels', {}).get(value, value)
            rows.append(MenuRow(label, section=section, help=MenuHelp(label, initial.get('details', {}).get(value, ''))))
        form.renderer.render(title=initial['title'], subtitle=initial['subtitle'], rows=tuple(rows),
            selected=selected, help_panel=True, instructions='Choose a number · Back returns to accounts')
        event = form.menu_input.read_event()
        if event.action in (MenuAction.BACK, MenuAction.QUIT):
            return False, CANCELLED
        selected, handled = navigate_menu(event, selected, len(values))
        if not handled and event.action == MenuAction.ACTIVATE:
            return False, values[selected]
