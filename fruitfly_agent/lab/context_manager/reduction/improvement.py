"""Owner-controlled H surfaces; grants and trials use existing component contracts."""
from dataclasses import fields
from fruitfly_agent.lab.improvement.components.parameters import editable_parameters


def expose(definition, config_type, *, protected=()):
    return editable_parameters(definition, {f.name for f in fields(config_type)} - set(protected))
