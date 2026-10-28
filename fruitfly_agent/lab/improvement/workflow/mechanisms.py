"""Lab policies installed per job; the kernel owns no research decisions."""
import inspect
from typing import Any

from fruitfly_agent.improvement.contracts.stopping import StopDecision
from fruitfly_agent.runtime_spec.documents import mapping
from ..termination.policies import BoundedStopPolicy
from ..research import ResearchLedger
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


def mechanism_parameters(parameters):
    definitions: dict[str, dict[str, Any]] = {
        'research': {'enabled': False, 'max_entries': 128, 'retrieve_entries': 8, 'guidance': ''},
        'progress': {'patience': 0, 'failure_patience': 0},
        'finalization': {'reserve_model_calls': 0, 'reserve_executions': 0}}
    result = {}
    for name, defaults in definitions.items():
        supplied = mapping(parameters.get(name, {}), set(defaults), name)
        values = {**defaults, **supplied}
        for key, value in values.items():
            if key == 'enabled':
                if type(value) is not bool:
                    raise ValueError('research.enabled must be boolean')
            elif key == 'guidance':
                if not isinstance(value, str) or len(value) > 4000:
                    raise ValueError('research.guidance must be at most 4000 characters')
            elif type(value) is not int or not 0 <= value <= 10000:
                raise ValueError(name + '.' + key + ' must be an integer in 0..10000')
        if name == 'research' and not 1 <= values['retrieve_entries'] <= values['max_entries'] <= 256:
            raise ValueError('research requires 1 <= retrieve_entries <= max_entries <= 256')
        result[name] = values
    return result


class FinalizationReserve:
    def __init__(self, services, parameters):
        self.services, self.parameters, self.scope = services, parameters, None

    def start(self, event):
        self.scope = self.services.budget.child({'model': self.parameters['reserve_model_calls'],
                                               'execution': self.parameters['reserve_executions']})

    def release(self, event=None):
        if self.scope is not None:
            self.scope.close()
            self.scope = None

    def exhausted(self):
        if self.scope is None:
            return False
        return any(self.parameters[key] and self.services.budget.available(kind) == 0
                   for key, kind in (('reserve_model_calls', 'model'), ('reserve_executions', 'execution')))

    async def aclose(self):
        self.release()


class ResearchStopPolicy:
    def __init__(self, base, progress, reserve):
        self.base, self.progress, self.reserve = base, progress, reserve

    async def decide(self, state):
        if self.reserve.exhausted():
            return StopDecision('finalization_reserve')
        for key, counter in (('patience', state.consecutive_no_gain), ('failure_patience', state.consecutive_failures)):
            if self.progress[key] and counter >= self.progress[key]:
                return StopDecision('progress.' + key)
        value = self.base.decide(state)
        return await value if inspect.isawaitable(value) else value


def install_workflow_mechanisms(context, *, stop_policy=None):
    parameters = mechanism_parameters((context.system_settings or {}).get('search', {}))
    services = context.services
    if parameters['research']['enabled']:
        ResearchLedger(context, **{k: v for k, v in parameters['research'].items() if k != 'enabled'}).install()
    reserve = services.own(FinalizationReserve(services, parameters['finalization']))
    services.hooks.register('before_run', reserve.start, required=True, priority=0, identity='finalization-reserve')
    services.hooks.register('before_finalization', reserve.release, required=True, priority=0, identity='finalization-reserve')
    if context.hooks_factory is not None:
        context.hooks_factory(context)
    return ResearchStopPolicy(stop_policy or BoundedStopPolicy(), parameters['progress'], reserve)
