"""Plain-text observation of active content and pending attributed updates."""


def render_state(state, *, kind='skill', detailed=False):
    if kind == 'memory' and not detailed:
        lines = ['Memory location: ' + (state.get('memory_path') or 'unavailable'),
            'Automatic upkeep: ' + ('enabled' if state.get('auto_enabled') else 'disabled'),
            'Trigger state: ' + ('blocked by unresolved batches' if state.get('blocked') else
                'automatic upkeep is queued' if state.get('auto_enabled') and state.get('automatic_due')
                else 'below thresholds' if state.get('auto_enabled') else 'automatic upkeep is disabled')]
        if state.get('error'):
            lines.append('Last upkeep error: ' + state['error'])
        active = state.get('operations', ())
        for row in active:
            lines.append('Paused batch: ' + row['id'] + ' · ' + row['status'] + ' · ' + row['operation'])
            if row['status'] == 'running':
                lines.append('Memory upkeep is running. Use /memory details to inspect counters.')
            elif row.get('recoverable') is False:
                lines.append('This legacy batch has no recovery journal. Use /memory discard ' + row['id'] + ' to end it without deleting evidence, then /memory run.')
            elif 'conditions' in str(state.get('error', '')).lower():
                lines.append('Environment changed. Restore its original conditions, or run /memory discard ' + row['id'] + ' then /memory run to start with current conditions.')
            elif row['status'] in {'retry-authorized', 'retry-generation'}:
                lines.append('Retry is already authorized. Use /memory run ' + row['id'] + ' to resume this batch.')
            else:
                lines.append('To authorize retry: /memory retry ' + row['id'])
        if state.get('can_run_manually'):
            lines.append('Manual upkeep: /memory run')
        lines.append('For counters and retained documents: /memory details')
        if state.get('refresh_pending'):
            lines.append('Saved memory will load after the next checked session refresh.')
        if state.get('refresh_error'):
            lines.append('Refresh failed; this session uses its previous snapshot. ' + state['refresh_error'])
        return '\n'.join(lines) + '\n'
    lines = []
    for entry in state['entries']:
        source = entry.get('origin')
        details = (' · ' + source['source'] + '@' + source['revision']) if source else (
            ' · ' + entry.get('kind', '') + ' · ' + entry.get('status', ''))
        lines.extend((entry.get('name', entry['id']), '  ' + ' '.join(entry['description'].split()),
            '  ' + details.removeprefix(' · '), ''))
    if not lines:
        lines.append('No retained documents.')
    if 'user_chars' in state:
        lines.append(f"Unprocessed user characters: {state['user_chars']}; new completed turns: {state['user_turns']}")
    lines.extend('Pending update: ' + row['id'] + ' · ' + row['operation'] for row in state['pending'])
    for row in state.get('operations', ()):
        action = ('/memory run ' + row['id'] if row['status'] in {'retry-authorized', 'retry-generation'}
            else '/memory retry ' + row['id'])
        lines.append('Maintenance operation (' + row['status'] + '): ' + row['id'] + ' · ' + row['operation'] +
            '; use ' + action + '.')
    if state.get('error'):
        lines.append('Maintenance: ' + state['error'])
    if state.get('refresh_pending'):
        lines.append('Saved memory awaits the next checked session refresh.')
    if state.get('refresh_error'):
        lines.append('Memory refresh failed; this task uses the previous snapshot. ' + state['refresh_error'])
    return '\n'.join(lines) + '\n'
