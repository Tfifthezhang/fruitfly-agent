"""Catalog declaration for independent comparison method selection."""
from .improvement import ComparisonTarget, POLICY_FIELDS
from fruitfly_agent.lab.catalog.configuration import ConfigurationSurface
from fruitfly_agent.runtime_spec.documents import mapping, parameter_default
from typing import Any

_RESOURCE = (__package__ + '.methods.measured', 'defaults.yaml')
_ROLES = {'model': 'assessor', 'measured': None}


def normalize(parameters):
    mapping(parameters, {'settings'}, 'comparison parameters')
    settings = mapping(parameters.get('settings', {}), {'method', *POLICY_FIELDS, 'bootstrap_resamples', 'bootstrap_seed'}, 'comparison settings')
    method = settings.get('method', parameter_default(*_RESOURCE, 'settings.method'))
    if not isinstance(method, str) or method not in _ROLES:
        raise ValueError('unknown improvement comparison method')
    effective: dict[str, Any] = {'method': method}
    for key, (low, high) in POLICY_FIELDS.items():
        value = settings.get(key, parameter_default(*_RESOURCE, 'settings.' + key))
        if value is not None and (method != 'measured' or type(value) not in (int, float) or not low <= value <= high):
            raise ValueError('invalid measured comparison threshold: ' + key)
        effective[key] = value
    for key, low, high in (('bootstrap_resamples', 100, 100000), ('bootstrap_seed', 0, 2**32 - 1)):
        value = settings.get(key, parameter_default(*_RESOURCE, 'settings.' + key))
        if type(value) is not int or not low <= value <= high:
            raise ValueError('invalid comparison setting: ' + key)
        effective[key] = value
    return {'settings': effective}


def method_and_role(component_settings):
    method = normalize(component_settings.get('comparison', {}))['settings']['method']
    return method, _ROLES[method]


def apply_thresholds(parameters, manifest):
    settings = normalize(parameters)['settings']
    return {**manifest, **{key: settings[key] for key in POLICY_FIELDS if settings[key] is not None}}


def edit_options(fields, bounds):
    if bounds:
        raise ValueError('comparison thresholds use the registered bounds')
    options = {'editable_fields': list(fields)}
    ComparisonTarget().validate_options(options)
    return options


def target(state, context, parameters):
    return ComparisonTarget(parameters)


def surface():
    return ConfigurationSurface('improvement-comparison', 'I', 'settings', 'comparison', normalize,
                                standalone=True, default_resource=_RESOURCE,
                                edit_options=edit_options, optimization=ComparisonTarget.optimization,
                                target_factory=target, kind=ComparisonTarget.component_kind,
                                schema='comparison-settings-v1', artifact_slot='improvement-comparison')
