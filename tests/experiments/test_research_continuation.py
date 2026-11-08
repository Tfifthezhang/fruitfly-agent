"""Public independent actions keep portable results and changed configuration."""
import asyncio
from contextlib import redirect_stdout
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import yaml
from fruitfly_agent.experiments.cli import parser
from fruitfly_agent.experiments.operations.research import dispatch
from fruitfly_agent.core.config import AgentLoopConfig
from fruitfly_agent.core.data_model import AssistantMessage, ToolCallBlock, TextBlock
from fruitfly_agent.core.model_stream import AssistantMessageEventStream
from tests.support.experiments import workspace
from tests.support.model_evaluation import RoleProvider


class ResearchContinuationTests(unittest.IsolatedAsyncioTestCase):
    async def test_public_actions_use_bundles_and_allow_configuration_change(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve(); config = workspace(root)
            raw = yaml.safe_load(config.read_text()); raw.pop('tasks'); config.write_text(yaml.safe_dump(raw))
            archive = root / 'archive/artifacts/harbor/job/task'
            agent = archive / 'agent'; agent.mkdir(parents=True)
            (agent / 'session.jsonl').write_text(json.dumps({'type':'message','message':{'role':'user','content':'Retained instruction'}})+'\n')
            (archive / 'result.json').write_text('{"task_name":"fixture"}')
            output = root / 'portable'
            provider = RoleProvider()
            async def invoke(action, inputs=()):
                args = parser().parse_args(['--cwd', str(root), 'improvement', action, '--study', 'study',
                    '--output-root', str(output), '--config', str(config), *inputs])
                return await dispatch(args, root)
            args = parser().parse_args(['improvement','import','--study','study','--output-root',str(output),
                '--source','eval',str(root/'archive')])
            imported = await dispatch(args, root)
            def role_config(self, role): return AgentLoopConfig(provider, context_window=64000)
            with patch('fruitfly_agent.run.improvement.roles.ResearchRoles.configuration', role_config):
                organized = await invoke('organize', (imported['bundle'],))
                def propose(view, signal=None):
                    # The regular editor must supply original executions before attribution.
                    from fruitfly_agent.core.data_model import ToolResultMessage
                    pages = [m for m in view.messages if isinstance(m, ToolResultMessage)]
                    if not pages:
                        message = AssistantMessage([ToolCallBlock('read-evidence','read',{'path':'context/executions.json'})],stop_reason='toolUse')
                    elif len(pages) == 1:
                        document = {'id': 'base_prompt', 'role': 'H', 'implementation': 'base_prompt',
                            'parameters': {'instructions': {'system': 'Inspect evidence and verify the deliverable.'}}}
                        message = AssistantMessage([ToolCallBlock('write-candidate','write_file',
                            {'path':'harness/base_prompt/parameters.yaml','content':yaml.safe_dump(document)})],stop_reason='toolUse')
                    else:
                        data = json.loads(pages[0].text)
                        run = json.loads(data['text'])[0]['run_id']
                        message = AssistantMessage([TextBlock(json.dumps({'reasons':[{'component_id':'base_prompt',
                            'explanation':'Observed retained execution', 'expected_effect':'Verify actual deliverables',
                            'evidence_ids':[run]}]}))],stop_reason='stop')
                    return AssistantMessageEventStream(provider._message_stream(message))
                provider.script = [propose] * 12
                proposed = await invoke('propose', (imported['bundle'],organized['bundle']))
            proposal = json.loads((Path(proposed['bundle']).parent/'proposal.json').read_text())
            self.assertEqual(len(proposal['candidates']), 1)
            candidates = Path(proposed['bundle']).parent
            self.assertTrue(list(candidates.glob('*/candidate/config.yaml')))
            self.assertGreater(len(proposal['candidates'][0]['base']['components']), 1)
            self.assertTrue(Path(proposed['report']).exists())
            report = json.loads(Path(proposed['report']).read_text())
            self.assertTrue(report['configuration_differences'])
            # Exercise the registered Application executor with the saved complete
            # candidate config in a separate invocation of the public operation.
            raw['tasks'] = {'inline': {'source': 'files', 'instruction': 'Execute the supplied task'}}
            config.write_text(yaml.safe_dump(raw))
            from tests.support.task_execution import TaskApplicationFixture
            from unittest.mock import Mock
            registry = Mock(); registry.create.return_value = provider
            def factory(prepared, runtime):
                return TaskApplicationFixture(cwd=root, config_path=str(runtime), environment=prepared.environment,
                    provider_registry=registry)
            provider.script.clear()
            provider.respond_text('Delivered test result')
            with patch('fruitfly_agent.experiments.composition.application_factory', factory):
                executed = await invoke('execute', (proposed['bundle'],))
            self.assertTrue(Path(executed['bundle']).exists())
            executed_batch = json.loads((Path(executed['bundle']).parent / 'batch.json').read_text())
            self.assertEqual(executed_batch['records'][0]['status'], 'completed')
            # Current configuration drift creates a retained derived proposal.
            system_path = root / '.fruitfly/default-config.yaml'
            system = yaml.safe_load(system_path.read_text())
            selected = system['profiles'][system['default_profile']]
            selected['H']['base_prompt'] = {'inline': {'id':'base_prompt','role':'H','implementation':'base_prompt',
                'parameters': {'instructions': {'system':'Current configuration changed after proposal'}}}}
            system_path.write_text(yaml.safe_dump(system))
            provider.script.clear(); provider.respond_text('Derived candidate execution')
            with patch('fruitfly_agent.experiments.composition.application_factory', factory):
                derived = await invoke('execute', (proposed['bundle'], '--apply-to-current'))
            self.assertTrue(any(r['path']=='derived-proposal.json' for r in derived['outputs']))


            # Move the complete study; no repository artifact cache is needed.
            moved = root/'moved'; output.rename(moved)
            from fruitfly_agent.run.storage.research_bundles import ResearchOutputs
            store = ResearchOutputs(root,'study',moved)
            imported_path = moved/Path(imported['bundle']).relative_to(output)
            resources, _ = store.inputs((str(imported_path),),'organize')
            self.assertTrue(resources)

    async def test_configuration_report_retained_when_provider_cannot_start(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve(); config = workspace(root)
            archive = root/'archive/artifacts/harbor/job/task'
            archive.mkdir(parents=True); (archive/'result.json').write_text('{}')
            out = root/'out'
            args = parser().parse_args(['improvement','import','--study','study','--output-root',str(out),
                '--source','eval',str(root/'archive')])
            imported = await dispatch(args,root)
            args = parser().parse_args(['improvement','organize','--study','study','--output-root',str(out),
                '--config',str(config),imported['bundle']])
            def fail_after_capture(*args):
                captured = list((out/'runs').glob('organize-*/configuration/effective.json'))
                self.assertEqual(len(captured), 1, 'configuration must be durable before Provider construction')
                raise ValueError('offline missing provider')
            with patch('fruitfly_agent.run.improvement.roles.ResearchRoles.configuration',side_effect=fail_after_capture):
                with self.assertRaisesRegex(ValueError,'offline missing provider'):
                    await dispatch(args,root)
            reports=[json.loads(p.read_text()) for p in (out/'runs').glob('*/report.json')]
            failed=next(r for r in reports if r['status']=='failed')
            run=out/'runs'/failed['id']
            self.assertTrue((run/'configuration/effective.json').exists())
            self.assertTrue((run/'configuration/differences.json').exists())
