"""Register the independent group composition policy."""
from fruitfly_agent.lab.catalog.configuration import ConfigurationSurface
from fruitfly_agent.runtime_spec.documents import mapping, parameter_default

from .improvement import GroupingTarget, MAX_BATCH_SIZE
from .methods.fixed.algorithm import select as fixed
from .methods.random.algorithm import select as random

_RESOURCE = (__package__ + '.methods.fixed', 'defaults.yaml')
METHODS = {'fixed': fixed, 'random': random}
RELATION_METHODS = frozenset({'failure', 'text', 'trajectory', 'matched', 'diverse'})


def normalize(parameters):
    mapping(parameters, {'settings'}, 'grouping parameters')
    keys = ('method', 'batch_size', 'seed')
    supplied = mapping(parameters.get('settings', {}), keys, 'grouping settings')
    settings = {key: supplied.get(key, parameter_default(*_RESOURCE, 'settings.' + key)) for key in keys}
    method, size, seed = (settings[key] for key in keys)
    if not isinstance(method, str) or method not in {*METHODS, *RELATION_METHODS}:
        raise ValueError('unknown improvement grouping method')
    if type(size) is not int or not 1 <= size <= MAX_BATCH_SIZE or type(seed) is not int:
        raise ValueError('grouping requires a positive batch size and integer seed')
    return {'settings': settings}


def edit_options(fields, bounds):
    if bounds:
        raise ValueError('grouping size uses the registered bounds')
    options = {'editable_fields': list(fields)}
    GroupingTarget().validate_options(options)
    return options


def target(state, context, parameters):
    return GroupingTarget(parameters)


def surface():
    return ConfigurationSurface('improvement-grouping', 'I', 'settings', 'grouping', normalize,
                                standalone=True, default_resource=_RESOURCE,
                                edit_options=edit_options, optimization=GroupingTarget.optimization,
                                target_factory=target, kind=GroupingTarget.component_kind,
                                schema='group-settings-v1', artifact_slot='improvement-grouping')
