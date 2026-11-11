"""Strict named worker documents; runtime hosts bind roles and material grants."""
from dataclasses import dataclass, asdict
import math
import re
from fruitfly_agent.runtime_spec.documents import mapping
from .configuration import default


@dataclass(frozen=True)
class WorkerDefinition:
    description: str
    model_role: str
    instructions: str
    capabilities: dict
    inheritance: dict
    limits: dict
    result: dict

    @classmethod
    def from_dict(cls, value):
        names = set(cls.__dataclass_fields__)
        data = mapping(value, names, 'worker')
        if set(data) != names:
            raise ValueError('worker requires its complete declared shape')
        for name in ('description', 'model_role', 'instructions'):
            if not isinstance(data[name], str) or not data[name].strip() or len(data[name]) > 120000:
                raise ValueError('worker text fields require bounded nonempty strings')
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*', data['model_role']):
            raise ValueError('worker model_role must name a declared role')
        caps = mapping(data['capabilities'], {'tools', 'resources', 'writes', 'delegation'}, 'worker capabilities')
        if set(caps) != {'tools', 'resources', 'writes', 'delegation'}:
            raise ValueError('worker requires explicit capabilities')
        tools = caps['tools']
        if (not isinstance(tools, list) or any(not isinstance(v, str) or v not in {'catalog', 'search', 'read'} for v in tools)
                or len(set(tools)) != len(tools)):
            raise ValueError('worker tools must be a distinct read-only evidence subset')
        if caps['resources'] != 'assigned' or caps['writes'] != 'deny' or caps['delegation'] != 'disabled':
            raise ValueError('worker capabilities cannot broaden assigned read-only authority')
        inheritance = mapping(data['inheritance'], {'conversation', 'state'}, 'worker inheritance')
        if inheritance != {'conversation': 'explicit_materials', 'state': 'independent'}:
            raise ValueError('workers require explicit materials and independent state')
        limits = mapping(data['limits'], {'seconds', 'model_requests', 'evidence_characters', 'evidence_responses'}, 'worker limits')
        if set(limits) != {'seconds', 'model_requests', 'evidence_characters', 'evidence_responses'}:
            raise ValueError('worker requires complete execution and evidence limits')
        for name, value in limits.items():
            if (isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value)
                    or value <= 0 or name != 'seconds' and type(value) is not int):
                raise ValueError('worker limits must be finite positive values; counts must be integers')
        if limits['seconds'] > 3600 or limits['model_requests'] > 512:
            raise ValueError('worker execution limits exceed supported bounds')
        result = mapping(data['result'], {'contract', 'max_characters'}, 'worker result')
        if (set(result) != {'contract', 'max_characters'} or result['contract'] != 'evidence_findings'
                or type(result['max_characters']) is not int or not 1 <= result['max_characters'] <= 24000):
            raise ValueError('worker requires a bounded evidence_findings result')
        # Copy normalized data; never retain mutable caller dictionaries.
        return cls(data['description'], data['model_role'], data['instructions'],
            {**caps, 'tools': list(tools)}, dict(inheritance), dict(limits), dict(result))

    def to_dict(self):
        return asdict(self)


def worker_definitions(parameters):
    value = parameters.get('workers', default('settings.workers'))
    if not isinstance(value, dict):
        raise ValueError('workers must map names to complete worker documents')
    workers = {}
    for name, data in value.items():
        if not isinstance(name, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*', name):
            raise ValueError('worker names must be stable identifiers')
        workers[name] = WorkerDefinition.from_dict(data)
    return workers
