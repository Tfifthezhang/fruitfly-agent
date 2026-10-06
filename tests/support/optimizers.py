"""Offline optimizer substitution and terminal fixtures."""
from queue import Queue
from unittest.mock import Mock
from fruitfly_agent.lab.catalog import builtin_catalog, MechanismDefinition, MechanismDescriptor, MechanismContribution, ParameterDescriptor
from fruitfly_agent.lab.optimization.text_optimizer import SearchPreview, TextProposal, TEXT_OPTIMIZER_COMPONENT
from fruitfly_agent.run.application import RunApplicationFactory
from tests.support.materials import _write_models, _write_cases
from tests.support.faux_provider import FauxProvider


class QueueEditor:
    def __init__(self):
        self.lines = Queue()
    def read_line(self):
        return self.lines.get(timeout=3)
    def send(self, *lines):
        for line in lines:
            self.lines.put(line)


class OfflineOptimizer:
    def __init__(self, target):
        self.target = target
        self.calls = 0
    def preview(self, *, task=None):
        return SearchPreview('offline-search', 'Offline search', 'No network or model calls', target_id=self.target)
    async def search(self, text, direction, *, parent_manifest, task=None):
        self.calls += 1
        return (TextProposal(text + '\nUse exact answers.', 'offline-search', evidence=(('Rule', 'deterministic append'),)),)
    def cancel(self):
        return False


def custom_definition(optimizer_type=OfflineOptimizer):
    return MechanismDefinition(
        MechanismDescriptor('offline-search', 'Offline search', 'Alternative text algorithm',
            contributions=(MechanismContribution('optimization', 'context'),),
            exclusive_group='text-optimizer',
            parameters=(ParameterDescriptor('target', 'string', 'Target', 'Named text target', 'base_prompt'),)),
        lambda state, context, params: state.with_component(TEXT_OPTIMIZER_COMPONENT, context.own(optimizer_type(params['target']))),
        implementation_id='offline-v1',
        selection_group='text-optimizer', selection_group_label='Text optimizer',
    )

def offline_factory(root, algorithm='offline-search', target='base_prompt', definition=None):
    _write_models(root)
    _write_cases(root)
    registry = Mock()
    registry.create.side_effect = lambda *_: FauxProvider()
    catalog = builtin_catalog().extended((definition or custom_definition(),))
    factory = RunApplicationFactory(cwd=root, environment={}, catalog=catalog, provider_registry=registry)
    factory.configuration.set_mechanism(algorithm, enabled=True)
    factory.configuration.set_parameter(algorithm, 'target', target)
    factory.configuration.save()
    factory.reload_configuration()
    return factory
