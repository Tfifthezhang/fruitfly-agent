"""Page complete compact execution rows without character-offset guessing."""
import json


def execution_page(workspace, *, cursor, limit, status=None, max_characters=24000):
    rows = json.loads(workspace.read('context/executions.json'))
    if status is not None:
        rows = [row for row in rows if row.get('status') == status]
    page = []
    size = 0
    for row in rows[cursor:cursor + limit]:
        length = len(json.dumps(row, ensure_ascii=False))
        if page and size + length > max_characters:
            break
        if length > max_characters:
            row = {'run_id': row['run_id'], 'summary_path': 'context/summaries/' + row['run_id'] + '.json',
                'note': 'Read the oversized summary through paged evidence access.'}
            length = len(json.dumps(row))
        page.append(row)
        size += length
    end = cursor + len(page)
    return {'executions': page, 'total': len(rows),
        'next_cursor': end if end < len(rows) else None,
        'note': 'Navigation only. Read context/summaries/<run_id>.json for citable facts.'}
