"""Lab evidence navigation and stopping installed once per job."""
import inspect
from typing import Any

from fruitfly_agent.improvement.contracts.stopping import StopDecision
from fruitfly_agent.runtime_spec.documents import mapping
from ..termination.policies import BoundedStopPolicy
from fruitfly_agent.improvement.contracts.versions import canonical_json


def extension_spec(extension):
    if extension is None:
        return None
    configuration = getattr(extension, 'configuration', None)
    if not isinstance(configuration, dict):
        raise ValueError('workflow extensions require an explicit configuration identity')
    value = {'implementation': getattr(extension, 'implementation_id',
        getattr(extension, '__module__', type(extension).__module__) + '.' +
        getattr(extension, '__qualname__', type(extension).__qualname__)), 'configuration': configuration}
    # Return detached JSON so subsequent plugin mutation cannot rewrite a preview.
    import json
    return json.loads(canonical_json(value))


def install_workflow_mechanisms(context, *, stop_policy=None):
    from ..termination.policies import BoundedStopPolicy, NoImprovement, FailureLimit
    from ..termination.composition import AnyOf
    from ..evidence.rounds import RoundIndex
    RoundIndex(context).install()
    settings = context.workflow_settings or {}
    policies: list[Any] = []
    if settings.get('no_improvement_rounds', 0):
        policies.append(NoImprovement(settings['no_improvement_rounds']))
    if settings.get('consecutive_failures', 0):
        policies.append(FailureLimit(settings['consecutive_failures']))
    policies.append(stop_policy or BoundedStopPolicy())
    if context.hooks_factory is not None:
        context.hooks_factory(context)
    return AnyOf(*policies)
