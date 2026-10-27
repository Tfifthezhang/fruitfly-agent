"""Temporary experiment inputs and deterministic candidate generation."""
from tests.support.configuration import profile_document
from dataclasses import replace
import json
from pathlib import Path
import yaml

from fruitfly_agent.lab.improvement.api import (WorkflowBindings, GeneratorRegistry,
    CandidateBundle, ComponentFile, HarnessSnapshot, EditReason, ProposalResult)
from fruitfly_agent.run import RunApplicationFactory
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
        'base_prompt': ['parameters.text'],
        'execution-workflow': ['parameters.steps'],
        'skill-document': ['parameters.initial_text'], 'learned-memory': ['parameters.initial_text'],
        'improvement-editor': ['parameters.instructions.' + key for key in ('propose', 'invariant', 'domain', 'compose')]}
    edit = {}
    options = values.get('component_options', {})
    for name in component_ids:
        if name == 'execution-policy':
            from fruitfly_agent.runtime_spec.execution import flatten_execution
            default = ['parameters.' + key for key in flatten_execution({})]
        else:
            default = field_defaults.get(name, ['parameters.text'])
        option = options.get(name, {})
        edit[name] = {'fields': ['parameters.' + key for key in option['editable_fields']]
                      if 'editable_fields' in option else default}
        if 'bounds' in option:
            edit[name]['bounds'] = {'parameters.' + key: bound for key, bound in option['bounds'].items()}
    comparison = {key: values[key] for key in ('scope', 'feedback') if key in values}
    search = {key: values[key] for key in ('strategy', 'generator', 'rounds', 'mode', 'width', 'retain_experience') if key in values}
    if 'exploration' in sections:
        search['exploration'] = sections.pop('exploration')['policy']
    multi = sections.pop('multi_task', {})
    trial = {key: values[key] for key in ()}
    trial.update(multi.get('execution', {}))
    if 'operation_timeout' in values:
        trial['operation_timeout_seconds'] = values['operation_timeout']
    if multi.get('sampling'):
        search['sampling'] = multi['sampling']
    promotion = dict(multi.get('promotion', {}))
    if 'every_rounds' in promotion:
        search['promotion_every_rounds'] = promotion.pop('every_rounds')
    comparison.update(multi.get('evaluation', {})); comparison.update(promotion)
    def settings_document(name, parameters):
        return {'inline': {'id': name, 'role': 'I', 'implementation': name, 'parameters': parameters}}
    if search:
        profile['I']['improvement-search'] = settings_document('improvement-search', search)
    if 'process_assessment' in sections:
        profile['I']['improvement-feedback'] = settings_document('improvement-feedback', {
            'process_assessment': sections.pop('process_assessment')})
    config = {'default_profile': 'baseline', 'profiles': {'baseline': profile}}
    (directory / 'default-config.yaml').write_text(yaml.safe_dump(config))
    (directory / 'secrets.env').write_text('EXPERIMENT_TEST_KEY=offline-placeholder\n')
    document = {'baseline': {'config': 'default-config.yaml'}, 'tasks': {'inline': task},
        'comparison': {'inline': comparison}, 'edit': edit,
        'budget': {key: values[key] for key in ('max_model_calls', 'max_executions', 'timeout_seconds') if key in values},
        'trial': trial, **sections}
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
                text = document.files[0].text
                if document.role == 'I':
                    value = json.loads(text)
                    value['propose'] += ' STEP'
                    text = json.dumps(value)
                else:
                    text += '\nSynthetic revision'
                document = replace(document, files=(ComponentFile('instructions.txt', text),))
            documents.append(document)
        return ProposalResult((CandidateBundle(request.plan.parent, request.baseline, HarnessSnapshot(tuple(documents)),
            self.generator_id, tuple(EditReason(name, 'Synthetic observed difference', (request.records[0].run_id,))
                for name in request.plan.component_ids)),))


def factory_builder(registry):
    def build(prepared, path):
        generators = GeneratorRegistry()
        generators.register(Rule.generator_id, Rule)
        return RunApplicationFactory(cwd=prepared.config.workspace, environment=prepared.environment,
            config_path=str(path), profile_id=prepared.profile.profile_id, provider_registry=registry,
            improvement_bindings=WorkflowBindings(generators=generators, selector=lambda *args: FirstSelector()))
    return build
