"""Bounded result previews shared by model tools and parent notifications."""
import json
from .configuration import ResultSettings

def bounded(value, *, settings=None):
    """Keep status/result previews bounded without omitting execution identities."""
    settings = settings if settings is not None else ResultSettings()
    if 'executions' in value:
        rows = [bounded(row, settings=settings) for row in value['executions']]
        value = {**value, 'executions': rows}
        if len(json.dumps(value)) > settings.max_preview_characters:
            value = {**value, 'previews_omitted': True, 'executions': [
                {k: row[k] for k in ('agent_id', 'run_id', 'state', 'cleanup', 'result_reference', 'result_resource', 'error') if k in row}
                for row in rows]}
        return value
    if 'task' in value:
        return {**value, 'task': value['task'][:settings.task_preview_characters], 'task_characters': len(value['task']), 'summary': value.get('summary', '')[:settings.summary_preview_characters]}
    return value
