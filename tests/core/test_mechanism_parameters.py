"""Generic structured parameter values stay finite, detached and serializable."""
import unittest
from fruitfly_agent.core.mechanisms import ParameterDescriptor


class StructuredParameterTests(unittest.TestCase):
    def descriptor(self, value=None):
        return ParameterDescriptor('options', 'object', 'Options', 'Owner-validated structured options.', value or {})

    def test_object_defaults_normalization_and_serialization_are_detached(self):
        source = {'items': [{'limit': 2}]}
        descriptor = self.descriptor(source)
        source['items'][0]['limit'] = 3
        normalized = descriptor.validate(descriptor.default)
        normalized['items'][0]['limit'] = 4
        payload = descriptor.to_dict()
        payload['default']['items'][0]['limit'] = 5
        self.assertEqual(2, descriptor.default['items'][0]['limit'])
        self.assertEqual({'items': [{'limit': 2}]}, descriptor.parse('{"items":[{"limit":2}]}'))

    def test_object_parameters_reject_nonobjects_duplicate_keys_and_nonfinite_data(self):
        descriptor = self.descriptor()
        for value in ([], 'text', {1: 'bad key'}, {'value': float('nan')}, {'value': b'bytes'}):
            with self.subTest(value=value), self.assertRaises(ValueError):
                descriptor.validate(value)
        for text in ('[]', 'null', '{"a":1,"a":2}', '{"a":{"b":1,"b":2}}', '{"a":Infinity}'):
            with self.subTest(text=text), self.assertRaises(ValueError):
                descriptor.parse(text)
        cyclic = {}; cyclic['self'] = cyclic
        with self.assertRaises(ValueError):
            descriptor.validate(cyclic)
