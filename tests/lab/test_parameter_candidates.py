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
    async def test_bash_candidate_materializes_and_changes_actual_execution_timeout(self):
        catalog = builtin_catalog()
        definition = catalog.get('bash-tool')
        target = ParameterTarget(definition, {}, {'default_timeout_seconds'})
        options = {'editable_fields': ['default_timeout_seconds'],
            'bounds': {'default_timeout_seconds': {'minimum': 1, 'maximum': 240}}}
        target.validate_options(options)
        values = json.loads(target.snapshot().text)
        values['default_timeout_seconds'] = 7
        text = json.dumps(values)
        target.validate_change(text, options)
        baseline = HarnessProfile('default', mechanisms=(MechanismSelection('local-env'), MechanismSelection('bash-tool')))
        candidate = apply_profile_binding(baseline, 'configuration', 'component.bash-tool', text)
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
        values['timeout_seconds'] = 10
        with self.assertRaises(ValueError):
            target.validate_change(json.dumps(values), {'editable_fields': ['timeout_seconds'],
                'bounds': {'timeout_seconds': {'maximum': 5}}})
        with self.assertRaises(ValueError): target.parse('{"timeout_seconds":1,"timeout_seconds":2}')

    def test_editor_tool_allowance_has_a_grant_bounds_and_exact_restoration(self):
        target = EditorInstructionTarget(max_tool_calls=48)
        options = editor_edit_options(['parameters.max_tool_calls'],
            {'parameters.max_tool_calls': {'minimum': 24, 'maximum': 96}})
        target.validate_options(options)
        value = json.loads(target.snapshot().text); value['max_tool_calls'] = 72
        text = json.dumps(value, indent=2)
        target.validate_change(text, options)
        restored = restore_editor({'model_role': 'editor'}, text)
        self.assertEqual(restored['max_tool_calls'], 72)
        self.assertEqual(EditorInstructionTarget.parse_document(text)[1], 72)
        with self.assertRaises(ValueError):
            target.validate_change(text, {'editable_fields': ['propose']})
        value['max_tool_calls'] = 100
        with self.assertRaises(ValueError): target.validate_change(json.dumps(value), options)

    async def test_context_prompt_candidates_materialize_and_change_real_auxiliary_requests(self):
        from fruitfly_agent.core.data_model import ContextItem, ContextSnapshot, UserMessage, AssistantMessage, ToolCallBlock, ToolResultMessage, TextBlock
        from fruitfly_agent.lab.catalog import ProviderBinding
        from tests.support.faux_provider import FauxProvider
        for name, field in (('compaction', 'summary_instructions'), ('working-memory-reduction', 'update_instructions')):
            with self.subTest(method=name), tempfile.TemporaryDirectory() as directory:
                catalog = builtin_catalog(); definition = catalog.get(name)
                target = ParameterTarget(definition, {}, {field})
                grant = {'editable_fields': [field]}
                target.validate_options(grant)
                values = json.loads(target.snapshot().text)
                values[field] = 'EXACT candidate prompt\nKeep verified constraints and pending tests.'
                text = json.dumps(values)
                target.validate_change(text, grant)
                baseline = HarnessProfile('default', mechanisms=(MechanismSelection('context-history'), MechanismSelection(name)))
                candidate = apply_profile_binding(baseline, 'configuration', 'component.' + name, text)
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
                self.assertIn(values[field], provider.calls[0]['messages'][0].content)
                installed = runtime.components['text-target:' + name].snapshot()
                self.assertNotEqual(target.snapshot().content_hash, installed.content_hash)
                self.assertEqual(values[field], json.loads(installed.text)[field])
                self.assertEqual({}, baseline.mechanisms[-1].parameters)

    async def test_measurement_candidate_changes_actual_budget_without_modifying_precision_controls(self):
        from fruitfly_agent.core.data_model import ProviderView, UserMessage
        definition = builtin_catalog().get('context-measurement')
        target = ParameterTarget(definition, {}, {'margin_tokens'})
        value = json.loads(target.snapshot().text); value['margin_tokens'] = 500
        target.validate_change(json.dumps(value), {'editable_fields': ['margin_tokens']})
        with tempfile.TemporaryDirectory() as directory:
            baseline = HarnessProfile('default', mechanisms=(MechanismSelection('context-measurement'),))
            candidate = apply_profile_binding(baseline, 'configuration', 'component.context-measurement', json.dumps(value))
            path = materialize_system(candidate, Path(directory) / 'config.yaml', catalog=builtin_catalog())
            profile = load_system_config(path).select()
            runtime = assemble_lab(AgentLoopConfig(provider=lambda *a, **k: None), catalog=builtin_catalog(),
                selections=profile.mechanisms, context=AssemblyContext(Path(directory), None, '', lambda *a: None))
            measure = await runtime.config.context_meter.measure(ProviderView('', [UserMessage('task')], [], '', 32), runtime.config.provider)
            self.assertEqual(500, measure.margin)
            self.assertEqual('heuristic', measure.quality)
            installed = runtime.components['text-target:context-measurement']
            with self.assertRaises(ValueError): installed.validate_options({'editable_fields': ['strict']})

    async def test_history_capacity_candidate_changes_actual_artifact_admission(self):
        from tests.support.faux_provider import FauxProvider
        catalog = builtin_catalog(); definition = catalog.get('context-history')
        target = ParameterTarget(definition, {}, {'max_artifact_bytes'})
        values = json.loads(target.snapshot().text); values['max_artifact_bytes'] = 1024
        text = json.dumps(values)
        target.validate_change(text, {'editable_fields': ['max_artifact_bytes'],
            'bounds': {'max_artifact_bytes': {'minimum': 1024, 'maximum': 16000000}}})
        profile = HarnessProfile('default', mechanisms=(MechanismSelection('context-history'),))
        candidate = apply_profile_binding(profile, 'configuration', 'component.context-history', text)
        with tempfile.TemporaryDirectory() as directory:
            path = materialize_system(candidate, Path(directory) / 'config.yaml', catalog=catalog)
            restored = load_system_config(path).select()
            runtime = assemble_lab(AgentLoopConfig(provider=FauxProvider()), catalog=catalog,
                selections=restored.mechanisms, context=AssemblyContext(Path(directory), None, 'fake', lambda *a: None))
            history = runtime.components['context-history']
            with self.assertRaisesRegex(ValueError, 'max_artifact_bytes'): history.put('x' * 1500)
            reference = history.put('small archive')
            self.assertEqual('small archive', history.text(reference))
