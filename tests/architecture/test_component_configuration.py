"""Registered component configuration remains pure and independent of hosts."""
from dataclasses import replace
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import yaml

from fruitfly_agent.core.mechanisms import ParameterDescriptor
from fruitfly_agent.lab.catalog import builtin_catalog, load_system_config, configuration_inventory
from fruitfly_agent.lab.catalog.configuration import configuration_surfaces


class ComponentAdmissionTests(unittest.TestCase):
    def test_builtin_declarations_have_unique_configuration_positions_and_documented_owners(self):
        catalog = builtin_catalog()
        surfaces = configuration_surfaces(catalog)
        definitions = catalog.definitions()
        root = Path(__file__).resolve().parents[2]
        self.assertEqual(len({d.descriptor.mechanism_id for d in definitions}), len(definitions))
        for definition in definitions:
            with self.subTest(owner=definition.descriptor.mechanism_id):
                self.assertIn(definition.configuration_role, ('H', 'S', 'I'))
                self.assertTrue((root / definition.implementation_path).is_file())
                self.assertTrue((root / definition.documentation_path).is_file())
                for surface in definition.configuration_surfaces:
                    self.assertEqual(surfaces[surface.id][0], definition.descriptor.mechanism_id)

    def test_new_parameter_owner_loads_and_inspects_without_host_dispatch_or_installer_work(self):
        catalog = builtin_catalog()
        template = catalog.get('local-env')
        def install(*args):
            raise AssertionError('inspection must not install a component')
        definition = replace(template, descriptor=replace(template.descriptor,
            mechanism_id='custom-owner', parameters=(ParameterDescriptor('capacity', 'integer',
                'Capacity', 'Bounded offline fixture.', 3, minimum=1),)), install=install)
        catalog = catalog.extended((definition,))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'config.yaml'
            path.write_text(yaml.safe_dump({'schema_version': 2, 'default_profile': 'test',
                'profiles': {'test': {'models': {'catalog': 'models.yaml', 'roles': {'executor': 'fake'}},
                    'H': {'custom-owner': {'inline': {'schema_version': 1, 'id': 'custom-owner',
                        'implementation': 'custom-owner', 'role': 'H', 'parameters': {'capacity': 7}}}}}}}))
            with patch('fruitfly_agent.providers.registry.ProviderRegistry.create', side_effect=AssertionError('Provider')):
                profile = load_system_config(path, catalog=catalog).select()
                rows = configuration_inventory(profile, catalog)
            row = next(row for row in rows if row['id'] == 'custom-owner')
            self.assertEqual(row['effective']['capacity'], 7)
            self.assertFalse(row['field_editing_declared'])
            self.assertEqual(profile.mechanisms[0].mechanism_id, 'custom-owner')
