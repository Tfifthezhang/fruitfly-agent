"""Mode-aware H grants through the shared parameter materializer."""
from dataclasses import fields
from fruitfly_agent.lab.improvement.components.parameters import editable_parameters
from .config import LayeredCompactionConfig

PROTECTED = frozenset({'mode', 'summary_model_profile'})
SUMMARY_FIELDS = frozenset({'summary_instructions', 'summary_target_tokens', 'summary_max_output_tokens',
    'summary_input_max_tokens', 'summary_timeout_seconds'})
EDITABLE = frozenset(f.name for f in fields(LayeredCompactionConfig)) - PROTECTED


def available_fields(parameters):
    return EDITABLE if parameters['mode'] == 'hybrid' else EDITABLE - SUMMARY_FIELDS


def register(definition):
    return editable_parameters(definition, EDITABLE, available_fields=available_fields)
