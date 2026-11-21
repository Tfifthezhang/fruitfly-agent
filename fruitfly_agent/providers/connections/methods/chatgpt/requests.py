"""Public ChatGPT plan Responses constraints, not legacy backend endpoints."""
from __future__ import annotations
from typing import Any

UNSUPPORTED = frozenset({'temperature', 'top_p', 'top_logprobs', 'user', 'prompt_cache_retention'})

class ChatGPTRequests:
    def validate(self, options: dict[str, Any]) -> None:
        if options.keys() & UNSUPPORTED or options.get('extra_body') or options.get('extra_headers'):
            raise ValueError('Unsupported ChatGPT plan request parameters')

    def prepare(self, request: dict[str, Any], session_id: str) -> dict[str, Any]:
        result = dict(request)
        result.pop('max_output_tokens', None)
        result['store'] = False
        tools = result.pop('tools', [])
        if tools:
            result['tools'] = [{'type': 'namespace', 'name': 'fruitfly', 'description': 'Client tools', 'tools': tools}]
        if isinstance(result.get('tool_choice'), dict) and result['tool_choice'].get('type') == 'function':
            result['tool_choice'] = {**result['tool_choice'], 'namespace': 'fruitfly'}
        result['input'] = [{**item, 'namespace': 'fruitfly'} if item.get('type') == 'function_call'
            and 'namespace' not in item else item for item in result['input']]
        return result
