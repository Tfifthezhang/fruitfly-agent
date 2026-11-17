"""Read Provider receipts independently from derived trajectory conversion."""
import json
from fruitfly_agent.improvement.execution.facts import model_usage_facts
from fruitfly_agent.lab.improvement.evidence.decoding import decode_rows


def receipt_usage_facts(value):
    """Adapt native Core Usage receipts to the internal reporting vocabulary."""
    requests = value['requests']
    if value.get('schema_version') != 1 or type(value.get('used')) is not int or value['used'] < 0 or value['used'] != len(requests) or len({r['id'] for r in requests}) != len(requests):
        raise ValueError('invalid usage receipt')
    fields = {'inputTokens': 'input_tokens', 'outputTokens': 'output_tokens',
              'cacheReadTokens': 'cache_read_tokens', 'cacheCreationTokens': 'cache_creation_tokens'}
    rows = []
    for request in requests:
        usage = request.get('usage')
        converted = {target: usage[source] for source, target in fields.items() if source in usage} if isinstance(usage, dict) else None
        rows.extend(({'kind': 'request', 'id': request['id']},
                     {'kind': 'response', 'attempt_id': request['id'], 'usage': converted}))
    return model_usage_facts(rows, value['used'])


def retained_usage(directory):
    receipt = directory / 'model-usage.json'
    if receipt.is_file():
        value = json.loads(receipt.read_bytes())
        facts = receipt_usage_facts(value)
        return {v.resource: v.used for v in facts}, 'provider-receipts'
    rows, _, gaps = decode_rows((directory / 'session.jsonl').read_text(encoding='utf-8'))
    totals, reported = {}, 0
    for row in rows:
        message = row.value.get('message', {})
        usage = message.get('usage')
        if message.get('role') != 'assistant' or not isinstance(usage, dict):
            continue
        reported += 1
        for native, key in (('inputTokens', 'input_tokens'), ('outputTokens', 'output_tokens')):
            val = usage.get(native)
            if type(val) is int and val >= 0:
                totals[key] = totals.get(key, 0) + val
    # Legacy canonical totals cover only retained messages, never auxiliary calls.
    return {**{f'reported_{k}': v for k, v in totals.items()},
            **{k: None if gaps else v for k, v in totals.items()},
            'reported_model_calls': reported}, 'canonical-message-subtotals'
