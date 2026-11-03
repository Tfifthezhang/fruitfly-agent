"""Unified policy changes execution; detailed tool usage stays source-owned."""
from tests.support.configuration import component_parameters, with_component_parameters, with_component_text, parameter_payload
from dataclasses import replace
from pathlib import Path
import tempfile
import unittest

from fruitfly_agent.core import AgentLoopConfig
from fruitfly_agent.core.data_model import UserMessage
from fruitfly_agent.core.loop import run_agent_loop
from fruitfly_agent.core.tool_runtime import ToolCallContext
from fruitfly_agent.lab.catalog import AssemblyContext, ProviderBinding, assemble_lab, builtin_catalog, MechanismSelection
from fruitfly_agent.lab.improvement.components import component_registry
from fruitfly_agent.lab.improvement.evidence import MemoryArtifacts
from fruitfly_agent.improvement.contracts.components import ComponentFile, HarnessSnapshot
from fruitfly_agent.lab.tools.catalog import ToolCatalogTarget, configuration_surface
from fruitfly_agent.lab.tools.read import create_read_tool
from fruitfly_agent.lab.tools.resources import ResourceRegistry
from fruitfly_agent.lab.tools.write import create_write_tool
from tests.support.faux_provider import FauxProvider
from fruitfly_agent.runtime_spec import HarnessProfile


class ToolCatalogTests(unittest.IsolatedAsyncioTestCase):
    async def test_full_usage_is_read_on_demand_without_changing_tool_contracts(self):
        provider = FauxProvider()
        detail = 'DETAILED_USAGE_ONLY: inspect the original before writing.'
        resources = ResourceRegistry()
        read = create_read_tool(resources=resources)
        write = replace(create_write_tool(), description=detail)
        target = ToolCatalogTarget('Inspect inputs and verify outputs.')
        config = target.prepare_trial(AgentLoopConfig(provider, tools=(read, write), readable_resources=resources), target.usage)
        prefix = f'resource://{config.readable_resources.scope}/tools/'
        provider.respond_tool_call('read', {'path': prefix + 'write.txt'})
        provider.respond_text('verified')
        try:
            result = await run_agent_loop(config, [UserMessage('Inspect the tool instructions')])
            self.assertFalse(result.is_error)
            self.assertNotIn(detail, provider.calls[0]['system_prompt'])
            self.assertFalse(any(detail in tool.description for tool in config.tools))
            self.assertIn(detail, next(m.text for m in provider.calls[-1]['messages'] if m.role == 'toolResult'))
            self.assertEqual({t.name for t in config.tools}, {'read', 'write'})
            for original, projected in zip((read, write), config.tools):
                self.assertIs(projected.execute, original.execute)
                self.assertEqual(projected.parameters, original.parameters)
                self.assertEqual(projected.permission, original.permission)
            with self.assertRaises(ValueError):
                await config.tools[1].execute(ToolCallContext('w', 'write',
                    {'path': prefix + 'write.txt', 'content': 'changed'}, env=object()))
            again = target.prepare_trial(config, 'Use original evidence.')
            self.assertEqual(again.system_prompt.count('<!-- fruitfly:tool-catalog:start -->'), 1)
            self.assertEqual(again.readable_resources.read(prefix + 'write.txt').decode(), detail)
        finally:
            config.readable_resources.close()

    async def test_ordinary_assembly_applies_candidate_policy_and_keeps_resource_scopes_separate(self):
        catalog = builtin_catalog()
        provider = FauxProvider()
        profile = HarnessProfile('trial', mechanisms=tuple(MechanismSelection(name)
            for name in ('local-env', 'read-tool', 'write-tool')))
        with tempfile.TemporaryDirectory() as directory:
            original = assemble_lab(AgentLoopConfig(provider), catalog=catalog, selections=profile.mechanisms,
                context=AssemblyContext(Path(directory), None, 'fake', lambda *a: ProviderBinding(provider, 'fake', 'fake')))
            self.assertEqual(original.config.system_prompt, '')
            self.assertIn('instruction-components.tool-catalog', original.context_pipeline.profile.augmentation)
            registry = component_registry(tuple(v for k, v in original.components.items() if k.startswith('text-target:')))
            baseline = registry.snapshot()
            old = baseline.component('tool-catalog')
            changed = with_component_text(old, 'CANDIDATE_POLICY: verify before completion.')
            candidate = HarnessSnapshot(tuple(changed if d.component_id == old.component_id else d for d in baseline.components))
            scopes = []
            for harness in (baseline, candidate):
                owned = []
                policy = component_parameters(harness.component('tool-catalog'))['instructions']['usage']
                trial = assemble_lab(AgentLoopConfig(provider), catalog=catalog, selections=profile.mechanisms,
                    context=AssemblyContext(Path(directory), None, 'fake', lambda *a: ProviderBinding(provider, 'fake', 'fake'),
                        resource_sink=owned, artifact_bindings={'tool-catalog': policy}, artifact_reader=lambda key: key))
                scopes.append(trial.config.readable_resources)
                prefix = f'resource://{scopes[-1].scope}/tools/'
                provider.respond_tool_call('read', {'path': prefix + 'write.txt'})
                provider.respond_text('done')
                try:
                    result = await run_agent_loop(trial.config, [UserMessage('Inspect instructions')], context_pipeline=trial.context_pipeline)
                    self.assertFalse(result.is_error)
                    self.assertIn('Write a complete', next(m.text for m in result.messages if m.role == 'toolResult'))
                finally:
                    for value in reversed(owned):
                        close = getattr(value, 'aclose', None) or getattr(value, 'close', None)
                        if close:
                            result = close()
                            if hasattr(result, '__await__'): await result
            self.assertNotIn('CANDIDATE_POLICY', provider.calls[0]['system_prompt'])
            self.assertIn('CANDIDATE_POLICY', provider.calls[2]['system_prompt'])
            self.assertTrue(all(scope.closed for scope in scopes))
            self.assertIsNot(scopes[0], scopes[1])
            self.assertEqual(registry.snapshot(), baseline)

    def test_no_reader_keeps_usage_inline_and_policy_has_no_schema_edit_fields(self):
        tool = create_write_tool()
        config = ToolCatalogTarget().prepare_trial(AgentLoopConfig(FauxProvider(), tools=(tool,)), 'Verify results.')
        try:
            self.assertEqual(config.tools[0].description, tool.description)
            surface = configuration_surface()
            with self.assertRaises(ValueError):
                surface.edit_options(['parameters.settings.schema'], {})
        finally:
            config.readable_resources.close()
