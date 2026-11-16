"""Shared budget candidates alter actual context execution without source edits."""
from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest

from fruitfly_agent.core.config import AgentLoopConfig
from fruitfly_agent.core.context.budget import ContextBudget
from fruitfly_agent.core.data_model import AssistantMessage, TextBlock, UserMessage
from fruitfly_agent.core.loop import run_agent_loop
from fruitfly_agent.lab.catalog import builtin_catalog, assemble_lab, AssemblyContext, load_system_config
from fruitfly_agent.lab.catalog.configuration import materialize_system
from fruitfly_agent.lab.catalog.adapters.parameters import ParameterTarget
from fruitfly_agent.runtime_spec import HarnessProfile, MechanismSelection
from fruitfly_agent.runtime_spec.execution import apply_profile_binding
from tests.support.faux_provider import FauxProvider


class SharedBudgetExecutionTests(unittest.IsolatedAsyncioTestCase):
    async def test_threshold_candidate_changes_isolated_execution_and_protects_ceiling(self):
        catalog = builtin_catalog()
        baseline = HarnessProfile('test', mechanisms=tuple(MechanismSelection(name) for name in
            ('context-budget', 'local-env', 'read-tool', 'layered-compaction')))
        target = ParameterTarget(catalog.get('context-budget'), {}, {'trigger_ratio', 'target_ratio'})
        before = target.snapshot()
        values = json.loads(before.text)
        values['settings'].update(trigger_ratio=.5, target_ratio=.25)
        grant = {'editable_fields': ['parameters.settings.trigger_ratio', 'parameters.settings.target_ratio']}
        target.validate_change(json.dumps(values), grant)
        candidate = apply_profile_binding(baseline, 'configuration', 'component.context-budget', target.export_text(json.dumps(values)))
        forbidden = json.loads(before.text)
        forbidden['settings']['max_input_tokens'] *= 2
        with self.assertRaisesRegex(ValueError, 'fixed'):
            target.validate_change(json.dumps(forbidden), grant)
        counts, identities = [], []
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for index, profile in enumerate((baseline, candidate)):
                path = materialize_system(profile, root / str(index) / 'config.yaml', catalog=catalog)
                source = path.read_bytes()
                restored = load_system_config(path).select()
                provider = FauxProvider(); provider.respond_text('done')
                resources = []
                runtime = assemble_lab(AgentLoopConfig(provider, context_window=1048576, max_tokens=128),
                    catalog=catalog, selections=restored.mechanisms,
                    context=AssemblyContext(root, None, 'offline', lambda *args: None, resource_sink=resources))
                try:
                    messages = [UserMessage('Implement and verify the task.')]
                    for i in range(56):
                        messages.extend((AssistantMessage([TextBlock('evidence ' * 375)]), UserMessage('Keep correction ' + str(i))))
                    messages.append(UserMessage('Finish the task and report tests.'))
                    result = await run_agent_loop(runtime.config, messages, context_pipeline=runtime.context_pipeline)
                    self.assertFalse(result.is_error, result.error_details)
                    sent = provider.calls[0]['messages']
                    self.assertIn(messages[-1], sent)
                    self.assertIn(messages[0], sent)
                    counts.append(len(sent))
                    identities.append(restored.profile_hash)
                    self.assertEqual(source, path.read_bytes())
                finally:
                    for resource in reversed(resources):
                        close = getattr(resource, 'aclose', None) or getattr(resource, 'close', None)
                        if close:
                            result = close()
                            if hasattr(result, '__await__'): await result
        self.assertGreater(counts[0], counts[1])
        self.assertNotEqual(*identities)
        self.assertEqual({}, baseline.mechanisms[0].parameters)
        self.assertEqual(before, target.snapshot())

    def test_obsolete_method_thresholds_are_rejected(self):
        catalog = builtin_catalog()
        for name, field in (('layered-compaction', 'trigger_ratio'), ('layered-compaction', 'target_ratio'),
                            ('working-memory-reduction', 'switch_ratio')):
            with self.subTest(name=name, field=field), self.assertRaises(ValueError):
                catalog.resolve((MechanismSelection(name, parameters={field: .5}),))

    def test_execution_projection_cannot_change_undeclared_host_conditions(self):
        from fruitfly_agent.lab.catalog import resolve_execution_conditions
        definition = replace(builtin_catalog().get('context-budget'),
            execution_projection=lambda values: {'max_turns': 1})
        from fruitfly_agent.lab.catalog import LabCatalog
        catalog = LabCatalog((definition,))
        profile = HarnessProfile('test', mechanisms=(MechanismSelection('context-budget'),))
        with self.assertRaisesRegex(ValueError, 'undeclared'):
            resolve_execution_conditions(profile, catalog)
