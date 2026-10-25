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
    if kind != 'configuration' or key != 'execution':
        raise ValueError('unsupported configuration binding')
    return replace(profile, execution=parse_execution(text))
