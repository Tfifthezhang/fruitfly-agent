"""Default scope is shared across continuous execution and retained-evidence proposals."""
from dataclasses import replace
from pathlib import Path
import json
import tempfile
import unittest
from unittest.mock import patch
import yaml

from fruitfly_agent.experiments.configuration import load_configuration
from fruitfly_agent.experiments.composition import prepare_experiment
from fruitfly_agent.experiments.cli import parser
from fruitfly_agent.experiments.operations.research import defaults
from fruitfly_agent.lab.catalog import builtin_catalog, load_system_config, optimization_grants
from fruitfly_agent.lab.improvement.execution import builtin_executions, ExecutionRegistry
from tests.support.experiments import workspace
from tests.support.task_execution import TaskRunnerFixture

PROFILE = Path(__file__).resolve().parents[2] / 'examples/configuration/default-config.example.yaml'
EXCLUDED = {'file-memory','improvement-editor','improvement-evaluator','improvement-organizer'}
EXPECTED = {'base_prompt','layered-compaction','skills','memory-library','skill-library',
    'read-tool','write-tool','edit-tool','bash-tool','subagent'}


class OptimizationDefaultsTests(unittest.IsolatedAsyncioTestCase):
    def prepare_files(self, root):
        config = workspace(root)
        profile = yaml.safe_load(PROFILE.read_text())
        profile['profiles']['baseline']['models']['roles']['executor'] = 'executor'
        (root/'.fruitfly/default-config.yaml').write_text(yaml.safe_dump(profile))
        document = yaml.safe_load(config.read_text());document.pop('edit')
        config.write_text(yaml.safe_dump(document))
        return config

    def test_same_owner_defaults_and_mode_protection_in_both_entries(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);config=self.prepare_files(root)
            definition=builtin_executions().get('agent-task')
            executions=ExecutionRegistry((replace(definition,capabilities=TaskRunnerFixture.capabilities),))
            with patch('fruitfly_agent.experiments.composition.builtin_executions',return_value=executions), \
                 patch('fruitfly_agent.experiments.validation.builtin_executions',return_value=executions), \
                 patch('fruitfly_agent.providers.registry.ProviderRegistry.create',side_effect=AssertionError('Provider created')):
                prepared=prepare_experiment(load_configuration(root),'improvement')
                args=parser().parse_args(['improvement','defaults','--config',str(config)])
                preview=defaults(args,root)
            self.assertEqual(set(prepared.request.component_ids),EXPECTED - {'subagent'})
            self.assertEqual(set(preview['components']),EXPECTED)
            self.assertFalse(set(preview['components']) & EXCLUDED)
            rows={r['component_id']:r for r in preview['optimization_table']}
            self.assertTrue(all(not rows[name]['default_selected'] for name in EXCLUDED))
            self.assertIn('parameters.instructions.description',rows['bash-tool']['editable_fields'])
            fields=rows['layered-compaction']['editable_fields']
            self.assertNotIn('parameters.settings.mode',fields)
            self.assertNotIn('parameters.instructions.summary',fields)
            self.assertIn('parameters.instructions.readback',fields)
            from fruitfly_agent.experiments.records import RunRecords
            records=RunRecords(root);record=records.create('improvement',prepared.summary())
            table=records.directory(record['id'])/'configuration/optimization.json'
            self.assertEqual({r['component_id'] for r in json.loads(table.read_text()) if r['selected']},EXPECTED - {'subagent'})
            self.assertTrue(table.with_suffix('.md').exists())

    def test_explicit_scope_replaces_defaults_and_excluded_roles_can_opt_in(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);config=self.prepare_files(root)
            document=yaml.safe_load(config.read_text())
            document['edit']={'base_prompt':{'fields':['parameters.instructions.system']}}
            config.write_text(yaml.safe_dump(document))
            args=parser().parse_args(['improvement','defaults','--config',str(config)])
            preview=defaults(args,root)
            self.assertEqual(preview['selection'],'explicit')
            self.assertEqual(preview['components'],['base_prompt'])
            catalog=builtin_catalog();profile=load_system_config(root/'.fruitfly/default-config.yaml',catalog=catalog).select()
            grants=optimization_grants(profile,catalog,('file-memory','improvement-editor'))
            self.assertIn('parameters.instructions.extraction',grants['file-memory']['editable_fields'])
            self.assertIn('parameters.instructions.propose',grants['improvement-editor']['editable_fields'])

    async def test_retained_proposal_defaults_can_change_tool_and_save_scope_before_model(self):
        from fruitfly_agent.experiments.operations.research import dispatch
        from fruitfly_agent.core.config import AgentLoopConfig
        from fruitfly_agent.core.data_model import AssistantMessage, TextBlock, ToolCallBlock, ToolResultMessage
        from fruitfly_agent.core.model_stream import AssistantMessageEventStream
        from tests.support.faux_provider import FauxProvider
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory).resolve();config=self.prepare_files(root)
            raw=yaml.safe_load(config.read_text());raw.pop('tasks');config.write_text(yaml.safe_dump(raw))
            trial=root/'archive/artifacts/harbor/job/trial';agent=trial/'agent';agent.mkdir(parents=True)
            (trial/'result.json').write_text('{"task_name":"fixture"}')
            (agent/'session.jsonl').write_text(json.dumps({'message':{'role':'user','content':'Retained task'}})+'\n')
            out=root/'study'
            args=parser().parse_args(['improvement','import','--study','study','--output-root',str(out),
                '--source','eval',str(root/'archive')])
            imported=await dispatch(args,root)
            provider=FauxProvider()
            def configuration(roles,role):
                tables=list(out.glob('runs/propose-*/configuration/optimization.json'))
                self.assertEqual(len(tables),1)
                rows=json.loads(tables[0].read_text())
                self.assertEqual({r['component_id'] for r in rows if r['selected']},EXPECTED)
                return AgentLoopConfig(provider,context_window=64000)
            def reply(view,signal=None):
                pages=[m for m in view.messages if isinstance(m,ToolResultMessage)]
                if not pages:
                    message=AssistantMessage([ToolCallBlock('evidence','read',{'path':'context/executions.json'})],stop_reason='toolUse')
                elif len(pages)==1:
                    message=AssistantMessage([ToolCallBlock('tool','read',{'path':'harness/bash-tool/parameters.yaml'})],stop_reason='toolUse')
                elif len(pages)==2:
                    document=yaml.safe_load(json.loads(pages[1].text)['text'])
                    document['parameters']['instructions']['description']+=' Verify the command output before claiming completion.'
                    message=AssistantMessage([ToolCallBlock('write','write_file',{'path':'harness/bash-tool/parameters.yaml',
                        'content':yaml.safe_dump(document,sort_keys=False,allow_unicode=True)})],stop_reason='toolUse')
                else:
                    run=json.loads(json.loads(pages[0].text)['text'])[0]['run_id']
                    reasons=[{'component_id':'bash-tool','explanation':'Inspect retained command behavior',
                        'expected_effect':'Verify command output','evidence_ids':[run]}]
                    message=AssistantMessage([TextBlock(json.dumps({'reasons':reasons}))],stop_reason='stop')
                return AssistantMessageEventStream(provider._message_stream(message))
            provider.script=[reply]*6
            args=parser().parse_args(['improvement','propose','--study','study','--output-root',str(out),
                '--config',str(config),imported['bundle']])
            with patch('fruitfly_agent.run.improvement.roles.ResearchRoles.configuration',configuration):
                result=await dispatch(args,root)
            proposal=json.loads((Path(result['bundle']).parent/'proposal.json').read_text())
            candidate=proposal['candidates'][0]
            before={c['component_id']:c for c in candidate['base']['components']}
            after={c['component_id']:c for c in candidate['harness']['components']}
            self.assertEqual({name for name in before if before[name]!=after[name]}, {'bash-tool'})
            self.assertTrue(list(Path(result['bundle']).parent.glob('*/candidate/config.yaml')))
