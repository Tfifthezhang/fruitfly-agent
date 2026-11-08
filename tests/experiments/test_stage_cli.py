"""A single editable document drives separate imports and detached proposals."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import yaml
from fruitfly_agent.experiments.cli import parser
from fruitfly_agent.experiments.operations.step import dispatch
from fruitfly_agent.core.config import AgentLoopConfig
from fruitfly_agent.core.data_model import AssistantMessage, ToolCallBlock, TextBlock, ToolResultMessage
from fruitfly_agent.core.model_stream import AssistantMessageEventStream
from tests.support.experiments import workspace
from tests.support.model_evaluation import RoleProvider


class StageCliTests(unittest.IsolatedAsyncioTestCase):
    async def test_document_import_and_two_proposals_inherit_selected_candidate(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve(); path = workspace(root)
            old = yaml.safe_load(path.read_text())
            trial = root / 'archive/artifacts/harbor/job/task'
            (trial / 'agent').mkdir(parents=True)
            (trial / 'result.json').write_text('{"task_name":"fixture"}')
            (trial / 'agent/session.jsonl').write_text(json.dumps({'message': {'role': 'user', 'content': 'Inspect deliverables'}}) + '\n')
            authored = {'research': {'id': 'study', 'output_root': '../study'},
                'baseline': old['baseline'], 'roles': {},
                'optimization': {'scope': 'explicit', 'include': old['edit']},
                'stages': {'import': {'source': 'eval', 'path': '../archive'},
                    'propose': {'direction': 'Verify actual results'}},
                'next': {'stage': 'import', 'publish_as': 'baseline'}}
            path.write_text('# Research controls\n' + yaml.safe_dump(authored, sort_keys=False))
            async def invoke(command='step'):
                args = parser().parse_args(['improvement', command, '--config', str(path)])
                return await dispatch(args, root)
            with patch('fruitfly_agent.providers.registry.ProviderRegistry.create', side_effect=AssertionError('Provider constructed')):
                await invoke()
                repeated = await invoke()
                self.assertTrue(repeated['observed_updated'])
            self.assertEqual(yaml.safe_load(path.read_text())['next'], authored['next'])
            self.assertIn('# Research controls', path.read_text())
            provider = RoleProvider()
            def script(view, signal=None):
                pages = [m for m in view.messages if isinstance(m, ToolResultMessage)]
                if not pages:
                    message = AssistantMessage([ToolCallBlock('evidence', 'read', {'path': 'context/executions.json'})], stop_reason='toolUse')
                elif len(pages) == 1:
                    message = AssistantMessage([ToolCallBlock('baseline', 'read', {'path': 'harness/base_prompt/parameters.yaml'})], stop_reason='toolUse')
                elif len(pages) == 2:
                    document = yaml.safe_load(json.loads(pages[1].text)['text'])
                    document['parameters']['instructions']['system'] += '\nVerify the actual deliverable.'
                    message = AssistantMessage([ToolCallBlock('edit', 'write_file', {'path': 'harness/base_prompt/parameters.yaml',
                        'content': yaml.safe_dump(document)})], stop_reason='toolUse')
                else:
                    run = json.loads(json.loads(pages[0].text)['text'])[0]['run_id']
                    message = AssistantMessage([TextBlock(json.dumps({'reasons': [{'component_id': 'base_prompt',
                        'explanation': 'Inspect retained results', 'expected_effect': 'Verify outputs', 'evidence_ids': [run]}]}))], stop_reason='stop')
                return AssistantMessageEventStream(provider._message_stream(message))
            def role_config(roles, role):
                self.assertEqual(role, 'editor')
                return AgentLoopConfig(provider, context_window=64000)
            for generation in (1, 2):
                authored['next'] = {'stage': 'propose', 'publish_as': 'candidate-' + str(generation),
                    'inputs': {'batches': [{'artifact': 'baseline'}]}}
                if generation == 2:
                    authored['next']['inputs']['harness'] = {'candidate': 'candidate-1'}
                    authored['overrides'] = {'H': {'base_prompt': {'inline': {
                        'parameters': {'instructions': {'system': text + '\nHuman proposal adjustment.'}}}}}}
                path.write_text('# Research controls\n' + yaml.safe_dump(authored, sort_keys=False))
                provider.script = [script] * 12
                with patch('fruitfly_agent.run.improvement.roles.ResearchRoles.configuration', role_config):
                    result = await invoke()
                configs = list(Path(result['bundle']).parent.glob('*/candidate/config.yaml'))
                self.assertEqual(len(configs), 1)
                candidate = yaml.safe_load(configs[0].read_text())
                text = candidate['profiles'][candidate['default_profile']]['H']['base_prompt']['inline']['parameters']['instructions']['system']
                self.assertEqual(text.count('Verify the actual deliverable.'), generation)
                if generation == 2:
                    self.assertTrue((configs[0].parent.parent / 'origin/config.yaml').exists())
                    human = json.loads((configs[0].parent.parent / 'human-changes.json').read_text())
                    total = json.loads((configs[0].parent.parent / 'total-changes.json').read_text())
                    self.assertTrue(human)
                    self.assertTrue(total)
                    self.assertIn('Human proposal adjustment.', json.dumps(human))
                self.assertEqual(yaml.safe_load(path.read_text())['next'], authored['next'])
                if generation == 1:
                    # Reusing the completed activity must not require a model
                    # client or credentials merely to read retained outputs.
                    with patch('fruitfly_agent.providers.registry.ProviderRegistry.create',
                            side_effect=AssertionError('cached proposal constructed a Provider')):
                        reused = await invoke()
                    self.assertTrue(reused['observed_updated'])
            # A fresh invocation executes the selected complete candidate plus
            # explicit human overrides; no editor or assessor request is made.
            authored['overrides'] = {'H': {'base_prompt': {'inline': {
                'parameters': {'instructions': {'system': text + '\nHuman execution adjustment.'}}}}}}
            authored['stages']['execute'] = {'tasks': {'inline': {
                'source': 'files', 'instruction': 'Inspect deliverables'}}}
            authored['next'] = {'stage': 'execute', 'publish_as': 'candidate-2-results',
                'inputs': {'harness': {'candidate': 'candidate-2'}}}
            path.write_text(yaml.safe_dump(authored, sort_keys=False))
            from tests.support.task_execution import TaskApplicationFixture
            from unittest.mock import Mock
            registry = Mock(); registry.create.return_value = provider
            captured = []
            def factory(prepared, runtime):
                captured.append(prepared.profile)
                return TaskApplicationFixture(cwd=root, config_path=str(runtime),
                    environment=prepared.environment, provider_registry=registry)
            provider.script.clear(); provider.respond_text('Executed supplied configuration')
            with patch('fruitfly_agent.experiments.composition.application_factory', factory):
                executed = await invoke()
            batch = json.loads((Path(executed['bundle']).parent / 'batch.json').read_text())
            self.assertEqual(batch['records'][0]['status'], 'completed')
            self.assertEqual(batch['records'][0]['output'], 'Executed supplied configuration')
            self.assertEqual(len(captured), 1)
            self.assertIn('Human execution adjustment.', str(captured[0].to_dict(references=False)))

    async def test_eval_registers_results_without_organizer_editor_or_assessor(self):
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve(); path = workspace(root)
            original = yaml.safe_load(path.read_text())
            trial = root / 'eval-output/artifacts/harbor/job/task'
            (trial / 'agent').mkdir(parents=True)
            (trial / 'result.json').write_text('{"task_name":"fixture"}')
            (trial / 'agent/session.jsonl').write_text(json.dumps({'message': {'role': 'user', 'content': 'Fixed Eval'}}) + '\n')
            report = root / 'eval-output/report.json'; report.write_text('{}')
            path.write_text(yaml.safe_dump({'research': {'id': 'study', 'output_root': '../study'},
                'baseline': original['baseline'],
                'stages': {'eval': {'tasks': {'inline': {'source': 'files', 'instruction': 'Fixed Eval'}}}},
                'next': {'stage': 'eval', 'publish_as': 'eval-baseline'}}))
            prepared = SimpleNamespace(summary=lambda: {'operation': 'eval'})
            args = parser().parse_args(['improvement', 'step', '--config', str(path)])
            with patch('fruitfly_agent.experiments.composition.prepare_experiment', return_value=prepared), \
                 patch('fruitfly_agent.experiments.operations.evaluate.run', return_value={'report': str(report)}) as evaluate, \
                 patch('fruitfly_agent.providers.registry.ProviderRegistry.create', side_effect=AssertionError('Provider constructed')):
                result = await dispatch(args, root)
            self.assertEqual(evaluate.call_count, 1)
            self.assertEqual(json.loads(Path(result['bundle']).read_text())['kind'], 'eval')
            self.assertEqual(len(list((root / 'study/runs').iterdir())), 1)
