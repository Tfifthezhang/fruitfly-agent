"""Deterministic presentation helpers used by tool owners, not the terminal."""
from fruitfly_agent.core.data_model import TextBlock
from fruitfly_agent.core.tool_runtime.presentation import ToolPresentation


def file_call(operation, arguments):
    target = str(arguments.get('path', ''))[:800]
    if operation == 'read':
        if 'character_offset' in arguments:
            target += ' · character ' + str(arguments['character_offset'])
        elif 'offset' in arguments or 'limit' in arguments:
            target += ' · line ' + str(arguments.get('offset', 1))
            if 'limit' in arguments:
                target += ' · limit ' + str(arguments['limit'])
    return ToolPresentation(operation, target)


def text_result(operation, result):
    text = '\n'.join(block.text for block in result.content if isinstance(block, TextBlock))
    rows = [row.strip() for row in text.splitlines() if row.strip()]
    summary = (rows[0][:220] + (' … ' + rows[-1][:120] if len(rows) > 1 else '')) if rows else ''
    status = result.details.get('status', '')
    state = {'completed': 'succeeded'}.get(status, status)
    return ToolPresentation(operation, summary=summary, execution_state=state)


def web_result(operation, result):
    details = result.details
    if operation == 'search':
        count = len(details.get('results', ()))
        return ToolPresentation(operation, summary=f'{count} results', items=count)
    start, end = details.get('start_line'), details.get('end_line')
    return ToolPresentation(operation, summary=f'Lines {start}–{end} of {details.get("total_lines")}'
        + (' · truncated' if details.get('truncated') else ''))
