"""Install shared request measurement without a selectable policy surface."""
from dataclasses import replace
from .budget import MeasurementConfig, MeasurementService


def install(state, context):
    meter = state.config.context_meter or MeasurementService(MeasurementConfig())
    meter.validate_provider(state.config.provider)
    return replace(state, config=replace(state.config, context_meter=meter))
