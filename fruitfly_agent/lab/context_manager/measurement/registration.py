"""Shared request measurement, selected separately from reduction."""
from dataclasses import replace
from functools import partial
from fruitfly_agent.core.mechanisms import MechanismDescriptor, MechanismContribution, MechanismEffects
from fruitfly_agent.lab.catalog.models import MechanismDefinition
from ..registration import parameters, validate
from .budget import MeasurementConfig, MeasurementService
from .improvement import expose


def definition():
    return expose(MechanismDefinition(MechanismDescriptor('context-measurement', 'Context measurement',
        'Measure final request inputs with explicit precision and conservative usage calibration.',
        contributions=(MechanismContribution('capability', 'context'),), default_enabled=True, install_order=55,
        parameters=parameters(MeasurementConfig), effects=MechanismEffects(uses_network=True,
            cost_notice='Optional exact input counting contacts a declared Provider endpoint.')),
        install, implementation_id='context-measurement-v1',
        implementation_path='fruitfly_agent/lab/context_manager/measurement/budget.py',
        documentation_path='fruitfly_agent/lab/context_manager/measurement/README.md',
        validate_parameters=partial(validate, MeasurementConfig)))


def install(state, context, values):
    meter = MeasurementService(MeasurementConfig(**values))
    meter.validate_provider(state.config.provider)
    return replace(state, config=replace(state.config, context_meter=meter)).with_component('context-measurement', meter)
