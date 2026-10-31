"""Object-owned execution configuration, independently editable as H."""
from fruitfly_agent.improvement.contracts.optimization import OptimizationSpec, OptimizationField
from dataclasses import replace
import json

from fruitfly_agent.runtime_spec import effective_execution, parse_execution, execution_kwargs, execution_values
from fruitfly_agent.improvement.contracts.optimization import TargetBinding, TargetSnapshot


class ExecutionPolicyTarget:
    optimization = OptimizationSpec('H', 'parameters', required_capabilities=frozenset({'execution-config'}))
    label = 'Execution policy'
    component_kind = 'execution-policy'
    required_capabilities = frozenset({'execution-config'})

    def __init__(self, config, *, fixed_fields=()):
        self.fixed_fields = frozenset(fixed_fields) | {'max_turns','max_tool_calls_per_turn'}
        self.values = effective_execution(config)

    def snapshot(self):
        return TargetSnapshot('execution-policy', json.dumps({'settings':self.values}, sort_keys=True),
            TargetBinding('configuration', 'execution'), 'execution-policy-v1', 'H')

    def describe_fields(self, text=None):
        values = self.values if text is None else parse_policy(text)
        descriptions = {
            'max_tool_calls_per_turn': 'Optional daily tool attempts per turn; protected and disabled in Improvement trials.',
            'max_turns': 'Maximum turn/continuation allowance; this is not a total model-request limit.',
            'max_context_recovery_attempts': 'Maximum attempts to recover an input-capacity failure before ending execution.',
            'tool_execution.max_parallel': 'Maximum concurrent tools in a batch; does not establish data independence.',
            'tool_execution.default_execution_mode': 'Default tool-batch ordering; tool-owned sequential or exclusive requirements remain authoritative.'}
        return tuple(OptimizationField('parameters.settings.' + name, 'choice' if isinstance(value, str) else 'integer',
            descriptions[name], value, flatten(execution_values({}))[name],
            minimum=(1 if name in {'max_context_recovery_attempts', 'tool_execution.max_parallel'} else 0) if isinstance(value, int) else None,
            unit='count' if isinstance(value, int) else '',
            choices=('parallel', 'sequential') if isinstance(value, str) else ())
            for name, value in flatten(values).items() if name not in self.fixed_fields)

    def export_text(self,text):
        return json.dumps(parse_policy(text),sort_keys=True)

    def validate(self, text):
        self.validate_change(text, {})

    def prepare_trial(self, config, text):
        return replace(config, **execution_kwargs(parse_policy(text)))

    def validate_options(self, options):
        if not isinstance(options, dict) or set(options) - {'editable_fields', 'bounds'}:
            raise ValueError('execution-policy options need editable_fields/bounds')
        names = {'parameters.settings.'+name for name in set(flatten(self.values))-self.fixed_fields}
        editable = options.get('editable_fields', sorted(names))
        bounds = options.get('bounds', {})
        if (not isinstance(editable, list) or not editable or any(not isinstance(v, str) for v in editable)
                or len(set(editable)) != len(editable) or set(editable) - names or not isinstance(bounds, dict)
                or set(bounds) - set(editable)):
            raise ValueError('execution-policy options cite unsupported fields')
        for key, values in bounds.items():
            if (not isinstance(values, dict) or not values or set(values) - {'minimum', 'maximum'}
                    or any(type(v) is not int for v in values.values())
                    or not isinstance(flatten(self.values)[key.removeprefix('parameters.settings.')], int)
                    or values.get('minimum', 0) > values.get('maximum', float('inf'))):
                raise ValueError('execution-policy bounds must be ordered integer limits')
        self.validate_change(self.snapshot().text, options)

    def validate_change(self, text, options):
        before, after = flatten(self.values), flatten(parse_policy(text))
        paths=options.get('editable_fields',['parameters.settings.'+name for name in set(before)-self.fixed_fields])
        if any(not p.startswith('parameters.settings.') for p in paths):raise ValueError('execution fields require canonical settings paths')
        editable={p.removeprefix('parameters.settings.')for p in paths}
        if editable & self.fixed_fields:
            raise ValueError('execution field is controlled by another enabled mechanism')
        if any(after[key] != value for key, value in before.items() if key not in editable):
            raise ValueError('candidate changed a fixed execution field')
        for path, bounds in options.get('bounds', {}).items():
            key=path.removeprefix('parameters.settings.')
            if not bounds.get('minimum', -float('inf')) <= after[key] <= bounds.get('maximum', float('inf')):
                raise ValueError('candidate execution field exceeds experiment bounds: ' + key)


def parse_policy(text):
    def unique(pairs):
        result={}
        for key,value in pairs:
            if key in result:raise ValueError('duplicate execution policy field')
            result[key]=value
        return result
    value=json.loads(text,object_pairs_hook=unique)
    if not isinstance(value,dict) or set(value)!={'settings'}:raise ValueError('execution policy requires settings')
    return execution_values(value['settings'])


def flatten(value):
    return {**{key: item for key, item in value.items() if key != 'tool_execution'},
            **{'tool_execution.' + key: item for key, item in value['tool_execution'].items()}}


def validate_component_options(name, options, inventory):
    from types import SimpleNamespace
    if name != 'execution-policy':
        raise ValueError('component does not expose structured options: ' + name)
    target = ExecutionPolicyTarget(SimpleNamespace(**execution_kwargs(inventory.execution)),
        fixed_fields=dict(inventory.execution_owners))
    target.validate_options(options)


def configuration_surface():
    from fruitfly_agent.lab.catalog.configuration import ConfigurationSurface
    from fruitfly_agent.runtime_spec import validate_execution
    def options(fields, bounds):
        if any(not field.startswith('parameters.settings.') for field in fields):
            raise ValueError('execution grants must select parameters fields')
        return {'editable_fields':list(fields),'bounds':dict(bounds)}
    def normalize(value):
        if not isinstance(value,dict) or set(value)-{'settings'}:raise ValueError('execution policy requires settings')
        return validate_execution(value.get('settings',{}))
    return ConfigurationSurface('execution-policy','H','configuration','execution',normalize,
        encode=lambda values:json.dumps(values),decode=lambda text:{'settings':json.loads(text)},edit_options=options)
