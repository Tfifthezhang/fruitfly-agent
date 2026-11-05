"""Read Provider receipts independently from derived trajectory conversion."""
import json
from fruitfly_agent.improvement.execution.facts import model_usage_facts
from fruitfly_agent.lab.improvement.evidence.decoding import decode_rows


def retained_usage(directory):
    receipt = directory / 'model-usage.json'
    if receipt.is_file():
        value = json.loads(receipt.read_bytes())
        requests = value['requests']
        if value.get('schema_version') != 1 or type(value.get('used')) is not int or value['used'] != len(requests) or len({r['id'] for r in requests}) != len(requests):
            raise ValueError('invalid usage receipt')
        rows = [event for r in requests for event in (
            {'kind': 'request', 'id': r['id']},
            {'kind': 'response', 'attempt_id': r['id'], 'usage': r.get('usage')})]
        facts = model_usage_facts(rows, value['used'])
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
