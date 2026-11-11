"""Five bounded model operations over one borrowed delegation service."""
import json
import math
from functools import partial
from typing import Any
from fruitfly_agent.core.errors import Result
from fruitfly_agent.core.data_model import AgentToolResult, TextBlock
from fruitfly_agent.core.tool_runtime import AgentTool
from fruitfly_agent.core.tool_runtime.authorization import ToolPermission
from .service import SubagentError
from .views import bounded

NAMES = ('spawn', 'send', 'wait', 'status', 'cancel')

def create_tools(service, instructions, *, workers=()):
    protocol, results = service.protocol, service.results
    def text(length):
        return {'type': 'string', 'minLength': 1, 'maxLength': length}
    identity = {'agent_id': text(128), 'run_id': text(128)}
    specs = {
        'spawn': ({'task': text(protocol.max_task_characters), 'context': {'type': 'string', 'maxLength': protocol.max_context_characters}}, ['task']),
        'send': ({**identity, 'mode': {'type': 'string', 'enum': ['steer', 'followup']}, 'message': text(protocol.max_message_characters)}, ['agent_id', 'run_id', 'mode', 'message']),
        'wait': ({'executions': {'type': 'array', 'minItems': 1, 'maxItems': service.max_agents,
            'items': {'type': 'object', 'properties': identity, 'required': ['agent_id', 'run_id'], 'additionalProperties': False}},
            'mode': {'type': 'string', 'enum': ['all', 'any']},
            'timeout_seconds': {'type': 'number', 'minimum': 0, 'maximum': protocol.max_wait_seconds}}, ['executions']),
        'status': ({**identity, 'output_offset': {'type': 'integer', 'minimum': 0}, 'offset': {'type': 'integer', 'minimum': 0}, 'limit': {'type': 'integer', 'minimum': 1, 'maximum': results.max_list_entries}}, []),
        'cancel': (identity, ['agent_id', 'run_id']),
    }
    if workers:
        specs['spawn'][0].update(worker={'type': 'string', 'enum': list(workers)},
            materials={'type': 'array', 'minItems': 1, 'maxItems': 256,
                'items': {'type': 'string', 'minLength': 1, 'maxLength': 16000}})
        specs['spawn'][1].extend(['worker', 'materials'])
    def specs_schema(action):
        properties, required = specs[action]
        return {'type': 'object', 'properties': properties, 'required': required, 'additionalProperties': False}
    tools = []
    for action in NAMES:
        async def execute(ctx, action=action):
            args = ctx.args
            if not validate(specs_schema(action), args).is_ok:
                return AgentToolResult(content=[TextBlock(json.dumps({'ok': False, 'error': 'invalid_arguments'}))], is_error=True)
            try:
                receipt_key = (ctx.tool_call_id, action)
                request_text = json.dumps(args, sort_keys=True)
                if action in {'spawn', 'send'} and receipt_key in service.receipts:
                    original, receipt = service.receipts[receipt_key]
                    if original != request_text:
                        raise SubagentError('call_identity_conflict')
                    return receipt
                if action == 'spawn':
                    value = service.spawn(args['task'], args.get('context', ''), worker=args.get('worker', ''), materials=tuple(args.get('materials', ())))
                elif action == 'send':
                    value = service.send(args['agent_id'], args['run_id'], args['mode'], args['message'])
                elif action == 'cancel':
                    value = await service.cancel(args['agent_id'], args['run_id'])
                elif action == 'wait':
                    value = await service.wait([(r['agent_id'], r['run_id']) for r in args['executions']],
                        mode=args.get('mode', 'all'), timeout_seconds=args.get('timeout_seconds', protocol.default_wait_seconds), signal=ctx.signal)
                    for row in value['executions']:
                        if row['state'] not in {'queued', 'running', 'cancelling'} and not row['delivered']:
                            service.offered_results[row['run_id']] = ctx.tool_call_id
                elif args.get('agent_id'):
                    value = service.detail(args['agent_id'], args.get('run_id'))
                    if 'output_offset' in args:
                        result = service.store.read_result(value)
                        output = result['output'] if result is not None else ''
                        offset = args['output_offset']
                        value = {**value, 'output': output[offset:offset + results.output_page_characters], 'output_characters': len(output),
                            'next_output_offset': offset + results.output_page_characters if offset + results.output_page_characters < len(output) else None}
                else:
                    if args.get('run_id') or 'output_offset' in args:
                        raise SubagentError('invalid_arguments')
                    snap = service.snapshot()
                    rows = snap['executions']
                    offset, limit = args.get('offset', 0), args.get('limit', results.default_list_entries)
                    value = {**snap, 'executions': rows[offset:offset + limit],
                        'next_offset': offset + limit if offset + limit < len(rows) else None}
                result = AgentToolResult(content=[TextBlock(json.dumps({'ok': True, **bounded(value, settings=results)}))])
                if action in {'spawn', 'send'}:
                    service.receipts[receipt_key] = (request_text, result)
                return result
            except SubagentError as exc:
                return AgentToolResult(content=[TextBlock(json.dumps({'ok': False, 'error': exc.code}))], is_error=True)
        properties, required = specs[action]
        schema = {'type': 'object', 'properties': properties, 'required': required, 'additionalProperties': False}
        tools.append(AgentTool(name='subagent_' + action, label='Subagent ' + action,
            description=instructions[action + '_instructions'] + ('\nWorker options: ' + json.dumps(workers) if action == 'spawn' and isinstance(workers, dict) and workers else ''), permission=ToolPermission('agent_control'),
            parameters=schema, validate_arguments=partial(validate, schema), execute=execute))
    return tuple(tools)


def validate(schema: dict[str, Any], arguments: dict[str, Any]) -> Result[dict[str, Any]]:
    """Enforce declared bounds before and after hooks; Core's subset omits lengths."""
    def check(rule, value):
        kind = rule.get('type')
        if kind == 'object':
            if not isinstance(value, dict): return False
            properties = rule.get('properties', {})
            return (not (set(value) - set(properties)) and all(k in value for k in rule.get('required', ()))
                and all(check(properties[k], v) for k, v in value.items()))
        if kind == 'array':
            return isinstance(value, list) and rule.get('minItems', 0) <= len(value) <= rule.get('maxItems', 32) and all(check(rule['items'], item) for item in value)
        if kind == 'string':
            return isinstance(value, str) and rule.get('minLength', 0) <= len(value) <= rule.get('maxLength', 16000) and ('enum' not in rule or value in rule['enum'])
        if kind in {'integer', 'number'}:
            return (not isinstance(value, bool) and isinstance(value, int if kind == 'integer' else (int, float))
                and math.isfinite(value) and rule.get('minimum', -math.inf) <= value <= rule.get('maximum', math.inf))
        return False
    return Result.success(arguments) if check(schema, arguments) else Result.failure('invalid subagent arguments or bounds')

