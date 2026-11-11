"""One YAML decoder and explicit bounded installed-resource access."""
import unittest
from unittest.mock import patch
from fruitfly_agent.core.configuration_resources import decode_yaml, package_parameter, package_bytes


class ConfigurationResourceTests(unittest.TestCase):
    def test_decoded_values_are_detached_and_invalid_mappings_are_rejected(self):
        data = b'parameters:\n  items: [first]\n'
        value = decode_yaml(data)
        value['parameters']['items'].append('changed')
        self.assertEqual(['first'], decode_yaml(data)['parameters']['items'])
        for invalid in (b'a: 1\na: 2', b'1: wrong', b'a: [', b'\xff'):
            with self.subTest(data=invalid), self.assertRaises(ValueError):
                decode_yaml(invalid)

    def test_parameter_access_is_explicit_and_cannot_select_a_path(self):
        with patch('fruitfly_agent.core.configuration_resources.package_bytes', return_value=b'parameters: {time: 7}'):
            self.assertEqual(7, package_parameter('explicit.owner', 'defaults.yaml', 'time'))
        for package, resource in (('bad/owner', 'defaults.yaml'), ('fruitfly_agent.core', '../defaults.yaml')):
            with self.subTest(resource=resource), self.assertRaises(ValueError):
                package_bytes(package, resource)
