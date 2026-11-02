"""Compaction uses ordinary configuration, model binding and owner grants."""
import json
from dataclasses import replace
from pathlib import Path
import tempfile
import unittest

from fruitfly_agent.core.session import Session
from fruitfly_agent.lab.catalog import builtin_catalog, MechanismSelection
from fruitfly_agent.run.configuration import HarnessProfile
from fruitfly_agent.run import RunConfigurationController, resolve_harness_selection
from tests.support.assembly import AssemblyWorkspace


class LayeredConfigurationTests(unittest.TestCase):
    def setUp(self):
        self.workspace = AssemblyWorkspace(self.enterContext(tempfile.TemporaryDirectory()))
        self.catalog = builtin_catalog()

    def profile(self, **parameters):
        selections = tuple(replace(s, parameters=parameters) if s.mechanism_id == 'layered-compaction'
            else s for s in self.catalog.default_selections())
        return HarnessProfile('default', str(self.workspace.model_path), 'offline', selections)

    def test_default_has_no_auxiliary_provider_and_conditional_grants_protect_inactive_fields(self):
        with Session(self.workspace.root / 'session.jsonl') as session:
            runtime = self.workspace.assemble(self.profile(), session, catalog=self.catalog)
            self.assertEqual(self.workspace.registry.create.call_count, 1)
            target = runtime.components['text-target:layered-compaction']
            fields = target.field_names()
            self.assertIn('parameters.instructions.readback', fields)
            self.assertNotIn('parameters.instructions.summary', fields)
            for path in ('parameters.instructions.summary', 'parameters.settings.mode',
                         'parameters.settings.summary_model_profile'):
                with self.subTest(path=path), self.assertRaises(ValueError):
                    target.validate_options({'editable_fields': [path]})
            value = json.loads(target.snapshot().text)
            value['settings']['mode'] = 'hybrid'
            with self.assertRaises(ValueError): target.validate_change(json.dumps(value), {})

    def test_hybrid_requires_explicit_binding_and_admits_summary_grants(self):
        with Session(self.workspace.root / 'session.jsonl') as session:
            with self.assertRaisesRegex(ValueError, 'context_summary'):
                self.workspace.assemble(self.profile(mode='hybrid'), session, catalog=self.catalog)
            runtime = self.workspace.assemble(self.profile(mode='hybrid', summary_model_profile='offline'),
                session, catalog=self.catalog)
            target = runtime.components['text-target:layered-compaction']
            target.validate_options({'editable_fields': ['parameters.instructions.summary']})
            self.assertIn('parameters.instructions.summary', target.field_names())
            self.assertNotIn('parameters.settings.summary_model_profile', target.field_names())
            self.assertEqual(set(runtime.manifest.models), {'main', 'auxiliary-1'})

    def test_controller_switches_exclusive_reducer_and_reader_dependency(self):
        selection = resolve_harness_selection(cwd=self.workspace.root, config_path=None,
            profile_id=None, environment={}, catalog=self.catalog, allow_incomplete=True)
        controller = RunConfigurationController(selection, self.catalog)
        self.assertEqual(next(g for g in controller.snapshot().selection_groups
            if g.group_id == 'reduction').selected_id, 'layered-compaction')
        controller.select_algorithm('reduction', 'working-memory-reduction')
        self.assertFalse(next(s for s in controller.profile().mechanisms
            if s.mechanism_id == 'layered-compaction').enabled)
        controller.select_algorithm('reduction', 'layered-compaction')
        controller.set_mechanism('read-tool', enabled=False)
        self.assertFalse(next(s for s in controller.profile().mechanisms
            if s.mechanism_id == 'layered-compaction').enabled)
        with self.assertRaises(ValueError):
            self.catalog.resolve((MechanismSelection('layered-compaction'),))
