"""Normalize immutable source events and preserve attributable relationships."""
import json
from typing import Any
from fruitfly_agent.improvement.contracts.versions import canonical_json, content_hash


def extract_events(resource, rows, source_format):
    events: list[dict[str, Any]] = []
    for row in rows:
        raw = row.value
        payload = raw.get('payload', raw.get('data', raw))
        if 'payload_json' in raw:
            try:
                payload = json.loads(raw['payload_json'])
            except (TypeError, ValueError):
                payload = {}
        payload = payload if isinstance(payload, dict) else {}
        message = raw.get('message', payload.get('message', payload))
        message = message if isinstance(message, dict) else {}
        base = {'source_path': resource.path, 'artifact_id': resource.artifact_id,
                'start': row.start, 'end': row.end, 'timestamp': raw.get('timestamp'),
                'elapsed_seconds': payload.get('elapsed_seconds'),
                'request_id': payload.get('request_id', message.get('requestId')),
                'operation_id': payload.get('operation_id', raw.get('operation_id')),
                'parent_id': raw.get('parentId', payload.get('parent_id')),
                'sequence': raw.get('position', {}).get('sequence') if isinstance(raw.get('position'), dict) else None,
                'phase': payload.get('stage', payload.get('phase')),
                'status': payload.get('status'), 'derived': source_format == 'atif',
                'tool_call_id': message.get('toolCallId', payload.get('tool_call_id')),
                'tool_name': payload.get('tool_name', message.get('toolName', message.get('tool_name'))),
                'is_error': message.get('isError', message.get('is_error', payload.get('is_error')))}
        def emit(kind, locator, **values):
            event = {**base, 'kind': kind, 'locator': row.locator + locator, **values}
            event['event_id'] = content_hash(canonical_json([resource.artifact_id, row.start, row.end, event['locator']]))
            # Token deltas remain in the original stream. Consecutive deltas
            # share one directory range instead of repeating metadata per token.
            group_fields = ('artifact_id', 'kind', 'request_id', 'operation_id', 'phase', 'tool_call_id')
            if kind in {'assistant_thinking_delta', 'assistant_text_delta', 'tool_output'} and events and all(
                    events[-1].get(k) == event.get(k) for k in group_fields):
                previous = events[-1]
                previous.update(end=row.end, record_count=previous.get('record_count', 1) + 1,
                                end_timestamp=event['timestamp'])
                previous['event_id'] = content_hash(canonical_json([
                    resource.artifact_id, previous['start'], previous['end'], previous['locator']]))
                return
            events.append(event)
        kind = raw.get('event') or raw.get('kind') or message.get('role') or raw.get('type', 'event')
        if source_format == 'model-usage':
            kind = 'model_request'
            base.update(request_id=raw.get('request_id') or raw.get('id'),
                        request_receipt_id=raw.get('id'), phase=raw.get('model_role'))
        emit(kind, '')
        blocks = message.get('content', [])
        if isinstance(blocks, list):
            for i, block in enumerate(blocks):
                if isinstance(block, dict) and block.get('type') == 'toolCall':
                    emit('toolCall', f'/message/content/{i}', tool_call_id=block.get('id'), tool_name=block.get('name'))
        if source_format == 'atif':
            for i, call in enumerate(raw.get('tool_calls', [])):
                emit('toolCall', f'/tool_calls/{i}', tool_call_id=call.get('tool_call_id'), tool_name=call.get('function_name'))
            for i, result in enumerate(raw.get('observation', {}).get('results', [])):
                emit('toolResult', f'/observation/results/{i}', tool_call_id=result.get('source_call_id'),
                     is_error=result.get('extra', {}).get('is_error'))
    return events


def correlate_events(events):
    # A derived trajectory can repeat native IDs. Correlate within each source.
    calls = {(e['artifact_id'], e['tool_call_id']): e for e in events
             if e['kind'] == 'toolCall' and e['tool_call_id']}
    for event in events:
        if event['kind'] != 'toolResult':
            continue
        owner = calls.get((event['artifact_id'], event['tool_call_id']))
        event['call_event_id'] = owner['event_id'] if owner else None
        event['relationship_status'] = 'matched' if owner else 'unmatched'
        if owner:
            event['tool_name'] = event['tool_name'] or owner['tool_name']
