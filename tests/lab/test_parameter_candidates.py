"""Owner parameter grants project into independently assembled candidate runtimes."""
from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock

from fruitfly_agent.core.config import AgentLoopConfig
from fruitfly_agent.core.errors import Result
from fruitfly_agent.core.env import ExecResult
from fruitfly_agent.core.tool_runtime import ToolCallContext
from fruitfly_agent.lab.catalog import builtin_catalog, assemble_lab, AssemblyContext, load_system_config
from fruitfly_agent.lab.catalog.configuration import materialize_system
from fruitfly_agent.lab.improvement.components.parameters import ParameterTarget
from fruitfly_agent.lab.improvement.editor.instructions import EditorInstructionTarget
from fruitfly_agent.lab.improvement.system_configuration import restore_editor, editor_edit_options
from fruitfly_agent.runtime_spec import HarnessProfile, MechanismSelection
from fruitfly_agent.runtime_spec.execution import apply_profile_binding


class ParameterCandidateTests(unittest.IsolatedAsyncioTestCase):
    def test_owned_parameter_descriptions_include_semantics_defaults_bounds_and_grants(self):
        from fruitfly_agent.lab.improvement.components import ComponentRegistry, TextComponentAdapter
        from fruitfly_agent.improvement.contracts.versions import canonical_json, content_hash
        definition = builtin_catalog().get('working-memory-reduction')
        target = ParameterTarget(definition, {}, {'memory_tokens', 'update_instructions'})
        registry = ComponentRegistry((TextComponentAdapter(target, 'mechanism-parameters'),))
        registry.configure({'working-memory-reduction': {'editable_fields': ['parameters.settings.memory_tokens'],
            'bounds': {'parameters.settings.memory_tokens': {'minimum': 512, 'maximum': 4096}}}})
        data = registry.descriptions(('working-memory-reduction',))
        fields = {f['path']: f for f in data['working-memory-reduction']['fields']}
        memory = fields['parameters.settings.memory_tokens']
        self.assertEqual((memory['kind'], memory['unit'], memory['current'], memory['default']), ('integer', 'tokens', 2048, 2048))
        self.assertEqual((memory['minimum'], memory['maximum']), (1, 32000))
        self.assertIn('capacity', memory['description'])
        self.assertEqual(['parameters.settings.memory_tokens'], data['working-memory-reduction']['grant']['editable_fields'])
        self.assertIn('parameters.instructions.update', fields)
        from fruitfly_agent.improvement.contracts.components import ComponentFile, HarnessSnapshot
        document = registry.snapshot().component('working-memory-reduction')
        values = json.loads(document.files[0].text); values['settings']['memory_tokens'] = 3072
        candidate = HarnessSnapshot((replace(document, files=(ComponentFile('instructions.txt', json.dumps(values)),)),))
        actual = registry.descriptions(('working-memory-reduction',), snapshot=candidate)
        updated = next(f for f in actual['working-memory-reduction']['fields'] if f['path'] == 'parameters.settings.memory_tokens')
        self.assertEqual((updated['current'], updated['default']), (3072, 2048))
        identity = content_hash(canonical_json(data))
        data['working-memory-reduction']['fields'][0]['description'] += ' changed'
        self.assertNotEqual(identity, content_hash(canonical_json(data)))
        self.assertEqual(target.values['memory_tokens'], 2048)

    async def test_information_candidate_changes_the_number_of_hits_sent_to_the_provider(self):
        from fruitfly_agent.core.loop import run_agent_loop
        from fruitfly_agent.core.data_model import UserMessage
        from fruitfly_agent.lab.context_manager.augmentation.information import InformationArtifact, InformationRef, create_static_lexical_space
        from tests.support.faux_provider import FauxProvider
        catalog = builtin_catalog()
        counts = []
        with tempfile.TemporaryDirectory() as directory:
            baseline = HarnessProfile('default', mechanisms=(MechanismSelection('information-context'),))
            target = ParameterTarget(catalog.get('information-context'), {}, {'top_k'})
            values = json.loads(target.snapshot().text); values['settings']['top_k'] = 1
            candidate = apply_profile_binding(baseline, 'configuration', 'component.information-context', target.export_text(json.dumps(values)))
            for index, profile in enumerate((baseline, candidate)):
                path = materialize_system(profile, Path(directory) / str(index) / 'config.yaml', catalog=catalog)
                provider = FauxProvider(); provider.respond_text('done')
                runtime = assemble_lab(AgentLoopConfig(provider=provider), catalog=catalog,
                    selections=load_system_config(path).select().mechanisms,
                    context=AssemblyContext(Path(directory), None, '', lambda *args: None))
                runtime.components['information'].register(create_static_lexical_space('probe', tuple(
                    InformationArtifact(InformationRef('probe', str(i)), 'Python evidence ' + str(i)) for i in range(3))))
                result = await run_agent_loop(runtime.config, [UserMessage('Python evidence')], context_pipeline=runtime.context_pipeline)
                self.assertFalse(result.is_error)
                counts.append(provider.calls[0]['system_prompt'].count('[probe:'))
            self.assertEqual(counts, [3, 1])
            self.assertEqual(baseline.mechanisms[0].parameters, {})

    async def test_skill_catalog_size_candidate_changes_the_projected_catalog(self):
        from fruitfly_agent.core.context import ContextFrame
        catalog = builtin_catalog()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            skill = root / '.skills/example/SKILL.md'; skill.parent.mkdir(parents=True)
            skill.write_text('---\nname: example\ndescription: ' + 'evidence ' * 100 + '\n---\nDo the task.\n')
            baseline = HarnessProfile('default', mechanisms=(MechanismSelection('skill-catalog'),))
            target = ParameterTarget(catalog.get('skill-catalog'), {}, {'max_chars'})
            values = json.loads(target.snapshot().text); values['settings']['max_chars'] = 128
            candidate = apply_profile_binding(baseline, 'configuration', 'component.skill-catalog', target.export_text(json.dumps(values)))
            omitted = []
            for index, profile in enumerate((baseline, candidate)):
                path = materialize_system(profile, root / str(index) / 'config.yaml', catalog=catalog)
                runtime = assemble_lab(AgentLoopConfig(provider=lambda *args: None), catalog=catalog,
                    selections=load_system_config(path).select().mechanisms,
                    context=AssemblyContext(root, None, '', lambda *args: None))
                transform = next(stage.mechanism for stage in runtime.context_pipeline.stages if stage.stage_id == 'skill-catalog')
                result = transform.transform(ContextFrame('base', (), (), 'fake', 32))
                omitted.append(result.metadata['catalog_omitted'])
            self.assertEqual(omitted, [False, True])

    async def test_bash_candidate_materializes_and_changes_actual_execution_timeout(self):
        catalog = builtin_catalog()
        definition = catalog.get('bash-tool')
        target = ParameterTarget(definition, {}, {'default_timeout_seconds'})
        options = {'editable_fields': ['parameters.settings.default_timeout_seconds'],
            'bounds': {'parameters.settings.default_timeout_seconds': {'minimum': 1, 'maximum': 240}}}
        target.validate_options(options)
        values = json.loads(target.snapshot().text)
        values['settings']['default_timeout_seconds'] = 7
        text = json.dumps(values)
        target.validate_change(text, options)
        baseline = HarnessProfile('default', mechanisms=(MechanismSelection('local-env'), MechanismSelection('bash-tool')))
        candidate = apply_profile_binding(baseline, 'configuration', 'component.bash-tool', target.export_text(text))
        with tempfile.TemporaryDirectory() as directory:
            destination = materialize_system(candidate, Path(directory) / 'candidate/config.yaml', catalog=catalog)
            restored = load_system_config(destination).select()
            resources = []
            result = assemble_lab(AgentLoopConfig(provider=lambda *a, **k: None), catalog=catalog,
                selections=restored.mechanisms,
                context=AssemblyContext(Path(directory), None, '', lambda *args: None, resource_sink=resources))
            try:
                execute = AsyncMock(return_value=Result.success(ExecResult('done', '', 0)))
                result.config.env.exec = execute
                tool = next(tool for tool in result.config.tools if tool.name == 'bash')
                await tool.execute(ToolCallContext('call', 'bash', {'command': 'fixture'}, env=result.config.env))
                self.assertEqual(execute.call_args.args[1].timeout_seconds, 7)
                self.assertEqual(baseline.mechanisms[-1].parameters, {})
            finally:
                for resource in reversed(resources):
                    if hasattr(resource, 'aclose'): await resource.aclose()

    def test_parameter_grants_reject_secrets_unknown_fields_and_out_of_bounds(self):
        definition = builtin_catalog().get('web-search-tool')
        target = ParameterTarget(definition, {}, {'timeout_seconds'})
        with self.assertRaises(ValueError): target.validate_options({'editable_fields': ['api_key']})
        values = json.loads(target.snapshot().text)
        values['settings']['timeout_seconds'] = 10
        with self.assertRaises(ValueError):
            target.validate_change(json.dumps(values), {'editable_fields': ['parameters.settings.timeout_seconds'],
                'bounds': {'parameters.settings.timeout_seconds': {'maximum': 5}}})
        with self.assertRaises(ValueError): target.parse('{"timeout_seconds":1,"timeout_seconds":2}')

    def test_editor_instruction_grants_and_exact_restoration(self):
        target=EditorInstructionTarget()
        options=editor_edit_options(['parameters.instructions.propose'],{})
        target.validate_options(options)
        value=json.loads(target.snapshot().text);value['instructions']['propose']='Inspect source evidence and test a behavioral change.'
        text=json.dumps(value,indent=2);target.validate_change(text,options)
        restored=restore_editor({'model_role':'editor'},text)
        self.assertEqual(restored['instructions']['propose'],value['instructions']['propose'])
        self.assertEqual(EditorInstructionTarget.parse_document(text).propose,value['instructions']['propose'])
        with self.assertRaises(ValueError):target.validate_change(text,{'editable_fields':['parameters.instructions.reflect']})
        with self.assertRaises(ValueError):editor_edit_options(['parameters.max_tool_calls'],{})

    async def test_context_prompt_candidates_materialize_and_change_real_auxiliary_requests(self):
        from fruitfly_agent.core.data_model import ContextItem, ContextSnapshot, UserMessage, AssistantMessage, ToolCallBlock, ToolResultMessage, TextBlock
        from fruitfly_agent.lab.catalog import ProviderBinding
        from tests.support.faux_provider import FauxProvider
        for name, field in (('working-memory-reduction', 'update_instructions'),):
            with self.subTest(method=name), tempfile.TemporaryDirectory() as directory:
                catalog = builtin_catalog(); definition = catalog.get(name)
                target = ParameterTarget(definition, {}, {field})
                grant = {'editable_fields': ['parameters.instructions.update']}
                target.validate_options(grant)
                values = json.loads(target.snapshot().text)
                values['instructions']['update'] = 'EXACT candidate prompt\nKeep verified constraints and pending tests.'
                text = json.dumps(values)
                target.validate_change(text, grant)
                baseline = HarnessProfile('default', mechanisms=(MechanismSelection('context-history'), MechanismSelection(name)))
                candidate = apply_profile_binding(baseline, 'configuration', 'component.' + name, target.export_text(text))
                path = materialize_system(candidate, Path(directory) / 'candidate/config.yaml', catalog=catalog)
                restored = load_system_config(path).select()
                provider = FauxProvider(); provider.respond_text('completed inspection; next run verifier')
                runtime = assemble_lab(AgentLoopConfig(provider=FauxProvider()), catalog=catalog,
                    selections=restored.mechanisms, context=AssemblyContext(Path(directory), None, 'fake',
                        lambda *args: ProviderBinding(provider, 'fake', 'fake', 16000, 64)))
                messages = (UserMessage('Complete the task'), AssistantMessage([ToolCallBlock('c', 'read', {})]),
                    ToolResultMessage('c', [TextBlock('full evidence ' + 'x' * 12000)]), UserMessage('Keep the correction'))
                snapshot = ContextSnapshot(tuple(ContextItem(str(i), m) for i, m in enumerate(messages)), messages,
                    '', (), 2048, 'fake', 32, 'budget')
                decision = await runtime.context_pipeline.check_budget(snapshot)
                self.assertIsNotNone(decision)
                self.assertIn(values['instructions']['update'], provider.calls[0]['messages'][0].content)
                installed = runtime.components['text-target:' + name].snapshot()
                self.assertNotEqual(target.snapshot().content_hash, installed.content_hash)
                self.assertEqual(values['instructions']['update'], json.loads(installed.text)['instructions']['update'])
                self.assertEqual({}, baseline.mechanisms[-1].parameters)

    async def test_measurement_is_shared_without_a_selectable_or_editable_component(self):
        from fruitfly_agent.lab.context_manager.measurement.budget import MeasurementService
        from tests.support.faux_provider import FauxProvider
        catalog = builtin_catalog()
        with self.assertRaises(ValueError): catalog.get('context-measurement')
        runtime = assemble_lab(AgentLoopConfig(FauxProvider()), catalog=catalog, selections=(),
            context=AssemblyContext(Path.cwd(), None, '', lambda *a: None))
        self.assertIsInstance(runtime.config.context_meter, MeasurementService)
        self.assertNotIn('text-target:context-measurement', runtime.components)

    async def test_history_capacity_candidate_changes_actual_artifact_admission(self):
        from tests.support.faux_provider import FauxProvider
        catalog = builtin_catalog(); definition = catalog.get('context-history')
        target = ParameterTarget(definition, {}, {'max_artifact_bytes'})
        values = json.loads(target.snapshot().text); values['settings']['max_artifact_bytes'] = 1024
        text = json.dumps(values)
        target.validate_change(text, {'editable_fields': ['parameters.settings.max_artifact_bytes'],
            'bounds': {'parameters.settings.max_artifact_bytes': {'minimum': 1024, 'maximum': 16000000}}})
        profile = HarnessProfile('default', mechanisms=(MechanismSelection('context-history'),))
        candidate = apply_profile_binding(profile, 'configuration', 'component.context-history', target.export_text(text))
        with tempfile.TemporaryDirectory() as directory:
            path = materialize_system(candidate, Path(directory) / 'config.yaml', catalog=catalog)
            restored = load_system_config(path).select()
            runtime = assemble_lab(AgentLoopConfig(provider=FauxProvider()), catalog=catalog,
                selections=restored.mechanisms, context=AssemblyContext(Path(directory), None, 'fake', lambda *a: None))
            history = runtime.components['context-history']
            with self.assertRaisesRegex(ValueError, 'max_artifact_bytes'): history.put('x' * 1500)
            reference = history.put('small archive')
            self.assertEqual('small archive', history.text(reference))
