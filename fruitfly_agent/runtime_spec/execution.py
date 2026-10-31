"""Portable scalar execution settings; never serialize live Core capabilities."""
from dataclasses import asdict, fields
from collections.abc import Mapping
import json

from fruitfly_agent.core.config import AgentLoopConfig, ToolExecutionConfig

LIMITS = {'max_turns': 0, 'max_tool_calls_per_turn': 0, 'max_context_recovery_attempts': 1}
TOOL_FIELDS = frozenset({'max_parallel', 'default_execution_mode'})


def validate_execution(value):
    if not isinstance(value, Mapping) or set(value) - {*LIMITS, 'tool_execution'}:
        raise ValueError('execution contains unsupported fields')
    result = dict(value)
    for key, minimum in LIMITS.items():
        if key in result and result[key] is None and key in {'max_turns', 'max_tool_calls_per_turn'}:
            continue
        if key in result and (type(result[key]) is not int or result[key] < minimum):
            raise ValueError('execution.' + key + ' must be an integer of at least ' + str(minimum))
    if 'tool_execution' in result:
        tools = result['tool_execution']
        if not isinstance(tools, Mapping) or set(tools) - TOOL_FIELDS:
            raise ValueError('execution.tool_execution contains unsupported fields')
        tools = dict(tools)
        if 'max_parallel' in tools and (type(tools['max_parallel']) is not int or tools['max_parallel'] < 1):
            raise ValueError('execution.tool_execution.max_parallel must be a positive integer')
        mode = tools.get('default_execution_mode', 'parallel')
        if not isinstance(mode, str) or mode not in {'parallel', 'sequential'}:
            raise ValueError('execution.tool_execution.default_execution_mode is invalid')
        result['tool_execution'] = tools
    return result


def execution_values(value):
    supplied = validate_execution(value)
    defaults = {f.name: f.default for f in fields(AgentLoopConfig) if f.name in LIMITS}
    return {**defaults, **supplied, 'tool_execution': {
        **asdict(ToolExecutionConfig()), **supplied.get('tool_execution', {})}}


def execution_kwargs(value):
    result = execution_values(value)
    result['tool_execution'] = ToolExecutionConfig(**result['tool_execution'])
    return result


def effective_execution(config):
    return {**{name: getattr(config, name) for name in LIMITS}, 'tool_execution': asdict(config.tool_execution)}


def parse_execution(text):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('duplicate execution field')
            result[key] = value
        return result
    try:
        value = json.loads(text, object_pairs_hook=unique)
    except (ValueError, TypeError) as exc:
        raise ValueError('execution policy must be a JSON object') from exc
    return execution_values(value)


def flatten_execution(value):
    value = execution_values(value)
    return {**{key: item for key, item in value.items() if key != 'tool_execution'},
            **{'tool_execution.' + key: item for key, item in value['tool_execution'].items()}}


def apply_profile_binding(profile, kind, key, text):
    """Apply a validated declarative configuration binding, without artifact I/O."""
    from dataclasses import replace
    if kind == 'configuration' and key.startswith('component.'):
        name = key.removeprefix('component.')
        def unique(pairs):
            values = {}
            for name, value in pairs:
                if name in values:
                    raise ValueError('duplicate component parameter')
                values[name] = value
            return values
        parameters = json.loads(text, object_pairs_hook=unique)
        if not isinstance(parameters, dict):
            raise ValueError('component parameters must be an object')
        if not any(m.mechanism_id == name and m.enabled for m in profile.mechanisms):
            raise ValueError('parameter binding requires an existing enabled component')
        return replace(profile,
            mechanisms=tuple(replace(m, parameters=parameters) if m.mechanism_id == name else m for m in profile.mechanisms),
            component_documents=profile.component_documents)
    if kind != 'configuration' or key != 'execution':
        raise ValueError('unsupported configuration binding')
    return replace(profile, execution=parse_execution(text))


def apply_execution_payload_binding(payload, kind, key, text):
    """Project a validated owner binding into the recorded execution identity."""
    if kind != 'configuration':
        raise ValueError('execution identity requires a configuration binding')
    if key == 'execution':
        return {**payload, 'execution': parse_execution(text)}
    if key.startswith('component.'):
        name = key.removeprefix('component.')
        values = json.loads(text)
        if not isinstance(values, dict) or not any(c['id'] == name for c in payload['components']):
            raise ValueError('parameter identity requires an existing component')
        return {**payload, 'components': [{**c, 'parameters': values} if c['id'] == name else c
            for c in payload['components']]}
    raise ValueError('unsupported configuration identity binding')
