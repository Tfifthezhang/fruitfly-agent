"""Measurement parameters are H; precision and protocol integrity are protected."""
from fruitfly_agent.lab.improvement.components.parameters import editable_parameters


def expose(definition):
    return editable_parameters(definition, {'token_estimator', 'chars_per_token', 'margin_tokens',
        'margin_ratio', 'count_timeout_seconds', 'calibration_samples'})
