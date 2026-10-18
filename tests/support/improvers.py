"""Offline improver substitution and terminal fixtures."""
from queue import Queue
from unittest.mock import Mock
from fruitfly_agent.lab.catalog import builtin_catalog, MechanismDefinition, MechanismDescriptor, MechanismContribution, ParameterDescriptor
from fruitfly_agent.lab.improvement.api import SearchPreview, TextProposal, TEXT_IMPROVER_COMPONENT
from fruitfly_agent.run.application import RunApplicationFactory
from tests.support.materials import _write_models, _write_cases
from tests.support.faux_provider import FauxProvider
from tests.support.terminal import menu_choice


class QueueEditor:
    def __init__(self):
        self.lines = Queue()
        self.output = None
        self.offset = 0
    def read_line(self):
        line = self.lines.get(timeout=3)
        if self.output is not None:
            rendered = self.output.getvalue()[self.offset:]
            self.offset = len(self.output.getvalue())
            if line.startswith('@'):
                return menu_choice(line[1:], rendered)
        return line
    def send(self, *lines):
        for line in lines:
            self.lines.put(line)


class OfflineImprover:
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


def custom_definition(improver_type=OfflineImprover):
    return MechanismDefinition(
        MechanismDescriptor('offline-search', 'Offline search', 'Alternative text algorithm',
            contributions=(MechanismContribution('improvement', 'context'),),
            exclusive_group='text-improver',
            parameters=(ParameterDescriptor('target', 'string', 'Target', 'Named text target', 'base_prompt'),)),
        lambda state, context, params: state.with_component(TEXT_IMPROVER_COMPONENT, context.own(improver_type(params['target']))),
        implementation_id='offline-v1',
        selection_group='text-improver', selection_group_label='Text improver',

        implementation_path='tests/support/improvers.py',
        documentation_path='tests/support/README.md',
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
