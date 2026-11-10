"""Bounded result previews shared by model tools and parent notifications."""
import json

def bounded(value):
    """Keep status/result previews bounded without omitting execution identities."""
    if 'executions' in value:
        rows = [bounded(row) for row in value['executions']]
        value = {**value, 'executions': rows}
        if len(json.dumps(value)) > 24000:
            value = {**value, 'previews_omitted': True, 'executions': [
                {k: row[k] for k in ('agent_id', 'run_id', 'state', 'cleanup', 'result_reference', 'result_resource', 'error') if k in row}
                for row in rows]}
        return value
    if 'task' in value:
        return {**value, 'task': value['task'][:400], 'task_characters': len(value['task']), 'summary': value.get('summary', '')[:2000]}
    return value
