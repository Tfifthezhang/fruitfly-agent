"""A single editable document drives separate imports and detached proposals."""
import json
from contextlib import asynccontextmanager
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


@asynccontextmanager
async def _fixture_runtime(self, *, config, **kwargs):
    from fruitfly_agent.lab.catalog import PreparedAgentRuntime

    yield PreparedAgentRuntime(config, None, {}, None, None)


class StageCliTests(unittest.IsolatedAsyncioTestCase):
    async def test_measured_compare_uses_catalog_method_without_constructing_provider(self):
        from fruitfly_agent.improvement.contracts.execution import ExecutionRecord
        from fruitfly_agent.improvement.contracts.research import ResearchBatch
        from fruitfly_agent.improvement.contracts.tasks import TaskMaterial
        from fruitfly_agent.improvement.contracts.versions import content_hash
        from tests.support.configuration import profile_document

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            path = workspace(root)
            baseline = yaml.safe_load(path.read_text())['baseline']
            profile = profile_document(executor='executor', mechanisms=[{
                'id': 'improvement-comparison', 'parameters': {'settings': {'method': 'measured'}},
            }])
            path.with_name(baseline['config']).write_text(yaml.safe_dump({
                'default_profile': 'baseline', 'profiles': {'baseline': profile},
            }))
            task = TaskMaterial('test-task', 'Inspect output')
            scorer, policy, state = (content_hash(value) for value in ('scorer', 'policy', 'state'))
            for index, side in enumerate(('before', 'after')):
                record = ExecutionRecord(side, task.task_id, task.material_id, content_hash(side),
                                         state, state, 'completed')
                observation = {'run_id': side, 'attempt': 0, 'name': 'reward', 'value': index,
                               'eligible': True, 'scorer_id': scorer, 'outcome_policy_id': policy,
                               'semantics': {'scope': 'execution', 'outcome': 'met' if index else 'unmet'}}
                batch = ResearchBatch((task,), (record,), (observation,))
                (root / (side + '.json')).write_text(json.dumps(batch.to_dict()))
            manifest = {'metric': 'reward', 'scorer_id': scorer, 'outcome_policy_id': policy,
                        'direction': 'max', 'minimum_gain': 0, 'maximum_regression_rate': 0,
                        'pairs': [{'task_id': task.task_id, 'attempt': 0, 'before': 'before', 'after': 'after'}]}
            (root / 'policy.json').write_text(json.dumps(manifest))
            authored = {'research': {'id': 'comparison-study', 'output_root': '../study'},
                        'baseline': baseline, 'next': {'stage': 'import'}, 'stages': {}}
            args = parser().parse_args(['improvement', 'step', '--config', str(path)])
            with patch('fruitfly_agent.providers.registry.ProviderRegistry.create',
                       side_effect=AssertionError('Provider constructed')):
                for side in ('before', 'after'):
                    authored['stages']['import'] = {'source': 'batch', 'path': '../' + side + '.json', 'publish_as': side}
                    path.write_text(yaml.safe_dump(authored))
                    await dispatch(args, root)
                authored['next']['stage'] = 'compare'
                authored['stages']['compare'] = {'measured_policy': '../policy.json',
                    'inputs': {'batches': [{'artifact': 'before'}, {'artifact': 'after'}]}}
                path.write_text(yaml.safe_dump(authored))
                result = await dispatch(args, root)
            report = json.loads((Path(result['bundle']).parent / 'comparison.json').read_text())
            self.assertEqual(report['conclusion'], 'better')
            self.assertEqual(report['usage']['comparison_model_calls'], 0)

    async def test_gepa_method_uses_organized_group_and_shared_candidate_export(self):
        from fruitfly_agent.improvement.contracts.execution import ExecutionRecord
        from fruitfly_agent.improvement.contracts.research import ResearchBatch
        from fruitfly_agent.improvement.contracts.tasks import TaskMaterial
        from fruitfly_agent.improvement.contracts.versions import content_hash
        from fruitfly_agent.lab.improvement.editor.methods.gepa_reflection import compat
        from tests.support.reflection import FixtureSignature
        from tests.support.configuration import profile_document
        from tests.support.faux_provider import FauxProvider

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            path = workspace(root)
            baseline = yaml.safe_load(path.read_text())['baseline']
            runtime = path.with_name(baseline['config'])
            profile = profile_document(executor='executor', mechanisms=[{
                'id': 'improvement-editor', 'parameters': {'settings': {'method': 'gepa-reflection'}},
            }])
            runtime.write_text(yaml.safe_dump({'default_profile': 'baseline', 'profiles': {'baseline': profile}}))
            task = TaskMaterial('task', 'Produce a deliverable')
            identity = content_hash('conditions')
            record = ExecutionRecord('run-fixture', task.task_id, task.material_id, identity, identity,
                                     identity, 'completed', output='A deliverable was reported.')
            (root / 'import.json').write_text(json.dumps(ResearchBatch((task,), (record,)).to_dict()))
            spec = {'research': {'id': 'gepa-study', 'output_root': '../study'}, 'baseline': baseline,
                    'next': {'stage': 'import'}, 'stages': {
                        'import': {'source': 'batch', 'path': '../import.json', 'publish_as': 'pool'},
                        'group': {'members': [['task']], 'inputs': {'batches': [{'artifact': 'pool'}]},
                                  'publish_as': 'grouped'},
                        'organize': {'inputs': {'batches': [{'artifact': 'grouped'}]}, 'publish_as': 'organized'},
                        'propose': {'inputs': {'batches': [{'artifact': 'grouped'}],
                                              'evidence': [{'artifact': 'organized'}]},
                                    'optimization': {'scope': 'explicit', 'include': {'base_prompt': {
                                        'fields': ['parameters.instructions.system']}}},
                                    'direction': 'Require verification of the actual deliverable'},
                    }}
            organizer = FauxProvider()
            organizer.respond_text(json.dumps({'schema_version': 2, 'sections': [], 'findings': []}))
            editor = FauxProvider()
            editor.respond_text('Verify that the requested deliverable exists and is usable.')
            editor.respond_text(json.dumps({'reasons': [{'component_id': 'base_prompt',
                'explanation': 'The output reports completion without an observable check.',
                'expected_effect': 'Require a check on the actual deliverable.',
                'evidence_ids': [record.run_id]}], 'decision': {'kind': 'candidate',
                'explanation': 'A shared verification instruction', 'baseline_applicability': 'Exact edit parent supplied'}}))

            def role_config(roles, role, *, tools=True):
                if role == 'organizer':
                    self.assertTrue(tools)
                    return AgentLoopConfig(organizer)
                self.assertEqual(role, 'editor')
                self.assertFalse(tools)
                return AgentLoopConfig(editor)

            args = parser().parse_args(['improvement', 'step', '--config', str(path)])
            with patch('fruitfly_agent.run.improvement.roles.ResearchRoles.configuration', role_config), \
                 patch('fruitfly_agent.run.improvement.research_runtime.ResearchRuntimeFactory.__call__',
                       new=_fixture_runtime), patch.object(compat, 'signature', return_value=FixtureSignature):
                for stage in ('import', 'group', 'organize', 'propose'):
                    spec['next']['stage'] = stage
                    path.write_text(yaml.safe_dump(spec))
                    result = await dispatch(args, root)
            candidate_file = Path(result['bundle']).parent / 'proposal.json'
            proposal = json.loads(candidate_file.read_text())
            self.assertEqual(len(proposal['candidates']), 1)
            self.assertEqual(len(editor.calls), 2)
            self.assertEqual(len(list(candidate_file.parent.glob('*/candidate/config.yaml'))), 1)
            usage = json.loads(Path(result['report']).read_text())['usage']
            self.assertEqual(usage['observed_model_requests'], 2)
            self.assertEqual(usage['observed_by_role'], {'editor': 2})
            self.assertIsNone(usage['billed_cost'])
            from fruitfly_agent.core.session import Session
            from fruitfly_agent.run.storage.artifacts import DataArtifactStore
            report = Path(result['report'])
            transcript, = (report.parent / 'roles' / 'editor').glob('*.jsonl')
            store = DataArtifactStore(root / 'study/artifacts')
            trace = json.loads(store.read_bytes(json.loads(report.read_text())['diagnostics']['artifact_id']))
            events = [json.loads(store.read_bytes(item['artifact_id'])) for item in trace['events']]
            event, = (item for item in events if item['event'] == 'research-session')
            self.assertEqual(store.read_bytes(event['artifact_id']), transcript.read_bytes())
            messages = [entry.payload['message']['role'] for entry in Session.inspect(transcript).read_all()
                        if entry.type == 'message']
            self.assertEqual(messages, ['user', 'assistant', 'user', 'assistant'])

    async def test_group_publishes_one_narrow_batch_without_constructing_provider(self):
        from fruitfly_agent.improvement.contracts.research import ResearchBatch
        from fruitfly_agent.improvement.contracts.tasks import TaskMaterial

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            path = workspace(root)
            baseline = yaml.safe_load(path.read_text())['baseline']
            batch = ResearchBatch((TaskMaterial('first', 'First instruction'),
                                   TaskMaterial('second', 'Second instruction')), ())
            (root / 'pool.json').write_text(json.dumps(batch.to_dict()))
            authored = {'research': {'id': 'group-study', 'output_root': '../study'},
                        'baseline': baseline, 'next': {'stage': 'import'},
                        'stages': {'import': {'source': 'batch', 'path': '../pool.json', 'publish_as': 'pool'},
                                   'group': {'position': 0, 'members': [['second']],
                                             'inputs': {'batches': [{'artifact': 'pool'}]}}}}
            args = parser().parse_args(['improvement', 'step', '--config', str(path)])
            with patch('fruitfly_agent.providers.registry.ProviderRegistry.create',
                       side_effect=AssertionError('Provider constructed')):
                path.write_text(yaml.safe_dump(authored))
                await dispatch(args, root)
                authored['next']['stage'] = 'group'
                path.write_text(yaml.safe_dump(authored))
                result = await dispatch(args, root)
            published = Path(result['bundle']).parent
            narrow = ResearchBatch.from_dict(json.loads((published / 'batch.json').read_text()))
            self.assertEqual([task.task_id for task in narrow.tasks], ['second'])
            decision = json.loads((published / 'grouping.json').read_text())
            self.assertEqual(decision['settings']['method'], 'fixed')
            from fruitfly_agent.run.storage.research_bundles import ResearchOutputs
            downstream = ResearchOutputs(root, 'group-study', root / 'study')
            resources, _ = downstream.inputs((result['bundle'],), 'organize')
            self.assertEqual([resource.path for resource in resources], ['batch.json'])

    async def test_document_import_and_two_proposals_inherit_selected_candidate(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve(); path = workspace(root)
            old = yaml.safe_load(path.read_text())
            trial = root / 'archive/artifacts/harbor/job/task'
            (trial / 'agent').mkdir(parents=True)
            (trial / 'result.json').write_text('{"task_name":"fixture"}')
            (trial / 'agent/session.jsonl').write_text(json.dumps({'message': {'role': 'user', 'content': 'Inspect deliverables'}}) + '\n')
            authored = {'research': {'id': 'study', 'output_root': '../study'},
                'baseline': old['baseline'],
                'stages': {'import': {'source': 'eval', 'path': '../archive', 'publish_as': 'baseline'},
                    'propose': {'direction': 'Verify actual results',
                        'optimization': {'scope': 'explicit', 'include': old['edit']}}},
                'next': {'stage': 'import'}}
            path.write_text('# Research controls\n' + yaml.safe_dump(authored, sort_keys=False))
            async def invoke(command='step'):
                args = parser().parse_args(['improvement', command, '--config', str(path)])
                return await dispatch(args, root)
            with patch('fruitfly_agent.providers.registry.ProviderRegistry.create', side_effect=AssertionError('Provider constructed')):
                await invoke()
                repeated = await invoke()
                self.assertTrue(repeated['observed_updated'])
            self.assertEqual(yaml.safe_load(path.read_text()), authored)
            self.assertNotIn('observed:', path.read_text())
            self.assertTrue(Path(repeated['observations']).is_file())
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
                authored['next'] = {'stage': 'propose'}
                authored['stages']['propose'].update(publish_as='candidate-' + str(generation),
                    inputs={'batches': [{'artifact': 'baseline'}]})
                if generation == 2:
                    authored['stages']['propose']['inputs']['harness'] = {'candidate': 'candidate-1'}
                path.write_text('# Research controls\n' + yaml.safe_dump(authored, sort_keys=False))
                provider.script = [script] * 12
                with patch('fruitfly_agent.run.improvement.roles.ResearchRoles.configuration', role_config):
                    result = await invoke()
                configs = list(Path(result['bundle']).parent.glob('*/candidate/config.yaml'))
                self.assertEqual(len(configs), 1)
                candidate = yaml.safe_load(configs[0].read_text())
                text = candidate['profiles'][candidate['default_profile']]['H']['base_prompt']['inline']['parameters']['instructions']['system']
                self.assertEqual(text.count('Verify the actual deliverable.'), generation)
                self.assertEqual(yaml.safe_load(path.read_text())['next'], authored['next'])
                if generation == 1:
                    # Reusing the completed activity must not require a model
                    # client or credentials merely to read retained outputs.
                    with patch('fruitfly_agent.providers.registry.ProviderRegistry.create',
                            side_effect=AssertionError('cached proposal constructed a Provider')):
                        reused = await invoke()
                    self.assertTrue(reused['observed_updated'])
            # Explicit source configuration customization remains separate from
            # research controls; execute resolves that complete system file.
            import shutil
            customized = root / 'customized'
            shutil.copytree(configs[0].parent, customized)
            changed_system = yaml.safe_load((customized / 'config.yaml').read_text())
            selected_profile = changed_system['profiles'][changed_system['default_profile']]
            selected_profile['H']['base_prompt']['inline']['parameters']['instructions']['system'] += '\nHuman execution adjustment.'
            (customized / 'config.yaml').write_text(yaml.safe_dump(changed_system))
            authored['stages']['execute'] = {'tasks': {'inline': {
                'source': 'files', 'instruction': 'Inspect deliverables'}},
                'publish_as': 'candidate-2-results',
                'inputs': {'harness': {'config': str(customized / 'config.yaml')}}}
            authored['next'] = {'stage': 'execute'}
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
                'stages': {'eval': {'tasks': {'inline': {'source': 'files', 'instruction': 'Fixed Eval'}}, 'publish_as': 'eval-baseline'}},
                'next': {'stage': 'eval'}}))
            prepared = SimpleNamespace(summary=lambda: {'operation': 'eval'})
            args = parser().parse_args(['improvement', 'step', '--config', str(path)])
            with patch('fruitfly_agent.experiments.composition.prepare_experiment', return_value=prepared), \
                 patch('fruitfly_agent.experiments.operations.evaluate.run', return_value={'report': str(report)}) as evaluate, \
                 patch('fruitfly_agent.providers.registry.ProviderRegistry.create', side_effect=AssertionError('Provider constructed')):
                result = await dispatch(args, root)
            self.assertEqual(evaluate.call_count, 1)
            self.assertEqual(json.loads(Path(result['bundle']).read_text())['kind'], 'eval')
            self.assertEqual(len(list((root / 'study/runs').iterdir())), 1)

    async def test_import_check_reports_missing_input_without_running_a_stage(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / 'improvement.yaml'
            path.write_text(yaml.safe_dump({'research': {'id': 'check-input', 'output_root': '.'},
                'stages': {'import': {'source': 'batch', 'path': 'missing.json'}},
                'next': {'stage': 'import'}}))
            args = parser().parse_args(['improvement', 'check', '--config', str(path)])
            with patch('fruitfly_agent.providers.registry.ProviderRegistry.create', side_effect=AssertionError('Provider')):
                result = await dispatch(args, root)
            self.assertFalse(result['available'])
            self.assertIn('missing', result['unavailable_reason'])
            self.assertEqual(list(root.iterdir()), [path])

    async def test_cli_defaults_to_improvement_entry_and_honors_explicit_config(self):
        import io
        from contextlib import redirect_stdout
        from fruitfly_agent.experiments.cli import dispatch as dispatch_cli
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / '.fruitfly').mkdir()
            entry = root / '.fruitfly/improvement.yaml'
            raw = {'research': {'id': 'default-entry', 'output_root': '.'},
                'stages': {'import': {'source': 'batch', 'path': 'missing.json'}},
                'next': {'stage': 'import'}}
            entry.write_text(yaml.safe_dump(raw))
            explicit = root / 'other.yaml'
            raw['research']['id'] = 'explicit-entry'
            explicit.write_text(yaml.safe_dump(raw))
            for extra, expected in (([], 'default-entry'), (['--config', str(explicit)], 'explicit-entry')):
                args = parser().parse_args(['improvement', 'show', '--cwd', str(root), *extra])
                output = io.StringIO()
                # Synchronous CLI owns its event loop; run outside this async test loop.
                import asyncio
                with redirect_stdout(output):
                    code = await asyncio.to_thread(dispatch_cli, args)
                self.assertEqual(code, 0)
                self.assertEqual(json.loads(output.getvalue())['research']['id'], expected)

    async def test_organize_stage_uses_delegated_sources_and_publishes_attributable_guide(self):
        from tests.support.faux_provider import FauxProvider
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            path = workspace(root)
            baseline = yaml.safe_load(path.read_text())['baseline']
            system = path.parent / baseline['config']
            raw_system = yaml.safe_load(system.read_text())
            raw_system['profiles'][raw_system['default_profile']]['H']['subagent'] = {'default': True}
            system.write_text(yaml.safe_dump(raw_system))
            trial = root / 'archive/artifacts/harbor/job/task'
            (trial / 'agent').mkdir(parents=True)
            (trial / 'result.json').write_text('{"task_name":"fixture"}')
            (trial / 'agent/session.jsonl').write_text(json.dumps({'message': {'role': 'user', 'content': 'Inspect task'}}) + '\n')
            authored = {'research': {'id': 'delegated', 'output_root': '../study'}, 'baseline': baseline,
                'stages': {'import': {'source': 'eval', 'path': '../archive', 'publish_as': 'batch'},
                    'organize': {'inputs': {'batches': [{'artifact': 'batch'}]},
                        'delegation': {'enabled': True, 'workers': ['evidence-reader']},
                        'incremental': {'enabled': True, 'reuse': True}, 'publish_as': 'guide'}},
                'next': {'stage': 'import'}}
            path.write_text(yaml.safe_dump(authored))
            args = parser().parse_args(['improvement', 'step', '--config', str(path)])
            await dispatch(args, root)
            parent, child = FauxProvider(), FauxProvider()
            def stream(message):
                return AssistantMessageEventStream(FauxProvider._message_stream(message))
            parent.respond_tool_call('subagent_spawn', {'task': 'Read the batch navigation and summarize its scope.',
                'worker': 'evidence-reader', 'materials': ['context/batch.json']})
            parent.respond_text('Waiting for the reader')
            def integrate(view, signal=None):
                notice = next(m for m in reversed(view.messages) if getattr(m, 'kind', '') == 'subagent-result')
                row = json.loads(notice.text.split('\n', 1)[1])
                path = json.loads(row['summary'])['findings_path']
                return stream(AssistantMessage([ToolCallBlock('read-findings', 'read', {'path': path})], 'toolUse'))
            def publish(view, signal=None):
                findings = json.loads(json.loads(view.messages[-1].text)['text'])['findings']
                guide = {'schema_version': 2, 'findings': [], 'sections': [{'title': 'Batch scope', 'summary': findings['summary'], 'sources': findings['sources']}]}
                return stream(AssistantMessage([TextBlock(json.dumps(guide))], 'stop'))
            parent.script.append(integrate)
            parent.script.append(publish)
            child.respond_tool_call('read', {'path': 'context/batch.json'})
            def submit(view, signal=None):
                page = json.loads(view.messages[-1].text)
                return stream(AssistantMessage([ToolCallBlock('submit-findings', 'submit_findings', {
                    'summary': 'One granted batch; inspect individual executions for details.',
                    'sources': [{'path': 'context/batch.json', 'citation_id': page['citation_id']}],
                    'unknowns': ['Full trajectories were not read.']})], 'toolUse'))
            child.script.append(submit)
            def configuration(roles, role, *, resources=None):
                provider = parent if role == 'organizer' else child
                if resources is not None:
                    resources.append(provider)
                return AgentLoopConfig(provider, model='offline', context_window=64000)
            authored['next']['stage'] = 'organize'
            path.write_text(yaml.safe_dump(authored))
            before = path.read_bytes()
            with patch('fruitfly_agent.run.improvement.roles.ResearchRoles.configuration', configuration):
                result = await dispatch(args, root)
            guide = json.loads((Path(result['bundle']).parent / 'organization/guide.json').read_text())
            self.assertEqual('Batch scope', guide['sections'][0]['title'])
            self.assertEqual('context/batch.json', guide['sections'][0]['sources'][0]['path'])
            parts = json.loads((Path(result['bundle']).parent / 'organization/parts.json').read_text())
            self.assertEqual(1, len(parts['parts']))
            self.assertTrue(list((root / 'study/organization-parts/main').glob('*.json')))
            self.assertNotIn('write_file', child.calls[0]['tools'])
            self.assertTrue(list((root / 'study/runs').glob('*/roles/organizer/*.subagents/*/session.jsonl')))
            self.assertEqual(before, path.read_bytes())
