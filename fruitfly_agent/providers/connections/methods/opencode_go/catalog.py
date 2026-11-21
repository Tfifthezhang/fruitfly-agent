"""Normalize Go inference catalog metadata; missing limits stay unavailable."""
from __future__ import annotations
from typing import Any

def parse_models(value: Any) -> list[dict[str, Any]]:
    rows = value.get('data') if isinstance(value, dict) else None
    if not isinstance(rows, list) or value.get('has_more'):
        raise ValueError('Incomplete Go model directory')
    result = []
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get('id'), str):
            raise ValueError('Invalid Go model directory')
        if row.get('type', 'chat') != 'chat':
            continue
        limits = row.get('limit', {})
        caps = row.get('capabilities', {})
        def supported(name: str) -> bool:
            flag = caps.get(name, {})
            return flag.get('supported') is True if isinstance(flag, dict) else flag is True
        modalities = row.get('modalities', {}).get('input', [])
        reasoning = caps.get('reasoning')
        declared = reasoning.get('effort') if isinstance(reasoning, dict) else None
        efforts = tuple(dict.fromkeys(value for value in declared if isinstance(value, str)
            and value in {'none', 'minimal', 'low', 'medium', 'high', 'xhigh', 'max'})) if isinstance(declared, list) else ()
        result.append({'id': row['id'], 'name': row.get('name', row['id']),
            'context_window': limits.get('context'), 'max_output_tokens': limits.get('output'),
            'input_limit': limits.get('input'),
            'pricing': _pricing(row),
            **({'options': {'reasoning_effort': list(efforts)}} if efforts and supported('reasoning') else {}),
            'capabilities': {'tools': supported('tools'), 'streaming': True,
                'reasoning': supported('reasoning'),
                'vision': any(str(m).startswith('image') for m in modalities)}})
    return result


def _pricing(row: dict[str, Any]) -> dict[str, Any]:
    import math
    def mapping(value: Any) -> dict[str, Any]:
        return value if isinstance(value, dict) else {}

    cost = mapping(mapping(row.get('cost')).get('text'))
    input_cost = mapping(cost.get('input'))
    output_cost = mapping(cost.get('output'))
    cache_cost = mapping(input_cost.get('cache'))
    result: dict[str, Any] = {}
    for name, value in (('input_usd_per_million', input_cost.get('price')),
                        ('output_usd_per_million', output_cost.get('price')),
                        ('cache_read_usd_per_million', cache_cost.get('read')),
                        ('cache_write_usd_per_million', cache_cost.get('write'))):
        if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value >= 0:
            result[name] = value
    go = row.get('go', {})
    allowance = go.get('monthly_usage') if isinstance(go, dict) else None
    if isinstance(allowance, dict):
        result['monthly_usage'] = {k: v for k, v in allowance.items() if isinstance(k, str)
            and isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) and v >= 0}
    return result
