"""Authorized delegation instruction candidates change real child execution."""
from pathlib import Path
import json
import tempfile
import unittest
from fruitfly_agent.lab.catalog import builtin_catalog, MechanismSelection, load_system_config
from fruitfly_agent.lab.catalog.adapters.parameters import ParameterTarget
from fruitfly_agent.lab.catalog.configuration import materialize_system
from fruitfly_agent.runtime_spec import HarnessProfile
from fruitfly_agent.runtime_spec.execution import apply_profile_binding
from fruitfly_agent.core.session import Session
from fruitfly_agent.interactive.application.runtime import RuntimeHandle
from tests.support.assembly import AssemblyWorkspace
from tests.support.faux_provider import FauxProvider

class SubagentInstructionTests(unittest.IsolatedAsyncioTestCase):
    async def test_materialized_candidate_changes_child_prompt_and_only_its_tool_description(self):
        catalog = builtin_catalog()
        definition = catalog.get('subagent')
        fields = {'child_instructions', 'spawn_instructions'}
        target = ParameterTarget(definition, {}, fields)
        value = json.loads(target.snapshot().text)
        value['instructions']['child'] = 'CANDIDATE_CHILD: retain precise file references.'
        value['instructions']['spawn'] = 'CANDIDATE_SPAWN: delegate bounded investigations.'
        candidate_text = json.dumps(value)
        target.validate_change(candidate_text, {'editable_fields': ['parameters.instructions.child', 'parameters.instructions.spawn']})
        baseline = HarnessProfile('test', model_profile='offline', mechanisms=(MechanismSelection('local-env'), MechanismSelection('subagent')))
        candidate = apply_profile_binding(baseline, 'configuration', 'component.subagent', target.export_text(candidate_text))
        prompts, descriptions = [], []
        with tempfile.TemporaryDirectory() as directory:
            workspace = AssemblyWorkspace(directory)
            for number, profile in enumerate((baseline, candidate)):
                path = materialize_system(profile, Path(directory) / str(number) / 'config.yaml', catalog=catalog)
                loaded = load_system_config(path, catalog=catalog).select()
                from dataclasses import replace
                loaded = replace(loaded, model_catalog=str(workspace.model_path))
                with Session(Path(directory) / str(number) / 'parent.jsonl') as session:
                    runtime = workspace.assemble(loaded, session, catalog=catalog, config_path=path)
                    owner = RuntimeHandle(None, {}, components=runtime.components)
                    try:
                        service = runtime.components['subagent-monitor']
                        captured = []
                        def create(*args):
                            p = FauxProvider(); p.respond_text('done'); captured.append(p); return p
                        workspace.registry.create.side_effect = create
                        service.begin()
                        row = service.spawn('Inspect')
                        result = await service.wait([(row['agent_id'], row['run_id'])], timeout_seconds=2)
                        self.assertEqual('completed', result['executions'][0]['state'])
                        prompts.append(captured[0].calls[0]['system_prompt'])
                        descriptions.append({t.name: t.description for t in runtime.config.tools})
                        await service.end()
                    finally:
                        await owner.close()
            self.assertNotIn('CANDIDATE_CHILD', prompts[0])
            self.assertIn('CANDIDATE_CHILD', prompts[1])
            self.assertNotEqual(descriptions[0]['subagent_spawn'], descriptions[1]['subagent_spawn'])
            self.assertEqual(descriptions[0]['subagent_wait'], descriptions[1]['subagent_wait'])

    def test_grants_reject_model_permissions_and_outer_limits(self):
        definition = builtin_catalog().get('subagent')
        for field in ('parameters.settings.model_profile', 'parameters.settings.max_concurrent',
                      'parameters.settings.run_timeout_seconds', 'parameters.settings.permissions'):
            with self.subTest(field=field), self.assertRaises(ValueError):
                definition.configuration_edit([field], {})
