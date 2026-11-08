"""Temporary experiment inputs and deterministic candidate generation."""
from tests.support.configuration import profile_document
from dataclasses import replace
import json
from pathlib import Path
import yaml

from fruitfly_agent.lab.improvement.api import StageBindings
from fruitfly_agent.lab.improvement.editor.generators import GeneratorRegistry
from fruitfly_agent.improvement.contracts.candidates import CandidateBundle, EditReason
from fruitfly_agent.improvement.contracts.components import ComponentFile, HarnessSnapshot
from fruitfly_agent.improvement.contracts.editing import ProposalResult
from tests.support.task_execution import TaskApplicationFixture as RunApplicationFactory
from tests.support.improvers import FirstSelector


def workspace(root, *, task=None, **sections):
    directory = root / '.fruitfly'
    directory.mkdir(exist_ok=True)
    models = {'models': {name: {'sdk': 'anthropic', 'protocol': 'messages', 'model': 'offline-' + name,
        'api_key_env': 'EXPERIMENT_TEST_KEY', 'context_window': 16000, 'max_output_tokens': 1024}
        for name in ('executor', 'editor', 'assessor')}}
    (directory / 'models.yaml').write_text(yaml.safe_dump(models))
    profile = profile_document(catalog='models.yaml', executor='executor')
    profile['models']['roles'].update(sections.pop('models', {}))
    task = task or {'source': 'files', 'instruction': 'Complete the explicit task.'}
    values = sections.pop('improvement', {})
    component_ids = values.get('components', ['improvement-editor'] if task.get('source') == 'editor' else ['base_prompt'])
    field_defaults = {
        'base_prompt': ['parameters.instructions.system'],
        'improvement-editor': ['parameters.instructions.' + key for key in ('propose', 'system', 'reflect')]}
    edit = {}
    options = values.get('component_options', {})
    for name in component_ids:
        default = field_defaults.get(name, ['parameters.instructions.system'])
        option = options.get(name, {})
        edit[name] = {'fields': list(option['editable_fields'])
                      if 'editable_fields' in option else default}
        if 'bounds' in option:
            edit[name]['bounds'] = dict(option['bounds'])
    multi = sections.pop('multi_task', {})
    times = values.get('timeouts', {'editor_seconds':1200, 'execution_seconds':3600, 'evaluator_seconds':1200})
    execution = {key: values[key] for key in ('generator', 'direction') if key in values}
    execution.update(editor_seconds=times['editor_seconds'], task_seconds=times['execution_seconds'])
    if multi.get('execution'):
        execution['trial'] = multi['execution']
    if multi.get('sampling'):
        execution['sampling'] = multi['sampling']
    promotion = dict(multi.get('promotion', {}))
    if 'every_rounds' in promotion:
        execution['promotion_every_rounds'] = promotion.pop('every_rounds')
    evaluation = {'evaluator_seconds':times['evaluator_seconds'], 'scope':values.get('scope', 'task'),
        'comparison': {**multi.get('evaluation', {}), **promotion}}
    config = {'default_profile': 'baseline', 'profiles': {'baseline': profile}}
    (directory / 'default-config.yaml').write_text(yaml.safe_dump(config))
    (directory / 'secrets.env').write_text('EXPERIMENT_TEST_KEY=offline-placeholder\n')
    document = {'baseline': {'config': 'default-config.yaml'}, 'tasks': {'inline': task}, 'edit': edit,
        'execution':execution, 'evaluation':evaluation, **sections}
    path = directory / 'experiment.yaml'
    path.write_text(yaml.safe_dump(document))
    return path


class Rule:
    generator_id = 'agent-editor-v1'
    required_capabilities = frozenset()

    async def propose(self, request, services):
        documents = []
        for document in request.baseline.components:
            if document.component_id in request.plan.component_ids:
                from tests.support.configuration import component_parameters, component_text, with_component_parameters, with_component_text
                values = component_parameters(document)
                if document.role == 'I':
                    values['instructions']['propose'] += ' STEP'
                    document = with_component_parameters(document, values)
                else:
                    text = component_text(document) + '\nSynthetic revision'
                    document = with_component_text(document, text)
            documents.append(document)
        return ProposalResult((CandidateBundle(request.plan.parent, request.baseline, HarnessSnapshot(tuple(documents)),
            self.generator_id, tuple(EditReason(name, 'Synthetic observed difference', (request.records[0].run_id,), expected_effect='The proposed behavior appears in the subsequent execution.')
                for name in request.plan.component_ids)),))


def factory_builder(registry):
    def build(prepared, path):
        generators = GeneratorRegistry()
        generators.register(Rule.generator_id, Rule)
        return RunApplicationFactory(cwd=prepared.config.workspace, environment=prepared.environment,
            config_path=str(path), profile_id=prepared.profile.profile_id, provider_registry=registry,
            improvement_bindings=StageBindings(generators=generators))
    return build
