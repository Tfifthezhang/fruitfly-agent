"""Temporary experiment inputs and deterministic candidate generation."""
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
    models = {'models': {name: {'provider': 'anthropic', 'model': 'offline-' + name,
        'api_key_env': 'EXPERIMENT_TEST_KEY', 'context_window': 16000, 'max_output_tokens': 1024}
        for name in ('executor', 'editor', 'assessor')}}
    (directory / 'default-models.yaml').write_text(yaml.safe_dump(models))
    (directory / 'default-config.yaml').write_text(yaml.safe_dump({'schema_version': 1,
        'default_profile': 'baseline', 'profiles': {'baseline': {'model': {'catalog': 'default-models.yaml',
            'profile': 'executor'}, 'mechanisms': []}}}))
    (directory / 'secrets.env').write_text('EXPERIMENT_TEST_KEY=offline-placeholder\n')
    path = directory / 'experiment.yaml'
    path.write_text(yaml.safe_dump({'schema_version': 1,
        'task': task or {'source': 'files', 'instruction': 'Complete the explicit task.'}, **sections}))
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
