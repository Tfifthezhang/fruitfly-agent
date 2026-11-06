"""One owner declaration drives menus, component discovery and conflict checks."""
from dataclasses import replace
import unittest

from fruitfly_agent.lab.catalog import (
    FeatureNode, LabCatalog, MechanismSelection, builtin_catalog, configuration_inventory,
    configure_profile, resolve_harness)
from fruitfly_agent.runtime_spec import HarnessProfile
from fruitfly_agent.run.configuration.views import mechanism_views
from fruitfly_agent.interactive.terminal.features.configuration.presentation import category_rows
from tests.support.configuration import MockConfiguration


class FeatureClassificationTests(unittest.TestCase):
    def test_extension_path_reaches_menu_and_optimization_without_host_dispatch(self):
        base = builtin_catalog()
        source = base.get('skills')
        path = (FeatureNode('custom-context', 'Custom context', 50),
                FeatureNode('injected', 'Injected selection', 5))
        catalog = LabCatalog(tuple(replace(d, feature_path=path)
            if d.descriptor.mechanism_id == 'skills' else d for d in base.definitions()), bootstrap=base.bootstrap)
        profile = configure_profile(HarnessProfile('test', mechanisms=base.default_selections()), catalog)
        mechanisms, groups = mechanism_views(profile, catalog, [])
        view = next(v for v in mechanisms if v.mechanism_id == 'skills')
        self.assertEqual(('custom-context', 'injected'), tuple(n[0] for n in view.feature_path))
        snapshot = replace(MockConfiguration(model='offline').snapshot(), mechanisms=mechanisms, selection_groups=groups)
        rows, _ = category_rows(snapshot, 'custom-context', None)
        self.assertEqual('Injected selection', rows[0].section)
        components = {c.component_id: c for c in resolve_harness(profile, catalog).components}
        self.assertEqual(('custom-context', 'injected'), components['skills'].feature_path)
        self.assertEqual(components['skills'].feature_path, components['skill-library'].feature_path)
        inventory = {row['id']: row for row in configuration_inventory(profile, catalog)}
        self.assertEqual(['custom-context', 'injected'], inventory['skill-library']['feature_path'])

    def test_conflicting_classification_and_surface_identity_fail_at_registration(self):
        base = builtin_catalog()
        value = base.get('local-env')
        duplicate = replace(value, descriptor=replace(value.descriptor, mechanism_id='fixture-env'))
        with self.assertRaisesRegex(ValueError, 'conflicting feature classification'):
            base.extended((replace(duplicate, feature_path=(FeatureNode('environment', 'Other label'),)),))
        with self.assertRaisesRegex(ValueError, 'feature path'):
            LabCatalog((replace(duplicate, feature_path=()),))
        with self.assertRaisesRegex(ValueError, 'surface identity'):
            base.extended((replace(duplicate, descriptor=replace(duplicate.descriptor, mechanism_id='skill-library')),))

    def test_retained_content_is_not_selectable_and_default_loaders_are_peers(self):
        catalog = builtin_catalog()
        defaults = catalog.default_selections()
        profile = configure_profile(HarnessProfile('daily', mechanisms=defaults), catalog)
        selected = {s.mechanism_id for s in defaults}
        self.assertTrue({'skills', 'file-memory'} <= selected)
        for identity in ('memory-library', 'skill-library', 'execution-policy', 'tool-catalog', 'skill-document'):
            with self.subTest(identity=identity), self.assertRaisesRegex(ValueError, 'unknown mechanism'):
                catalog.resolve((MechanismSelection(identity),))
        memory = catalog.get('file-memory')
        self.assertTrue(memory.descriptor.normalize_parameters({})['maintenance_enabled'])
        self.assertEqual('memory', memory.selection_group)
        self.assertEqual(('context', 'augmentation', 'memory'), tuple(n.id for n in memory.feature_path))
        self.assertEqual((), catalog.get('skills').input_parameters)
        mechanisms, _ = mechanism_views(profile, catalog, [])
        self.assertFalse(next(m for m in mechanisms if m.mechanism_id == 'component-improvement').visible)
        components = {c.component_id: c for c in resolve_harness(profile, catalog).components}
        self.assertEqual('H', components['file-memory'].role)
        self.assertEqual('S', components['memory-library'].role)
        self.assertEqual('S', components['skill-library'].role)
        self.assertEqual('I', components['improvement-editor'].role)
        self.assertEqual('I', components['improvement-evaluator'].role)

    def test_disabling_loaders_preserves_content_without_exposing_editable_state(self):
        catalog = builtin_catalog()
        profile = configure_profile(HarnessProfile('off', mechanisms=tuple(
            replace(s, enabled=False) if s.mechanism_id in {'file-memory', 'skills'} else s
            for s in catalog.default_selections())), catalog)
        ids = {c.component_id for c in resolve_harness(profile, catalog).components}
        self.assertFalse({'file-memory', 'skills', 'memory-library', 'skill-library'} & ids)

    def test_external_connectors_name_shared_projection_policy_without_editing_sources(self):
        catalog = builtin_catalog()
        for name in ('knowledge-files', 'live-http'):
            coverage = catalog.get(name).optimization_coverage
            self.assertEqual(('shared', ('information-context',)), (coverage.kind, coverage.components))
        self.assertEqual('protected', catalog.get('mcp-tools').optimization_coverage.kind)
        self.assertEqual('protected', catalog.get('remote-env').optimization_coverage.kind)
