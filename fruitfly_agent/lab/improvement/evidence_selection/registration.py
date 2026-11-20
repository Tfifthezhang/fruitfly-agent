"""Join Catalog's shared configuration and optimization declarations."""
from dataclasses import asdict
import json
from fruitfly_agent.lab.catalog.configuration import ConfigurationSurface
from .configuration import MaterialSettings, MATERIAL_PACKAGE
from .improvement import MaterialTarget


def normalize(parameters):
    settings = asdict(MaterialSettings.from_parameters(parameters))
    settings['optional_categories'] = list(settings['optional_categories'])
    return {'settings': settings}


def edit_options(fields, bounds):
    options = {'editable_fields': list(fields), 'bounds': dict(bounds)}
    MaterialTarget().validate_options(options)
    return options


def target(state, context, parameters):
    return MaterialTarget(MaterialSettings.from_parameters(parameters))


def restore(parameters, text):
    return {'settings': asdict(MaterialSettings.from_parameters(json.loads(text)))}


def surface():
    return ConfigurationSurface('improvement-evidence-selection', 'I', 'settings', 'evidence_selection', normalize,
        edit_options=edit_options, restore=restore, standalone=True, default_resource=(MATERIAL_PACKAGE, 'defaults.yaml'),
        optimization=MaterialTarget.optimization, target_factory=target,
        kind=MaterialTarget.component_kind, schema='evidence-selection-v1', artifact_slot='improvement-evidence-selection')
