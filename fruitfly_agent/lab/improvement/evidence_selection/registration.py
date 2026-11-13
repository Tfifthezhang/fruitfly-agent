"""Join Catalog's shared configuration and optimization declarations."""
from dataclasses import asdict
from fruitfly_agent.lab.catalog.configuration import ConfigurationSurface
from .configuration import SelectionSettings, PACKAGE
from .improvement import SelectionTarget


def normalize(parameters):
    return {'settings': asdict(SelectionSettings.from_parameters(parameters))}


def edit_options(fields, bounds):
    options = {'editable_fields': list(fields), 'bounds': dict(bounds)}
    SelectionTarget().validate_options(options)
    return options


def target(state, context, parameters):
    return SelectionTarget(SelectionSettings.from_parameters(parameters))


def surface():
    return ConfigurationSurface('improvement-evidence-selection', 'I', 'settings', 'evidence_selection', normalize,
        edit_options=edit_options, standalone=True, default_resource=(PACKAGE, 'defaults.yaml'),
        optimization=SelectionTarget.optimization, target_factory=target,
        kind=SelectionTarget.component_kind, schema='evidence-selection-v1', artifact_slot='improvement-evidence-selection')
