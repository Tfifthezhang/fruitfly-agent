"""Stable conversation attribution on every Go request, including auxiliary calls."""
from __future__ import annotations
from typing import Any

class GoRequests:
    def prepare(self, request: dict[str, Any], session_id: str) -> dict[str, Any]:
        headers = dict(request.get('extra_headers', {}))
        headers.update({'User-Agent': 'fruitfly-agent/0.1', 'x-opencode-session': session_id})
        return {**request, 'extra_headers': headers}

    def receipt(self, usage: Any) -> dict[str, Any]:
        import math
        from ....replay import wire_value
        value = wire_value(usage)
        if not isinstance(value, dict):
            return {}
        extension = value.get('opencode', {})
        if not isinstance(extension, dict):
            return {}
        result: dict[str, Any] = {}
        source = extension.get('billing_source')
        if source in {'free', 'balance', 'go', 'go-plus', 'byok'}:
            result['billing_source'] = source
        for name, raw in (('charged_usd', value.get('cost')), ('allowance_usd', extension.get('allowance'))):
            if isinstance(raw, (int, float)) and not isinstance(raw, bool) and math.isfinite(raw) and raw >= 0:
                result[name] = raw
        return result
