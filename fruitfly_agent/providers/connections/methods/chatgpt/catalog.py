"""Normalize the authenticated ChatGPT catalog without guessing model limits."""
from __future__ import annotations
from typing import Any

def parse_models(value: Any) -> list[dict[str, Any]]:
    rows = value.get('models') if isinstance(value, dict) else None
    if not isinstance(rows, list) or value.get('has_more'):
        raise ValueError('Incomplete ChatGPT model directory')
    result = []
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get('slug'), str):
            raise ValueError('Invalid ChatGPT model directory')
        if row.get('visibility') != 'list':
            continue
        result.append({'id': row['slug'], 'name': row.get('display_name', row['slug']),
            'context_window': row.get('context_window'),
            'max_output_tokens': row.get('max_output_tokens'),
            'capabilities': {'tools': True, 'streaming': True,
                'reasoning': True, 'vision': 'image' in row.get('input_modalities', [])}})
    return result
