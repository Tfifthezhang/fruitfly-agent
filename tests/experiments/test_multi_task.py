"""Actual Application task-set searches keep daily files and private material isolated."""
from tests.support.configuration import component_parameters, with_component_parameters, with_component_text, parameter_payload
from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from fruitfly_agent.experiments.configuration import load_configuration
from fruitfly_agent.experiments.composition import prepare_experiment, application_factory
from fruitfly_agent.experiments.operations.improve import run
from fruitfly_agent.experiments.records import RunRecords
from fruitfly_agent.lab.improvement.editor.generators import GeneratorRegistry
from tests.support.task_execution import TaskApplicationFixture as RunApplicationFactory
from tests.support.experiments import workspace, Rule
from tests.support.task_packs import install
from tests.support.model_evaluation import RoleProvider


class BatchRule(Rule):
    supports_task_sets = True


class MultiTaskExperimentTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        from tests.support.task_execution import collection_registry
        self.enterContext(patch('fruitfly_agent.experiments.task_sets.registry_for', side_effect=collection_registry))

    async def test_registered_task_set_runs_through_normal_application_and_retains_every_leaf(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            install(root)
            workspace(root, task={'source': 'task-set', 'collections': [{'id': 'daily', 'source': 'fixture', 'pack': 'project'}]})
            prepared = prepare_experiment(load_configuration(root), 'improvement')
            records = RunRecords(root)
            record = records.create('improvement', prepared.summary())
            provider = RoleProvider()
            for text in ('wrong', 'A', 'wrong', 'B'): provider.respond_text(text)
            registry = Mock(); registry.create.return_value = provider
            def builder(prepared, path):
                initial = application_factory(prepared, path, provider_registry=registry)
                generators = GeneratorRegistry(); generators.register(BatchRule.generator_id, BatchRule)
                return RunApplicationFactory(cwd=root, config_path=str(path), environment=prepared.environment,
                    provider_registry=registry, improvement_bindings=replace(initial.improvement_bindings, generators=generators))
            original = prepared.config_path.read_bytes()
            with patch('fruitfly_agent.experiments.operations.improve.application_factory', side_effect=builder):
                result = await run(prepared, record, records, lambda event: None)
            self.assertEqual(result['status'], 'completed')
            self.assertEqual(result['usage'], {'model': len(provider.calls), 'execution': 4})
            self.assertEqual(prepared.config_path.read_bytes(), original)
            self.assertIn('Official evaluation', record['links'])
            job = root / record['links']['Component job']
            output = json.loads((job / 'result.json').read_text())
            self.assertEqual(output['selected']['assessment']['score'], 1)
            self.assertTrue(list((job / 'executions').glob('*.json')))
            self.assertTrue(list((job / 'evaluations').glob('*.json')))
            self.assertTrue(list((job / 'comparisons').glob('*.json')))
            self.assertFalse(any('UNSEEN_INPUT' in call['messages'][0].content or 'SECRET_ANSWER' in call['system_prompt'] for call in provider.calls))

    def test_joint_check_is_provider_free_and_rejects_unsupported_parallelism(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); install(root)
            workspace(root, task={'source': 'task-set', 'collections': [{'id': 'daily', 'source': 'fixture', 'pack': 'project'}]},
                multi_task={'execution': {'candidate_concurrency': 2}})
            with self.assertRaisesRegex(ValueError, 'trial contains unknown fields'):
                load_configuration(root)

    def test_joint_check_preserves_material_and_supports_explicit_large_finite_times(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); install(root)
            workspace(root, task={'source': 'task-set', 'collections': [{'id': 'daily', 'source': 'fixture', 'pack': 'project'}]},
                improvement={'timeouts': {'editor_seconds': 20000, 'execution_seconds': 2000, 'evaluator_seconds': 1200}})
            before = {p: p.read_bytes() for p in root.rglob('*') if p.is_file()}
            with patch('fruitfly_agent.providers.registry.ProviderRegistry.create', side_effect=AssertionError('Provider constructed')):
                prepared = prepare_experiment(load_configuration(root), 'improvement')
            self.assertEqual(prepared.request.timeouts['editor_seconds'], 20000)
            self.assertEqual(before, {p: p.read_bytes() for p in root.rglob('*') if p.is_file()})

    async def test_registered_collections_reassemble_working_memory_candidates(self):
        from fruitfly_agent.interactive import AgentApplication
        from tests.support.task_packs import package
        from tests.support.faux_provider import FauxProvider
        from fruitfly_agent.lab.improvement.api import WorkflowBindings
        from fruitfly_agent.improvement.contracts.editing import ProposalResult
        from fruitfly_agent.improvement.contracts.candidates import CandidateBundle,EditReason
        from fruitfly_agent.improvement.contracts.components import ComponentFile,HarnessSnapshot
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            pack=package();pack['compatible_targets']=['working-memory-reduction'];install(root,pack)
            workspace(root,task={'source':'task-set','collections':[{'id':'memory','source':'fixture','pack':'project'}]},
                improvement={'components':['working-memory-reduction'],'component_options':{'working-memory-reduction':{
                    'editable_fields':['parameters.instructions.update']}}})
            import yaml
            path=root/'.fruitfly/default-config.yaml';document=yaml.safe_load(path.read_text())
            document['profiles']['baseline']['models']['roles']['working_memory'] = document['profiles']['baseline']['models']['roles']['executor']
            document['profiles']['baseline']['H']['working-memory-reduction']={'inline':{
                'id':'working-memory-reduction','role':'H','implementation':'working-memory-reduction',
                'parameters':{'settings':{'update_every_messages':1, 'maintenance_ratio':0.}}}}
            path.write_text(yaml.safe_dump(document))
            prepared=prepare_experiment(load_configuration(root),'improvement')
            class Provider(FauxProvider):
                def __call__(self,view,*,signal=None):
                    if view.system_prompt=='Maintain bounded task memory.':self.respond_text('memory')
                    elif 'Evaluate granted evidence' in view.system_prompt:
                        from tests.support.model_evaluation import judgment
                        self.respond(judgment(view))
                    else:self.respond_text('wrong')
                    return super().__call__(view,signal=signal)
            class Generator:
                generator_id='memory-collection';required_capabilities=frozenset();supports_task_sets=True
                async def propose(self,request,services):
                    old=request.baseline.component('working-memory-reduction');values=component_parameters(old)
                    values['instructions']['update']='CANDIDATE_COLLECTION: preserve evidence'
                    changed=with_component_parameters(old, values)
                    harness=HarnessSnapshot(tuple(changed if d.component_id==old.component_id else d for d in request.baseline.components))
                    return ProposalResult((CandidateBundle(request.plan.parent,request.baseline,harness,self.generator_id,
                        (EditReason(old.component_id,'Synthetic policy invocation.',(request.records[0].run_id,),expected_effect='Auxiliary requests use the candidate policy.'),)),))
            provider=Provider();providers=Mock();providers.create.return_value=provider
            generators=GeneratorRegistry();generators.register(Generator.generator_id,Generator)
            initial=application_factory(prepared,prepared.config_path,provider_registry=providers)
            factory=RunApplicationFactory(cwd=root,config_path=str(prepared.config_path),environment=prepared.environment,
                provider_registry=providers,improvement_bindings=replace(initial.improvement_bindings,generators=generators))
            app=AgentApplication(factory);await app.start()
            try:
                request=replace(prepared.request,generator_id=Generator.generator_id)
                await app.improve('',preview_token=app.workflow_preview(request).preview_token)
                outcome=factory._component_jobs.outcome
                self.assertEqual(outcome.stop_reason,'completed')
                self.assertTrue(all(trial.record.status=='completed' for evaluation in outcome.records for trial in evaluation.trials))
                calls=[call for call in provider.calls if call['system_prompt']=='Maintain bounded task memory.']
                self.assertTrue(any('CANDIDATE_COLLECTION' in repr(call['messages']) for call in calls))
                self.assertTrue(all('memory/checkpoints.json' in {resource.path for resource in trial.record.artifacts}
                    for evaluation in outcome.records for trial in evaluation.trials))
            finally:await app.close()
