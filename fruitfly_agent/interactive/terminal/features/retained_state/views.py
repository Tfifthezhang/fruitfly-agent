"""Plain-text observation of active content and pending attributed updates."""


def render_state(state):
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
    lines.extend('Unknown maintenance outcome: ' + row['id'] + ' · ' + row['operation'] +
        '; use /memory retry ' + row['id'] + ' to permit another potentially paid call.'
        for row in state.get('operations', ()))
    if state.get('error'):
        lines.append('Maintenance: ' + state['error'])
    return '\n'.join(lines) + '\n'
